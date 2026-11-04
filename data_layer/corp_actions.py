"""公司行動事件表（A2）：固定股數＋實得現金所需的每筆行動。

來源與口徑：
- 現金股利／配股：FinMind TaiwanStockDividend（公告值）。現金＝盈餘配息＋公積配息；
  配股股數＝(盈餘配股＋公積配股)÷面額（面額取 10 元，非 10 元面額者以官方參考價核對發現並標記）。
  同一除權息日有多筆公告時，取除權息日前最後一筆公告（不用事後更正值，A3）。
- 減資：FinMind TaiwanStockCapitalReductionReferencePrice。
  ・彌補虧損減資（無退還現金）：換股比＝停止買賣前收盤÷恢復買賣參考價（官方兩個價格相除），標「由官方參考價反推」；
  ・其他原因（可能有退還現金）：換股比與退還現金拆不開，列「資料不足」，不推估（A5）。
- 面額變更（分割）：FinMind TaiwanStockSplitPrice，換股比＝變更前價÷變更後參考價。
- 核對：與官方除權息表（TWT49U／TPEx）比對，用 (前收−現金)÷(1＋配股比) 應等於官方參考價，差異 >0.5% 標記。
配股可賣日：來源沒有，sellable_date 留空並標記（報告須逐筆揭露）。
"""
from __future__ import annotations

import glob
import gzip
import json
import os

import pandas as pd

RAW = os.environ.get("RAW_DIR", "raw")


def _jl(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def dividends() -> pd.DataFrame:
    rows = []
    for p in glob.glob(f"{RAW}/finmind/TaiwanStockDividend/*.json.gz"):
        for r in _jl(p).get("data", []):
            cash = _f(r.get("CashEarningsDistribution")) + _f(r.get("CashStatutorySurplus"))
            stk = _f(r.get("StockEarningsDistribution")) + _f(r.get("StockStatutorySurplus"))
            ann = (r.get("AnnouncementDate") or "") + " " + (r.get("AnnouncementTime") or "")
            if cash > 0 and r.get("CashExDividendTradingDate"):
                rows.append(dict(stock_id=r["stock_id"], ex_date=r["CashExDividendTradingDate"], kind="現金股利",
                                 cash=cash, share_ratio=1.0, cash_date=r.get("CashDividendPaymentDate") or None,
                                 announced=ann.strip(), source="FinMind TaiwanStockDividend", flag=None))
            if stk > 0 and r.get("StockExDividendTradingDate"):
                rows.append(dict(stock_id=r["stock_id"], ex_date=r["StockExDividendTradingDate"], kind="配股",
                                 cash=0.0, share_ratio=1 + stk / 10.0, cash_date=None, announced=ann.strip(),
                                 source="FinMind TaiwanStockDividend（面額10元）", flag="配股可賣日資料不足"))
    d = pd.DataFrame(rows)
    if d.empty:
        return d
    d["ex_date"] = pd.to_datetime(d["ex_date"], errors="coerce")
    d = d.dropna(subset=["ex_date"])
    d["ann_dt"] = pd.to_datetime(d["announced"].str[:10], errors="coerce")
    n0 = len(d)
    d = d[(d["ann_dt"].isna()) | (d["ann_dt"] <= d["ex_date"])]
    d = d.sort_values("announced").groupby(["stock_id", "ex_date", "kind"], as_index=False).last()
    d.attrs["dropped_post_ex_or_dup"] = n0 - len(d)
    return d.drop(columns=["ann_dt"])


def reductions() -> pd.DataFrame:
    rows = []
    for p in glob.glob(f"{RAW}/finmind/TaiwanStockCapitalReductionReferencePrice/*.json.gz"):
        for r in _jl(p).get("data", []):
            last, post = _f(r.get("ClosingPriceonTheLastTradingDay")), _f(r.get("PostReductionReferencePrice"))
            reason = r.get("ReasonforCapitalReduction") or ""
            losses = "loss" in reason.lower()
            ok = losses and last > 0 and post > 0
            rows.append(dict(stock_id=r["stock_id"], ex_date=r["date"], kind="減資",
                             cash=0.0 if ok else None, share_ratio=(last / post) if ok else None, cash_date=None,
                             announced=None, source="FinMind CapitalReductionReferencePrice",
                             flag=("由官方參考價反推（彌補虧損、無退還現金）" if ok else f"資料不足：{reason or '原因未載'}，換股比與退還現金待官方資料"),
                             reduction_reason=reason))
    d = pd.DataFrame(rows)
    if not d.empty:
        d["ex_date"] = pd.to_datetime(d["ex_date"])
    return d


def splits() -> pd.DataFrame:
    p = f"{RAW}/finmind/TaiwanStockSplitPrice/_all.json.gz"
    rows = []
    for r in _jl(p).get("data", []) if os.path.exists(p) else []:
        b, a = _f(r.get("before_price")), _f(r.get("after_price"))
        rows.append(dict(stock_id=r["stock_id"], ex_date=r["date"], kind="面額變更", cash=0.0,
                         share_ratio=(b / a) if a else None, cash_date=None, announced=None,
                         source="FinMind TaiwanStockSplitPrice", flag=None if a else "資料不足"))
    d = pd.DataFrame(rows)
    if not d.empty:
        d["ex_date"] = pd.to_datetime(d["ex_date"])
    return d


def build(official_ex: pd.DataFrame, log: dict) -> pd.DataFrame:
    dv, rd, sp = dividends(), reductions(), splits()
    ca = pd.concat([dv, rd, sp], ignore_index=True)
    ca["stock_id"] = ca["stock_id"].astype(str)
    # 與官方除權息表核對：同日現金與配股合併後，(前收−現金)/(配股比) 應≈官方參考價
    agg = (dv.assign(stock_id=dv["stock_id"].astype(str)).groupby(["stock_id", "ex_date"])
             .agg(cash=("cash", "sum"), ratio=("share_ratio", "prod")).reset_index())
    m = official_ex.drop(columns=[c for c in ("cash", "stock_per_k") if c in official_ex]).merge(agg, left_on=["stock_id", "date"], right_on=["stock_id", "ex_date"], how="left")
    m["calc_ref"] = (m["prev_close"] - m["cash"]) / m["ratio"]
    m["rel_diff"] = (m["calc_ref"] / m["ref"] - 1).abs()
    bad = m[m["rel_diff"] > 0.005]
    miss = m[m["cash"].isna()]
    log["corp_actions"] = {
        "rows": len(ca), "by_kind": ca["kind"].value_counts().to_dict(),
        "dividend_dropped_post_ex_or_dup": int(dv.attrs.get("dropped_post_ex_or_dup", 0)),
        "reduction_data_insufficient": int(rd["share_ratio"].isna().sum()) if not rd.empty else 0,
        "official_exright_rows": len(official_ex),
        "official_without_finmind_dividend": len(miss),
        "official_mismatch_gt_0.5pct": len(bad),
        "mismatch_examples": bad[["stock_id", "date", "prev_close", "ref", "cash", "ratio", "calc_ref"]]
        .head(20).astype(str).to_dict("records"),
    }
    # 官方除權息表有、FinMind 股利政策沒有的事件：用官方值補，不能拆分者列資料不足
    fill = []
    for r in miss.itertuples():
        base = dict(stock_id=r.stock_id, ex_date=r.date, cash_date=None, announced=None)
        o = official_ex[(official_ex["stock_id"] == r.stock_id) & (official_ex["date"] == r.date)].iloc[0]
        if o["src"].startswith("TPEx"):
            c, k, rs = (o.get("cash") or 0.0), (o.get("stock_per_k") or 0.0), (o.get("rights_sh") or 0.0)
            if c > 0:
                fill.append(dict(base, kind="現金股利", cash=c, share_ratio=1.0, source="TPEx 除權除息計算結果", flag=None))
            if k > 0:
                fill.append(dict(base, kind="配股", cash=0.0, share_ratio=1 + k / 1000.0, source="TPEx 除權除息計算結果",
                                 flag="配股可賣日資料不足"))
            if rs > 0:
                fill.append(dict(base, kind="現增除權", cash=0.0, share_ratio=1.0, source="TPEx 除權除息計算結果",
                                 flag="現增認購權，依策略卡另算"))
            if c <= 0 and k <= 0 and rs <= 0:
                fill.append(dict(base, kind="除權息未分類", cash=None, share_ratio=None, source="TPEx 除權除息計算結果",
                                 flag="資料不足：官方表無法拆分"))
        elif o["kind"] == "息" and (o.get("wv") or 0) > 0:
            fill.append(dict(base, kind="現金股利", cash=o["wv"], share_ratio=1.0, source="TWSE TWT49U（權值+息值，純息）", flag=None))
        else:
            fill.append(dict(base, kind="除權息未分類", cash=None, share_ratio=None, source="TWSE TWT49U",
                             flag=f"資料不足：官方表「{o['kind']}」無法拆分現金與配股／現增"))
    if fill:
        ca = pd.concat([ca, pd.DataFrame(fill)], ignore_index=True)
    log["corp_actions"]["filled_from_official"] = pd.DataFrame(fill)["kind"].value_counts().to_dict() if fill else {}
    log["corp_actions"]["rows_after_fill"] = len(ca)
    log["corp_actions"]["mismatch_by_year"] = bad.groupby(bad["date"].dt.year).size().to_dict()
    mm = set(zip(bad["stock_id"], bad["date"]))
    ca["flag"] = [("；".join(x for x in [f, "與官方參考價差異>0.5%"] if isinstance(x, str) and x) if (s, d) in mm else f)
                  for s, d, f in zip(ca["stock_id"], ca["ex_date"], ca["flag"])]
    return ca.sort_values(["stock_id", "ex_date", "kind"]).reset_index(drop=True)
