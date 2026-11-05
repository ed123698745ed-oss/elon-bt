"""交易日曆官方比對（退回-67：「只吃官方日曆」須有官方證據，與「FinMind 與成交比對」分開列）。

官方交易日來源：
- 2004-02-11 起：證交所每日收盤行情 MI_INDEX 有資料（stat=OK）的日期。
- 1999-01～2004-02：證交所個股月成交 STOCK_DAY（1101 台泥全月）出現的日期。
- 2007-07 起另以櫃買每日收盤行情交叉核對。
輸出 calendar_check.csv：每個日期的 FinMind 日曆、證交所官方、櫃買官方三欄與判定。
"""
import glob, json, os, re
import pandas as pd

RAW = os.environ.get("RAW_DIR", "raw")
MK = os.path.join(RAW, "market")


def official_days():
    tw, twq, tp = set(), set(), set()
    for f in glob.glob(f"{MK}/twse_daily/*/*.json"):
        d = pd.Timestamp(os.path.basename(f)[:10]); twq.add(d)
        if json.load(open(f, encoding="utf-8")).get("stat") == "OK":
            tw.add(d)
    for f in glob.glob(f"{MK}/twse_stock/1101/*.json"):
        j = json.load(open(f, encoding="utf-8"))
        for r in j.get("data") or []:
            n = re.findall(r"\d+", r[0]); tw.add(pd.Timestamp(int(n[0]) + 1911, int(n[1]), int(n[2])))
    for f in glob.glob(f"{MK}/tpex_daily/*/*.json"):
        t = (json.load(open(f, encoding="utf-8")).get("tables") or [{}])[0]
        if t.get("data"):
            tp.add(pd.Timestamp(os.path.basename(f)[:10]))
    return tw, twq, tp


def check(cal: pd.DataFrame, log: dict) -> pd.DataFrame:
    tw, twq, tp = official_days()
    sm1101 = {os.path.basename(f)[:7] for f in glob.glob(f"{MK}/twse_stock/1101/*.json")}
    c = set(pd.to_datetime(cal["date"]))
    lo = min(tw) if tw else None
    days = sorted(c | {d for d in tw if lo is not None})
    rows = []
    for d in days:
        in_c, in_tw = d in c, d in tw
        tw_known = (d >= pd.Timestamp("2004-02-11") and d in twq) or (d < pd.Timestamp("2004-02-11") and d.strftime("%Y-%m") in sm1101)
        tp_known = d >= pd.Timestamp("2007-07-01")
        verdict = ("一致" if in_c == in_tw else ("日曆多出（官方無行情）" if in_c else "日曆缺少（官方有行情）")) if tw_known else "官方未取得"
        rows.append(dict(date=d, finmind_calendar=in_c, twse_official=in_tw if tw_known else None,
                         tpex_official=(d in tp) if tp_known else None, verdict=verdict))
    out = pd.DataFrame(rows)
    log["calendar_official_check"] = out["verdict"].value_counts().to_dict() | {
        "examples_not_matching": out[out["verdict"].str.startswith("日曆")].head(20).astype(str).to_dict("records")}
    return out
