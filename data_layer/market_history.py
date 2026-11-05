"""逐日市場別（退回-67：A1 歷史市場別、初次掛牌前五日無漲跌幅）。

來源（全部官方原始檔，fetch_market.py 下載、核對回傳日期後才存檔）：
- 櫃買每日收盤行情（2007-07 起逐交易日）：當日表內代號＝當日上櫃。
- 櫃買個股月成交（2007-07 以前，只抓 FinMind 有行情但不在現行官方掛牌期間內的股票月份）。
- 證交所每日收盤行情 MI_INDEX（2004-02-11 起逐交易日）：當日表內代號＝當日上市。
- 證交所個股月成交 STOCK_DAY（2004-02 以前，同上只抓需要的股票月份）。
- 現行官方掛牌日（TWSE t187ap03_L、TPEx t187ap03_O）以後的期間：現行市場。

判定：
- FinMind 日K列若當日在上市或上櫃官方資料內 → 保留，market 欄記市場。
- 不在任何官方資料內（興櫃、掛牌前、或官方查無）→ 移出主日K，放隔離檔 daily_k_quarantine。
- 初次掛牌日＝該股第一個官方上市或上櫃日；之後換市場（上櫃轉上市、上市轉上櫃）是轉板，不是初次掛牌。
- 初次掛牌前五個交易日無漲跌幅：證交所自 2005-03-01 起（官方說明 introduce001.pdf：初次上市普通股，
  不含上櫃轉上市）；櫃買適用同一承銷新制，生效日以官方資料核對後寫入 NO_LIMIT_START。
  只適用普通股；ETF、受益憑證等非普通股不適用（代號以 0 開頭者視為非普通股）。
"""
from __future__ import annotations

import glob
import json
import os
import re

import pandas as pd

RAW = os.environ.get("RAW_DIR", "raw")
MK = os.path.join(RAW, "market")
NO_LIMIT_START = {"上市": pd.Timestamp("2005-03-01"), "上櫃": pd.Timestamp("2005-03-01")}
# 承銷新制過渡期：櫃買 100 年公告仍逐案註明「本案採用承銷新制…掛牌首五日無漲跌幅」，表示制度生效後
# 仍可能有個案適用舊制。過渡期內的初次掛牌前五日標「待查」：不套漲跌停、不判跳動，但不視為已證實無限幅。
TRANSITION_END = pd.Timestamp("2006-12-31")
NO_LIMIT_SRC = {"上市": "TWSE introduce001.pdf（94-03-01 實施；初次上市普通股，不含上櫃轉上市）",
                "上櫃": "同一承銷新制（櫃買業務規則第55條；上市轉上櫃與管理股票除外）"}


def _roc(s):
    n = re.findall(r"\d+", str(s))
    return pd.Timestamp(f"{int(n[0]) + 1911:04d}-{int(n[1]):02d}-{int(n[2]):02d}")


def _code(x):
    return str(x).strip().split()[0] if str(x).strip() else ""


def _iter_days():
    """逐檔串流官方逐日／逐月檔，產生 (stock_id, date字串, market, src)。不整批載入以控制記憶體。"""
    for f in glob.glob(f"{MK}/tpex_daily/*/*.json"):
        t = (json.load(open(f, encoding="utf-8")).get("tables") or [{}])[0]
        d = str(_roc(t["date"]).date())
        for r in t.get("data") or []:
            if r:
                yield _code(r[0]), d, "上櫃", "TPEx 每日收盤行情"
    for f in glob.glob(f"{MK}/tpex_stock/*/*.json"):
        sid = os.path.basename(os.path.dirname(f))
        t = (json.load(open(f, encoding="utf-8")).get("tables") or [{}])[0]
        for r in t.get("data") or []:
            yield sid, str(_roc(r[0].replace("*", "")).date()), "上櫃", "TPEx 個股月成交"
    for f in glob.glob(f"{MK}/twse_daily/*/*.json"):
        j = json.load(open(f, encoding="utf-8"))
        if str(j.get("stat", "")) != "OK":
            continue
        d = f"{j['date'][:4]}-{j['date'][4:6]}-{j['date'][6:]}"
        for t in j.get("tables") or []:
            fl = [x.strip() for x in t.get("fields") or []]
            if "證券代號" in fl and "收盤價" in fl:
                i = fl.index("證券代號")
                for r in t.get("data") or []:
                    yield _code(r[i]), d, "上市", "TWSE MI_INDEX"


def segments(cal_days, log: dict) -> pd.DataFrame:
    """官方逐日市場別壓成區段：同股同市場、市場交易日連續者合併。回傳 (stock_id, market, start, end, days, src)。"""
    idx = {str(pd.Timestamp(d).date()): i for i, d in enumerate(sorted(cal_days))}
    days = sorted(cal_days)
    acc, srcs, off_cal = {}, {}, 0
    for sid, d, mkt, src in _iter_days():
        i = idx.get(d)
        if i is None:
            off_cal += 1
            continue
        acc.setdefault((sid, mkt), set()).add(i)
        srcs.setdefault((sid, mkt), set()).add(src)
    rows = []
    for (sid, mkt), ii in acc.items():
        ii = sorted(ii)
        st = pv = ii[0]
        for x in ii[1:] + [None]:
            if x is not None and x == pv + 1:
                pv = x
                continue
            rows.append((sid, mkt, pd.Timestamp(days[st]), pd.Timestamp(days[pv]), pv - st + 1, "、".join(sorted(srcs[(sid, mkt)]))))
            if x is not None:
                st = pv = x
    seg = pd.DataFrame(rows, columns=["stock_id", "market", "start", "end", "days", "src"])
    log["market_history"] = {"segments": len(seg), "stocks": int(seg["stock_id"].nunique()),
                             "stock_days": int(seg["days"].sum()), "official_dates_not_in_calendar": off_cal}
    return seg


def lookup(px: pd.DataFrame, seg: pd.DataFrame) -> pd.Series:
    """px 每列（stock_id, date）在官方區段內的市場；不在任何區段回傳 None。"""
    out = pd.Series([None] * len(px), index=px.index, dtype=object)
    sg = seg.sort_values("start")
    for sid, g in px.groupby("stock_id"):
        s = sg[sg["stock_id"] == sid]
        if s.empty:
            continue
        st, en, mk = s["start"].values, s["end"].values, s["market"].values
        dv = g["date"].values
        pos = st.searchsorted(dv, side="right") - 1
        ok = (pos >= 0)
        pos2 = pos.clip(0)
        hit = ok & (dv <= en[pos2])
        out.loc[g.index[hit]] = mk[pos2[hit]]
    return out


def listing_events(seg: pd.DataFrame, st: pd.DataFrame) -> pd.DataFrame:
    """每檔股票的市場區段起點：初次掛牌（最早一段）與轉板（市場改變）。現行官方掛牌日一併納入。"""
    cur = st[st["verified"]][["stock_id", "status", "start_date"]].rename(columns={"status": "market", "start_date": "start"})
    ev = pd.concat([seg[["stock_id", "market", "start"]], cur], ignore_index=True).sort_values(["stock_id", "start"])
    out = []
    for sid, g in ev.groupby("stock_id"):
        g = g[g["market"].ne(g["market"].shift())]
        for i, (_, r) in enumerate(g.iterrows()):
            out.append(dict(stock_id=sid, start=r["start"], market=r["market"], initial=(i == 0)))
    return pd.DataFrame(out, columns=["stock_id", "start", "market", "initial"])


def first5_no_limit(ev: pd.DataFrame, cal_days: list) -> pd.DataFrame:
    """初次掛牌（非轉板）普通股、制度生效後：掛牌日起 5 個交易日無漲跌幅。回傳 (stock_id, date, no_limit_src)。"""
    idx = pd.DatetimeIndex(sorted(cal_days))
    rows = []
    for _, r in ev[ev["initial"]].iterrows():
        if str(r["stock_id"]).startswith("0"):
            continue
        if r["start"] < NO_LIMIT_START[r["market"]]:
            continue
        p = idx.searchsorted(r["start"])
        status = "待查（承銷新制過渡期，個案是否適用未逐案核對）" if r["start"] <= TRANSITION_END else "無漲跌幅"
        for d in idx[p:p + 5]:
            rows.append((r["stock_id"], d, status, f"初次{r['market']}前五日；{NO_LIMIT_SRC[r['market']]}"))
    return pd.DataFrame(rows, columns=["stock_id", "date", "no_limit_status", "no_limit_src"])


def coverage():
    """已取得（且回傳日期核對通過）的官方檔範圍，用來區分「官方查無」與「官方檔缺漏」。"""
    def days(sub):
        return {pd.Timestamp(os.path.basename(f)[:10]) for f in glob.glob(f"{MK}/{sub}/*/*.json")}

    def sm(sub):
        return {(os.path.basename(os.path.dirname(f)), os.path.basename(f)[:7]) for f in glob.glob(f"{MK}/{sub}/*/*.json")}
    return {"tpex_daily": days("tpex_daily"), "twse_daily": days("twse_daily"),
            "tpex_sm": sm("tpex_stock"), "twse_sm": sm("twse_stock")}


TPEX_DAILY_FROM = pd.Timestamp("2007-07-01")
TWSE_DAILY_FROM = pd.Timestamp("2004-02-11")


def quarantine_reason(sid: str, d: pd.Timestamp, cov: dict) -> str:
    """不在官方上市／上櫃逐日資料的列，說明為何不在：查過兩市場都沒有，或某一市場無官方逐日來源／檔案缺漏。"""
    ym = d.strftime("%Y-%m")
    tp = d in cov["tpex_daily"] if d >= TPEX_DAILY_FROM else (sid, ym) in cov["tpex_sm"]
    if d < TWSE_DAILY_FROM:
        return "證交所 2004-02-11 前無官方逐日資料（櫃買" + ("已查無" if tp else "檔缺漏") + "）；上市身分未證實"
    tw = d in cov["twse_daily"]
    if tp and tw:
        return "官方查無（興櫃、未掛牌或已下市）"
    return "官方檔缺漏（未取得，不判定）"
