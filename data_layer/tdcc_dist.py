"""集保戶股權分散週表（tdcc_dist）：由 Goodinfo 持股分級週統計原檔建表。

來源：Goodinfo EquityDistributionClassHis（集保結算所「集保戶股權分散表」週統計，簡化 8 級）。
原檔不進 repo，與 tdcc_dist.parquet 一起發佈在 Releases；清冊記 sha256。

可接受兩種原檔格式：
- 精簡格式（053_tdcc_goodinfo_20261108.json）：stocks[sid].wk = ["YYYYMMDD;收盤;集保庫存萬張;總人數;人數×8;比例×8", ...]
- 原表格式（053_tdcc_goodinfo_2015_*.json）：stocks[sid].people.wk / pct.wk = ["16W14;04/01;收盤;漲跌;漲跌%;總量;8 級...", ...]

輸出欄位（每股每週一列）：
  stock_id(str)、date(資料日期，週五為主)、holders(總股東人數)、lots_10k(集保庫存，萬張)、
  n_le10、n_10_50、n_50_100、n_100_200、n_200_400、n_400_800、n_800_1k、n_gt1k（各級人數）、
  r_le10 … r_gt1k（各級持有比例 %）、src（原檔名）
收盤價不收：價格一律用 daily_k。
可得時點：集保結算所於資料日期之後（目前為次一營業日、早年為週六）公布；研究上以「資料日期 + 7 日」後首個交易日開盤為保守可用時點，由策略卡另定。
精度：比例多數只到小數一位（約 ±0.05 個百分點）；人數為整數、精確。
缺值不推估：Goodinfo 無資料的週（日期為「-」或春節週）不產生列。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import pandas as pd

LEVELS = ["le10", "10_50", "50_100", "100_200", "200_400", "400_800", "800_1k", "gt1k"]
N_COLS = ["n_" + x for x in LEVELS]
R_COLS = ["r_" + x for x in LEVELS]
COLS = ["stock_id", "date", "holders", "lots_10k"] + N_COLS + R_COLS + ["src"]


def _num(s):
    s = str(s).replace(",", "").strip()
    if s in ("", "-", "N/A", "null", "undefined"):
        return None
    return float(s)


def _week_date(code: str, mmdd: str):
    """'16W14' + '04/01' → 2016-04-01；'16W01' + '12/31' → 2015-12-31。日期為 '-' 回 None。"""
    if not mmdd or "/" not in mmdd:
        return None
    yy, ww = int(code[:2]), int(code[3:5])
    mm, dd = (int(x) for x in mmdd.split("/"))
    y = 2000 + yy
    if mm == 12 and ww <= 2:
        y -= 1
    elif mm == 1 and ww >= 52:
        y += 1
    return pd.Timestamp(y, mm, dd)


def parse_compact(raw: dict, src: str) -> pd.DataFrame:
    head = raw["head"].split(";")
    assert head[3] == "總股東人數" and len(head) == 20, head
    rows = []
    for sid, v in raw["stocks"].items():
        for w in v.get("wk") or []:
            x = w.split(";")
            if not (len(x[0]) == 8 and x[0].isdigit()):
                continue
            vals = [_num(t) for t in x[2:]]
            if vals[1] is None:
                continue
            rows.append([sid, pd.Timestamp(x[0])] + vals[1:2] + vals[0:1] + vals[2:10] + vals[10:18] + [src])
    df = pd.DataFrame(rows, columns=["stock_id", "date", "holders", "lots_10k"] + N_COLS + R_COLS + ["src"])
    return df[COLS]


def parse_table(raw: dict, src: str) -> pd.DataFrame:
    def side(t):
        out = {}
        for w in t.get("wk") or []:
            x = w.split(";")
            if len(x) != 14:
                continue
            d = _week_date(x[0], x[1])
            if d is None or _num(x[5]) is None:
                continue
            out[d] = [_num(v) for v in x[5:14]]
        return out

    rows = []
    for sid, v in raw["stocks"].items():
        if v.get("err"):
            continue
        hp, hr = " ".join(v["people"]["head"]), " ".join(v["pct"]["head"])
        assert "人數" in hp and "比例" in hr, (sid, hp[:60], hr[:60])
        p, r = side(v["people"]), side(v["pct"])
        for d in sorted(set(p) & set(r)):
            rows.append([sid, d, p[d][0], r[d][0]] + p[d][1:] + r[d][1:] + [src])
    return pd.DataFrame(rows, columns=COLS)


def build(paths, out_dir):
    parts, files = [], {}
    for path in paths:
        raw = json.load(open(path, encoding="utf-8"))
        name = os.path.basename(path)
        files[name] = hashlib.sha256(open(path, "rb").read()).hexdigest()
        parts.append(parse_compact(raw, name) if "head" in raw else parse_table(raw, name))
    df = pd.concat(parts, ignore_index=True)
    # 重疊週：同股同日多來源時，數值須一致（比例容差 0.1），保留較新的原檔
    df = df.sort_values(["stock_id", "date", "src"])
    dup = df[df.duplicated(["stock_id", "date"], keep=False)]
    conflicts = 0
    if len(dup):
        g = dup.groupby(["stock_id", "date"])
        conflicts = int((g[N_COLS + ["holders"]].nunique() > 1).any(axis=1).sum()
                        + ((g[R_COLS].max() - g[R_COLS].min()) > 0.1001).any(axis=1).sum())
    df = df.drop_duplicates(["stock_id", "date"], keep="last").reset_index(drop=True)
    for c in ["holders"] + N_COLS:
        df[c] = df[c].astype("int64")
    log = {
        "rows": len(df), "stocks": int(df.stock_id.nunique()),
        "date_min": str(df.date.min().date()), "date_max": str(df.date.max().date()),
        "overlap_rows": int(len(dup)), "overlap_conflicts": conflicts,
        "people_sum_mismatch": int((df[N_COLS].sum(axis=1) != df.holders).sum()),
        "ratio_sum_range": [round(float(df[R_COLS].sum(axis=1).min()), 2), round(float(df[R_COLS].sum(axis=1).max()), 2)],
        "raw_files": files,
    }
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "tdcc_dist.parquet")
    df.to_parquet(p, index=False)
    log["sha256"] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    json.dump(log, open(os.path.join(out_dir, "tdcc_dist_log.json"), "w"), ensure_ascii=False, indent=1)
    return df, log


def big_ratio(df: pd.DataFrame, min_lots: int = 1000) -> pd.Series:
    """>min_lots 張持有比例（%）；min_lots ∈ {400, 800, 1000}。"""
    cols = {400: ["r_400_800", "r_800_1k", "r_gt1k"], 800: ["r_800_1k", "r_gt1k"], 1000: ["r_gt1k"]}[min_lots]
    return df[cols].sum(axis=1)


def big_holders(df: pd.DataFrame, min_lots: int = 400) -> pd.Series:
    """>min_lots 張持有人數；min_lots ∈ {400, 800, 1000}。"""
    cols = {400: ["n_400_800", "n_800_1k", "n_gt1k"], 800: ["n_800_1k", "n_gt1k"], 1000: ["n_gt1k"]}[min_lots]
    return df[cols].sum(axis=1)


if __name__ == "__main__":
    out = sys.argv[1]
    _, lg = build(sys.argv[2:], out)
    print(json.dumps({k: v for k, v in lg.items() if k != "raw_files"}, ensure_ascii=False))
