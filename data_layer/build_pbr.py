"""估值組建置：官方每日本益比／殖利率／股價淨值比 → valuation_daily、valuation_coverage（D-071-20261111-2354-1）。

用法：RAW=raw CAL=jobs/trading_days.txt OUT=out REQUIRE=all|monthend python data_layer/build_pbr.py
- 欄位依各檔 fields 名稱對應（官方欄位順序歷年不同，不依位置）。
- 「-」「N/A」與空白一律為缺值（NaN），不推估；數字去除千分位。
- 公司名稱附「*」者（櫃買註明：無面額或面額非 10 元，數值自換發新股起配合調整）記 name_star=True。
- valuation_coverage 逐交易日逐市場記錄：ok（有資料）、empty（官方明示查無）、missing（尚未取得）。
- REQUIRE=all：任一交易日 missing 即停止；REQUIRE=monthend：每月最後一個交易日不得 missing，其餘 missing 照實記錄。
"""
import glob, json, os, sys

import numpy as np
import pandas as pd

RAW = os.environ.get("RAW", "raw")
OUT = os.environ.get("OUT", "out")
CAL = os.environ.get("CAL", "jobs/trading_days.txt")
REQUIRE = os.environ.get("REQUIRE", "all")
START = {"twse_pbr": "2005-09-02", "tpex_pbr": "2007-01-02"}
MARKET = {"twse_pbr": "上市", "tpex_pbr": "上櫃"}
COLMAP = {"本益比": "pe", "殖利率(%)": "dividend_yield", "股價淨值比": "pbr", "財報年/季": "fin_period",
          "收盤價": "close_ref", "股利年度": "div_year", "每股股利": "dps"}


def num(x):
    if x is None:
        return np.nan
    s = str(x).replace(",", "").strip()
    if s in ("", "-", "--", "N/A", "NA", "null"):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def parse(src, fp):
    j = json.load(open(fp, encoding="utf-8"))
    if src == "twse_pbr":
        fields, rows = j.get("fields") or [], j.get("data") or []
    else:
        t = (j.get("tables") or [{}])[0]
        fields, rows = t.get("fields") or [], t.get("data") or []
    if not rows:
        return None
    idx = {f: i for i, f in enumerate(fields)}
    code_f = "證券代號" if "證券代號" in idx else "股票代號"
    name_f = "證券名稱" if "證券名稱" in idx else "公司名稱"
    date = pd.Timestamp(os.path.basename(fp)[:8])
    out = []
    for r in rows:
        rec = {"date": date, "stock_id": str(r[idx[code_f]]).strip(), "market": MARKET[src], "src": src}
        name = str(r[idx[name_f]]).strip()
        rec["name"] = name.replace("*", "").strip()
        rec["name_star"] = "*" in name
        for f, c in COLMAP.items():
            if f in idx:
                rec[c] = r[idx[f]]
        out.append(rec)
    df = pd.DataFrame(out)
    for c in ("pe", "dividend_yield", "pbr", "close_ref", "dps"):
        if c in df:
            df[c] = df[c].map(num)
    if "div_year" in df:
        df["div_year"] = pd.to_numeric(df["div_year"], errors="coerce").astype("Int64")
    if "fin_period" in df:
        df["fin_period"] = df["fin_period"].astype(str).str.strip().replace({"": None, "None": None, "-": None})
    return df


def main():
    cal = pd.DatetimeIndex(sorted(pd.to_datetime([x.strip() for x in open(CAL) if x.strip()])))
    os.makedirs(OUT, exist_ok=True)
    frames, cov = [], []
    for src in ("twse_pbr", "tpex_pbr"):
        days = cal[cal >= START[src]]
        me = set(days[np.r_[days.month[1:] != days.month[:-1], True]])
        have = {os.path.basename(p)[:8]: p for p in glob.glob(os.path.join(RAW, "pbr", src, "*.json"))}
        for d in days:
            k = d.strftime("%Y%m%d")
            if k not in have:
                cov.append((d, MARKET[src], "missing", d in me))
                continue
            df = parse(src, have[k])
            if df is None:
                cov.append((d, MARKET[src], "empty", d in me))
            else:
                frames.append(df)
                cov.append((d, MARKET[src], "ok", d in me))
    cv = pd.DataFrame(cov, columns=["date", "market", "status", "month_end"])
    miss = cv[cv.status == "missing"]
    if REQUIRE == "all" and len(miss):
        sys.exit(f"尚有 {len(miss)} 個交易日未取得（REQUIRE=all），停止")
    if REQUIRE == "monthend" and miss.month_end.any():
        sys.exit(f"月底交易日尚有 {int(miss.month_end.sum())} 個未取得，停止")
    v = pd.concat(frames, ignore_index=True)
    cols = ["date", "stock_id", "market", "name", "name_star", "pe", "dividend_yield", "pbr", "fin_period",
            "close_ref", "div_year", "dps", "src"]
    for c in cols:
        if c not in v:
            v[c] = None
    v = v[cols].sort_values(["date", "market", "stock_id"]).reset_index(drop=True)
    dup = v.duplicated(["date", "market", "stock_id"]).sum()
    if dup:
        sys.exit(f"同日同市場重複代號 {dup} 筆，停止")
    v.to_parquet(os.path.join(OUT, "valuation_daily.parquet"), index=False)
    cv.to_parquet(os.path.join(OUT, "valuation_coverage.parquet"), index=False)
    s = cv.groupby(["market", "status"]).size()
    print("REQUIRE", REQUIRE)
    print(s.to_string())
    print("rows", len(v), "date", v.date.min().date(), v.date.max().date(),
          "pbr缺值比例", round(v.pbr.isna().mean(), 4), "name_star", int(v.name_star.sum()))
    cross = v.groupby(["date", "stock_id"]).market.nunique()
    print("同日兩市場皆出現的代號列數（轉市場日）", int((cross > 1).sum()))


if __name__ == "__main__":
    main()
