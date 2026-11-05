"""由 raw/ 建立第一期資料檔（Parquet）與清冊。

輸出（out/）：
- calendar.parquet         官方交易日（FinMind 交易日曆；比對 TWSE 休市表與全市場成交，衝突列入日誌）
- status.parquet           每檔上市／上櫃期間（官方上市櫃日起；下市日止）、verified
- daily_k.parquet          日K（已剔除官方上市櫃日前的興櫃段，A9）、參考價與漲跌停（除權息日用官方值，A10、B6）、跳動旗標
- build_log.json           每個處理步驟的筆數、排除原因與衝突
- manifest.json            每個輸出檔的筆數、sha256、來源與 raw 包雜湊
缺值不推估：查無官方上市櫃日的代號不刪資料，但 status.verified=False，母體預設排除（A9）。
"""
from __future__ import annotations

import glob
import gzip
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework.elon_tools import limit_prices  # noqa: E402
from data_layer import corp_actions  # noqa: E402
from data_layer import market_history as mh  # noqa: E402
from data_layer import calendar_check  # noqa: E402

RAW = os.environ.get("RAW_DIR", "raw")
OUT = os.environ.get("OUT_DIR", "out")
LOG: dict = {}


def jl(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def roc(s: str) -> str:
    """'113/07/01' 或 '113年07月01日' → '2024-07-01'"""
    n = re.findall(r"\d+", s)
    return f"{int(n[0]) + 1911:04d}-{int(n[1]):02d}-{int(n[2]):02d}"


def parse_date(s):
    """'19620209'、'1150101'（民國）、'2024-07-01'、'115/01/01' → ISO；無法判讀回 None。"""
    if not s:
        return None
    s = str(s).strip()
    if "-" in s:
        return s[:10]
    if "/" in s or "年" in s:
        return roc(s)
    if s.isdigit() and len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if s.isdigit() and len(s) == 7:
        return f"{int(s[:3]) + 1911}-{s[3:5]}-{s[5:]}"
    return None


def num(x):
    try:
        v = float(str(x).replace(",", "").strip())
        return v
    except ValueError:
        return None


# ------------------------------------------------------------------ 日曆
def build_calendar(prices: pd.DataFrame) -> pd.DataFrame:
    fm = pd.to_datetime([x["date"] for x in jl(f"{RAW}/finmind/TaiwanStockTradingDate/_all.json.gz")["data"]])
    today = pd.Timestamp(date.today())
    cal = pd.DataFrame({"date": fm[fm <= today]})
    traded = set(prices.loc[prices["volume"] > 0, "date"].unique())
    no_trade = cal.loc[~cal["date"].isin(traded), "date"]
    LOG["calendar"] = {"finmind_days_to_today": len(cal), "days_without_any_trade": [d.strftime("%Y-%m-%d") for d in no_trade]}
    extra = sorted(d for d in traded if d not in set(cal["date"]) and d >= cal["date"].min())
    LOG["calendar"]["trade_days_missing_in_calendar"] = [d.strftime("%Y-%m-%d") for d in extra]
    cal = cal[~cal["date"].isin(no_trade)].reset_index(drop=True)
    cal["source"] = "FinMind TaiwanStockTradingDate；剔除全市場無成交日"
    return cal


# ------------------------------------------------------------------ 市場別
def build_status() -> pd.DataFrame:
    rows = []
    twse = json.load(open(f"{RAW}/official/twse_t187ap03_L.json", encoding="utf-8"))
    for x in twse:
        rows.append(dict(stock_id=x["公司代號"].strip(), status="上市", start=x["上市日期"], src="TWSE t187ap03_L"))
    p = f"{RAW}/official/tpex_t187ap03_O.json"
    if os.path.exists(p):
        for x in json.load(open(p, encoding="utf-8")):
            sd = x.get("DateOfListing") or x.get("上櫃日期")
            if sd:
                rows.append(dict(stock_id=x["SecuritiesCompanyCode"].strip(), status="上櫃", start=sd, src="TPEx t187ap03_O"))
    else:
        LOG.setdefault("status", {})["tpex_listing_file"] = "缺：上櫃日期待下次下載"
    info = jl(f"{RAW}/finmind/TaiwanStockInfo/_all.json.gz")["data"]
    mk = {}
    for x in info:
        if x["type"] in ("twse", "tpex"):
            mk[x["stock_id"]] = "上市" if x["type"] == "twse" else "上櫃"
    dl = {x["stock_id"]: x["date"] for x in jl(f"{RAW}/finmind/TaiwanStockDelisting/_all.json.gz")["data"]}
    known = {r["stock_id"] for r in rows}
    for sid, d in dl.items():
        if sid not in known:
            rows.append(dict(stock_id=sid, status=mk.get(sid, "上市或上櫃未定"), start=None, src="FinMind Delisting（無官方上市櫃日）"))
    for sid, m in mk.items():
        if sid not in known and sid not in dl:
            rows.append(dict(stock_id=sid, status=m, start=None, src="FinMind StockInfo（無官方上市櫃日）"))
    st = pd.DataFrame(rows)
    st["start_date"] = pd.to_datetime(st["start"].map(parse_date), errors="coerce")
    st["end_date"] = pd.to_datetime(st["stock_id"].map(dl), errors="coerce")
    st["verified"] = st["start_date"].notna()
    st = st.drop(columns=["start"]).drop_duplicates("stock_id")
    LOG.setdefault("status", {}).update(rows=len(st), verified=int(st["verified"].sum()), unverified=int((~st["verified"]).sum()))
    return st


# ------------------------------------------------------------------ 官方除權息
def official_exright() -> pd.DataFrame:
    """依欄位名稱取值（各年度欄位順序不同）。"""
    rows, empty = [], []
    pick = {"date": ("資料日期", "除權息日期", "除權除息交易日"), "stock_id": ("股票代號", "代號"), "prev_close": ("除權息前收盤價",),
            "ref": ("除權息參考價", "除權參考價"), "limit_up": ("漲停價格", "漲停價"), "limit_down": ("跌停價格", "跌停價"),
            "kind": ("權/息",), "cash": ("現金股利",), "stock_per_k": ("每仟股無償配股",),
            "wv": ("權值+息值",), "rights_sh": ("現金增資股數",)}
    def take(fields, r):
        out = {}
        for k, names in pick.items():
            idx = next((fields.index(n) for n in names if n in fields), None)
            out[k] = r[idx] if idx is not None else None
        return out
    # 退回-67：櫃買改用年度官方表（2000-09 起；2007 以前為舊版歷史表，只有參考價與漲跌停），
    # 舊的逐月檔有 96 個月是伺服器回傳「當日」資料，不再使用。每列日期須落在檔案查詢區間內，否則剔除並記錄。
    bad_rows = {}
    for pat, src in ((f"{RAW}/official/twse_twt49u/*.json", "TWSE TWT49U"), (f"{RAW}/market/tpex_exright/*.json", "TPEx 除權除息計算結果")):
        for f in sorted(glob.glob(pat)):
            j = json.load(open(f, encoding="utf-8"))
            stem = os.path.basename(f)[:-5]
            lo, hi = (pd.Timestamp(f"{stem[:4]}-{stem[4:6]}-01"), pd.Timestamp(f"{stem[:4]}-{stem[4:6]}-01") + pd.offsets.MonthEnd(0)) \
                if len(stem) == 6 else (pd.Timestamp(f"{stem}-01-01"), pd.Timestamp(f"{stem}-12-31"))
            tables = j.get("tables") or [{"fields": j.get("fields") or [], "data": j.get("data") or []}]
            n = 0
            for t in tables:
                fl = list(t.get("fields") or [])
                for r in t.get("data") or []:
                    x = take(fl, r)
                    dd = pd.Timestamp(roc(x["date"]))
                    if not (lo <= dd <= hi):
                        bad_rows[stem] = bad_rows.get(stem, 0) + 1
                        continue
                    rows.append(dict(date=roc(x["date"]), stock_id=str(x["stock_id"]).strip(), prev_close=num(x["prev_close"]),
                                     ref=num(x["ref"]), limit_up=num(x["limit_up"]), limit_down=num(x["limit_down"]),
                                     kind=str(x["kind"] or "").strip(), cash=num(x["cash"]) if x["cash"] is not None else None,
                                     stock_per_k=num(x["stock_per_k"]) if x["stock_per_k"] is not None else None,
                                     wv=num(x["wv"]) if x["wv"] is not None else None,
                                     rights_sh=num(x["rights_sh"]) if x["rights_sh"] is not None else None, src=src))
                    n += 1
            if n == 0:
                empty.append(os.path.basename(os.path.dirname(f)) + "/" + os.path.basename(f))
    ex = pd.DataFrame(rows)
    ex["date"] = pd.to_datetime(ex["date"])
    ex = ex.drop_duplicates(["date", "stock_id", "src"])
    LOG["exright"] = {"rows": len(ex), "by_src": ex["src"].value_counts().to_dict(), "empty_files": empty,
                      "rows_outside_query_range_dropped": bad_rows,
                      "coverage": {"TWSE TWT49U": "2003-05-05 起（官方說明）", "TPEx": "2000-09-01 起（2000-09～2007-12 歷史表、2008 起計算結果表）"}}
    return ex


# ------------------------------------------------------------------ 日K
def load_prices() -> pd.DataFrame:
    frames = []
    for f in glob.glob(f"{RAW}/finmind/TaiwanStockPrice/*.json.gz"):
        d = jl(f).get("data", [])
        if d:
            frames.append(pd.DataFrame(d))
    px = pd.concat(frames, ignore_index=True)
    px = px.rename(columns={"max": "high", "min": "low", "Trading_Volume": "volume", "Trading_money": "amount"})
    px["date"] = pd.to_datetime(px["date"])
    px["stock_id"] = px["stock_id"].astype(str)
    return px[["date", "stock_id", "open", "high", "low", "close", "volume", "amount"]].sort_values(["stock_id", "date"])


def split_by_market(px: pd.DataFrame, st: pd.DataFrame, cal: pd.DataFrame):
    """退回-67（A1）：逐列判定當日是否在官方上市或上櫃。回傳 (主日K, 隔離列, 市場區段, 前五日無限幅表)。

    - 在現行官方掛牌日以後（已驗證）→ 主日K，market＝現行市場。
    - 否則查官方逐日市場別：有 → 主日K（含轉上市前的合法上櫃期間）；沒有 → 隔離。
      隔離原因分「官方查無（興櫃、未掛牌或已下市）」與「官方檔缺漏（未取得，不判定）」。
    """
    stv = st.set_index("stock_id")
    cur_start = px["stock_id"].map(stv["start_date"])
    cur_mkt = px["stock_id"].map(stv["status"])
    ver = px["stock_id"].map(stv["verified"]).fillna(False).astype(bool)
    in_cur = ver & (px["date"] >= cur_start)
    seg = mh.segments(list(cal["date"]), LOG)
    ev = mh.listing_events(seg, st)
    px = px.reset_index(drop=True)
    in_cur = in_cur.reset_index(drop=True)
    cur_mkt = cur_mkt.reset_index(drop=True)
    px["mkt_off"] = None
    nc = ~in_cur.values
    px.loc[nc, "mkt_off"] = mh.lookup(px.loc[nc, ["stock_id", "date"]], seg).values
    px["market"] = cur_mkt.where(in_cur.values, None).values
    px.loc[px["market"].isna(), "market"] = px.loc[px["market"].isna(), "mkt_off"]
    px["market_src"] = "現行官方掛牌期間"
    px.loc[~in_cur.values, "market_src"] = "官方逐日市場別"
    q = px["market"].isna()
    cov = mh.coverage()
    qx = px[q].copy()
    qx["quarantine_reason"] = [mh.quarantine_reason(sid, d, cov) for sid, d in zip(qx["stock_id"], qx["date"])]
    main = px[~q].drop(columns=["mkt_off"]).copy()
    nl = mh.first5_no_limit(ev[ev["stock_id"].isin(set(px["stock_id"]))], list(cal["date"]))
    LOG["market_split"] = {"raw_rows": len(px), "main_rows": len(main), "quarantine_rows": len(qx),
                           "quarantine_by_reason": qx["quarantine_reason"].value_counts().to_dict(),
                           "quarantine_stocks": int(qx["stock_id"].nunique()),
                           "rows_restored_outside_current_listing": int((~in_cur.values & ~q.values).sum()),
                           "stocks_with_restored_rows": int(px.loc[~in_cur.values & ~q.values, "stock_id"].nunique()),
                           "transfers": int((~ev["initial"]).sum()) if len(ev) else 0,
                           "first5_rows_by_status": nl["no_limit_status"].value_counts().to_dict() if len(nl) else {}}
    LOG["market_split"]["segments_file"] = "market_segments.parquet（官方逐日區段）"
    return main, qx.drop(columns=["mkt_off"]), seg.merge(ev[["stock_id", "start", "initial"]], on=["stock_id", "start"], how="left"), nl


def build_daily(px: pd.DataFrame, ex: pd.DataFrame, ca: pd.DataFrame | None = None, nl: pd.DataFrame | None = None) -> pd.DataFrame:
    LOG["daily_k"] = {"rows_in": len(px)}
    # FinMind 無成交日以 0 價列出：標 no_trade、OHLC 改為空值，前收取前一個有成交日的收盤
    px["no_trade"] = (px["volume"].fillna(0) <= 0) | (px["close"].fillna(0) <= 0)
    for c in ("open", "high", "low", "close"):
        px.loc[px["no_trade"], c] = None
    LOG["daily_k"]["no_trade_rows"] = int(px["no_trade"].sum())
    # 前收只在同一段連續掛牌期間內取（跨隔離列以前一個主日K收盤為準；轉板不中斷）
    px["prev_close"] = px.groupby("stock_id")["close"].transform(lambda c: c.ffill().shift(1))
    px = px.merge(ex[["date", "stock_id", "ref", "limit_up", "limit_down"]].drop_duplicates(["date", "stock_id"]).rename(
        columns={"ref": "ref_off", "limit_up": "up_off", "limit_down": "dn_off"}), on=["date", "stock_id"], how="left")
    if nl is not None and len(nl):
        px = px.merge(nl, on=["stock_id", "date"], how="left")
    else:
        px["no_limit_status"], px["no_limit_src"] = None, None
    px["ref_price"] = px["ref_off"].where(px["ref_off"].notna(), px["prev_close"])
    # limit_status：官方除權息表／規則／無漲跌幅（初次掛牌前五日）／待查（過渡期）／缺參考價 —— 無限幅與缺限價分開
    px["limit_src"] = "規則"
    px.loc[px["up_off"].notna(), "limit_src"] = "官方除權息表"
    ups, dns = [], []
    for r, d, uo, do in zip(px["ref_price"], px["date"], px["up_off"], px["dn_off"]):
        if pd.notna(uo):
            ups.append(uo); dns.append(do)
        elif pd.isna(r) or r <= 0:
            ups.append(None); dns.append(None)
        else:
            u, dn = limit_prices(r, d)
            ups.append(u); dns.append(dn)
    px["limit_up"], px["limit_down"] = ups, dns
    nolim = px["no_limit_status"].notna()
    px.loc[nolim, ["limit_up", "limit_down"]] = None
    px.loc[nolim, "limit_src"] = px.loc[nolim, "no_limit_status"].map(lambda x: "無漲跌幅（初次掛牌前五日）" if x == "無漲跌幅" else "待查（過渡期初次掛牌前五日）")
    px.loc[~nolim & px["limit_up"].isna() & ~px["no_trade"], "limit_src"] = "缺參考價"
    # 跳動掃描：收盤超出漲跌停且「前一成交日之後到當日（含）」查無公司行動（含休市日除權息）；無限幅與待查日不判
    px["prev_date"] = px["date"].where(~px["no_trade"]).groupby(px["stock_id"]).transform(lambda c: c.ffill().shift(1))
    exk = ex[["stock_id", "date"]].copy()
    if ca is not None and len(ca):
        exk = pd.concat([exk, ca[["stock_id", "ex_date"]].rename(columns={"ex_date": "date"})], ignore_index=True)
    tol = 1e-9
    out_of_band = ~px["no_trade"] & ~nolim & px["prev_close"].notna() & px["limit_up"].notna() & \
        ((px["close"] > px["limit_up"] + tol) | (px["close"] < px["limit_down"] - tol))
    cand = px[out_of_band][["stock_id", "date", "prev_date"]]
    mm = cand.merge(exk.rename(columns={"date": "ex_date"}), on="stock_id", how="left")
    has_act = mm[(mm["ex_date"] > mm["prev_date"]) & (mm["ex_date"] <= mm["date"])][["stock_id", "date"]].drop_duplicates()
    has_act["has_action"] = True
    cand = cand.merge(has_act, on=["stock_id", "date"], how="left")
    jumps = cand[cand["has_action"].isna()][["stock_id", "date"]]
    jumps["jump_flag"] = True
    px = px.merge(jumps, on=["stock_id", "date"], how="left")
    px["jump_flag"] = px["jump_flag"].fillna(False).astype(bool)
    px["jump_reason"] = px["jump_flag"].map({True: "超出漲跌停且查無公司行動", False: None})
    LOG["daily_k"].update(rows=len(px), official_limit_rows=int((px["limit_src"] == "官方除權息表").sum()),
                          limit_src=px["limit_src"].value_counts().to_dict(), jump_rows=int(px["jump_flag"].sum()))
    return px.drop(columns=["ref_off", "up_off", "dn_off", "prev_date"])


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    os.makedirs(OUT, exist_ok=True)
    px = load_prices()
    st = build_status()
    ex = official_exright()
    cal = build_calendar(px)
    ca = corp_actions.build(ex, LOG)
    main, qx, ev, nl = split_by_market(px, st, cal)
    dk = build_daily(main, ex, ca, nl)
    dk["stock_id"] = dk["stock_id"].astype(str)
    files = {"calendar.parquet": cal, "status.parquet": st, "daily_k.parquet": dk, "official_exright.parquet": ex,
             "corp_actions.parquet": ca, "daily_k_quarantine.parquet": qx, "market_segments.parquet": ev,
             "calendar_check.parquet": calendar_check.check(cal, LOG)}
    man = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "raw_dir": RAW, "files": {}}
    for name, df in files.items():
        p = os.path.join(OUT, name)
        df.to_parquet(p, index=False)
        man["files"][name] = {"rows": len(df), "sha256": sha(p)}
    status_p = os.path.join(RAW, "_status_finmind.json")
    man["finmind_status"] = json.load(open(status_p)) if os.path.exists(status_p) else None
    json.dump(LOG, open(os.path.join(OUT, "build_log.json"), "w"), ensure_ascii=False, indent=1, default=str)
    json.dump(man, open(os.path.join(OUT, "manifest.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(man, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
