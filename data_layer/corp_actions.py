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
import re

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
    # 退回-69：groupby().last() 會逐欄取最後非空值，可能把舊公告的欄位混進新公告；改為整列取最後一筆公告
    d = d.sort_values("announced", kind="stable").drop_duplicates(["stock_id", "ex_date", "kind"], keep="last")
    d.attrs["dropped_post_ex_or_dup"] = n0 - len(d)
    return d.drop(columns=["ann_dt"])


def _detail(html: str, key: str):
    m = re.search(key + r"[:：]?\s*(?:<[^>]+>|\s|&nbsp;?)*([0-9.,]+|NA)", html or "")
    if not m or m.group(1) == "NA":
        return None
    return float(m.group(1).replace(",", ""))


def official_reductions() -> pd.DataFrame:
    """官方減資恢復買賣表：櫃買 revivt（2013 起）、證交所 TWTAUU（2011 起）。
    取每仟股換發新股、每股退還股款、減資後現金增資（有則另標，認購權不在本表處理）。"""
    rows = []
    for f in sorted(glob.glob(f"{RAW}/market/tpex_reduction/*.json")):
        j = json.load(open(f, encoding="utf-8"))
        for t in j.get("tables") or []:
            fl = [x.strip() for x in t.get("fields") or []]
            if "恢復買賣日期" not in fl:
                continue
            for r in t.get("data") or []:
                x = dict(zip(fl, r))
                html = x.get("詳細資料", "")
                d = str(x["恢復買賣日期"]).strip()
                rows.append(dict(stock_id=str(x["股票代號"]).strip(), ex_date=f"{int(d[:3]) + 1911}-{d[3:5]}-{d[5:7]}",
                                 per_k=_detail(html, "每壹仟股換發新股票"), refund=_detail(html, "每股退還股款"),
                                 rights_sh=_detail(html, "現金增資總股數"), reason=x.get("減資原因"),
                                 last_close=x.get("最後交易日之收盤價格"), ref=x.get("減資恢復買賣開始日參考價格"),
                                 src=f"TPEx 減資恢復買賣參考價 {os.path.basename(f)}"))
    for f in sorted(glob.glob(f"{RAW}/market/twse_reduction/*.json")):
        j = json.load(open(f, encoding="utf-8"))
        fl = [x.strip() for x in j.get("fields") or []]
        for r in j.get("data") or []:
            x = dict(zip(fl, r))
            det = str(x.get("詳細資料", "")).replace(" ", "").split(",")
            sid, fd = (det + ["", ""])[:2]
            dp = f"{RAW}/market/twse_reduction_detail/{sid}_{fd}.json"
            per_k = refund = rights = None
            if os.path.exists(dp):
                dj = json.load(open(dp, encoding="utf-8"))
                dx = dict(zip([k.strip().rstrip("：:") for k in dj.get("fields") or []], (dj.get("data") or [[]])[0]))
                per_k = _num_unit(dx.get("每壹仟股換發新股票"))
                refund = _num_unit(dx.get("每股退還股款"))
                rights = _num_unit(dx.get("減資並(有償)現金增資"))
            rows.append(dict(stock_id=str(x.get("股票代號", "")).strip(), ex_date=_iso(str(x.get("恢復買賣日期", ""))),
                             per_k=per_k, refund=refund, rights_sh=rights, reason=x.get("減資原因"),
                             last_close=x.get("停止買賣前收盤價格"), ref=x.get("恢復買賣參考價"),
                             src=f"TWSE TWTAUU／TWTAVUDetail {sid}_{fd}" if per_k is not None else "TWSE TWTAUU（明細未取得）"))
    d = pd.DataFrame(rows, columns=["stock_id", "ex_date", "per_k", "refund", "rights_sh", "reason", "last_close", "ref", "src"])
    if len(d):
        d["ex_date"] = pd.to_datetime(d["ex_date"])
    return d


def _num_unit(v):
    if v is None:
        return None
    m = re.search(r"[0-9][0-9,]*\.?[0-9]*", str(v))
    return float(m.group(0).replace(",", "")) if m else None


def _iso(s: str) -> str:
    n = re.findall(r"\d+", s)
    if len(n) == 1 and len(n[0]) == 7:
        return f"{int(n[0][:3]) + 1911}-{n[0][3:5]}-{n[0][5:]}"
    if len(n) == 1 and len(n[0]) == 8:
        return f"{n[0][:4]}-{n[0][4:6]}-{n[0][6:]}"
    y = int(n[0])
    return f"{y + 1911 if y < 1911 else y}-{int(n[1]):02d}-{int(n[2]):02d}"


def reductions() -> pd.DataFrame:
    """退回-67：換股比與退還現金只用官方公告值（官方減資表）。
    官方表查無者：彌補虧損案的「停止買賣前收盤÷恢復參考價」只記在 share_ratio_inferred（僅供比對），
    share_ratio 留空 → 標資料不足，持有期間碰到的交易自動排除（A5）。"""
    off = official_reductions()
    offk = {(r.stock_id, r.ex_date): r for r in off.itertuples()} if len(off) else {}
    rows = []
    for p in glob.glob(f"{RAW}/finmind/TaiwanStockCapitalReductionReferencePrice/*.json.gz"):
        for r in _jl(p).get("data", []):
            last, post = _f(r.get("ClosingPriceonTheLastTradingDay")), _f(r.get("PostReductionReferencePrice"))
            reason = r.get("ReasonforCapitalReduction") or ""
            losses = "loss" in reason.lower()
            inferred = (last / post) if (losses and last > 0 and post > 0) else None
            o = offk.get((r["stock_id"], pd.Timestamp(r["date"])))
            if o is not None and pd.notna(o.per_k):
                basis = "官方公告值"
                ratio, cash = o.per_k / 1000.0, (float(o.refund) if pd.notna(o.refund) else 0.0)
                has_rights = pd.notna(o.rights_sh) and float(o.rights_sh) > 0
                flag = "減資後現金增資：認購權未處理，資料不足" if has_rights else None
                src = o.src
                if flag:
                    ratio = cash = None
            else:
                basis = "僅有反推值" if inferred is not None else "取不到"
                ratio = cash = None
                flag = (f"資料不足：官方減資表查無（{'彌補虧損，反推值只供比對' if inferred is not None else reason or '原因未載'}）")
                src = "FinMind CapitalReductionReferencePrice"
            rows.append(dict(stock_id=r["stock_id"], ex_date=r["date"], kind="減資", cash=cash, share_ratio=ratio,
                             cash_date=None, announced=None, source=src, flag=flag, reduction_reason=reason,
                             ratio_basis=basis, share_ratio_inferred=inferred))
    d = pd.DataFrame(rows)
    if not d.empty:
        d["ex_date"] = pd.to_datetime(d["ex_date"])
    return d


def splits() -> pd.DataFrame:
    p = f"{RAW}/finmind/TaiwanStockSplitPrice/_all.json.gz"
    rows = []
    for r in _jl(p).get("data", []) if os.path.exists(p) else []:
        b, a = _f(r.get("before_price")), _f(r.get("after_price"))
        # 退回-67（A5）：變更前價÷變更後參考價是反推值（參考價經檔位進位，例 0050 得 4.000212），不進主結果
        rows.append(dict(stock_id=r["stock_id"], ex_date=r["date"], kind="面額變更", cash=None,
                         share_ratio=None, share_ratio_inferred=(b / a) if a else None, ratio_basis="僅有反推值" if a else "取不到",
                         cash_date=None, announced=None, source="FinMind TaiwanStockSplitPrice",
                         flag="資料不足：分割比率待官方公告（反推值只供比對）"))
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
        "reduction_ratio_basis": rd["ratio_basis"].value_counts().to_dict() if not rd.empty else {},
        "split_ratio_basis": sp["ratio_basis"].value_counts().to_dict() if not sp.empty else {},
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
            # 退回-68（Eve R01）：NaN 不得被「or 0.0」吃掉。2000-09～2007-12 櫃買歷史表沒有現金／配股／現增欄，
            # 三欄全缺時不是「0」而是「不知道」→ 列資料不足事件，訊號與持有窗須接住；不用參考價反推。
            raw3 = [o.get("cash"), o.get("stock_per_k"), o.get("rights_sh")]
            known = [x for x in raw3 if x is not None and pd.notna(x)]
            if not known:
                fill.append(dict(base, kind="除權息未分類", cash=None, share_ratio=None, source="TPEx 除權除息歷史表（無分項欄位）",
                                 flag="資料不足：官方歷史表只有參考價與漲跌停，無現金／配股／現增分項"))
                continue
            c, k, rs = [float(x) if (x is not None and pd.notna(x)) else 0.0 for x in raw3]
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
        elif o["kind"] == "息" and pd.notna(o.get("wv")) and float(o.get("wv") or 0) > 0:
            fill.append(dict(base, kind="現金股利", cash=o["wv"], share_ratio=1.0, source="TWSE TWT49U（權值+息值，純息）", flag=None))
        else:
            fill.append(dict(base, kind="除權息未分類", cash=None, share_ratio=None, source="TWSE TWT49U",
                             flag=f"資料不足：官方表「{o['kind']}」無法拆分現金與配股／現增"))
    if fill:
        ca = pd.concat([ca, pd.DataFrame(fill)], ignore_index=True)
    log["corp_actions"]["filled_from_official"] = pd.DataFrame(fill)["kind"].value_counts().to_dict() if fill else {}
    # 對帳：每筆官方除權息事件都必須在公司行動表有對應（FinMind 或官方補列），否則建置失敗
    keys = set(zip(ca["stock_id"].astype(str), pd.to_datetime(ca["ex_date"])))
    unmatched = [(s, d) for s, d in zip(official_ex["stock_id"].astype(str), pd.to_datetime(official_ex["date"])) if (s, d) not in keys]
    log["corp_actions"]["official_events_unmatched"] = len(unmatched)
    if unmatched:
        raise RuntimeError(f"官方除權息事件未進公司行動表 {len(unmatched)} 筆，例 {unmatched[:5]}")
    log["corp_actions"]["rows_after_fill"] = len(ca)
    log["corp_actions"]["mismatch_by_year"] = bad.groupby(bad["date"].dt.year).size().to_dict()
    mm = set(zip(bad["stock_id"], bad["date"]))
    ca["flag"] = [("；".join(x for x in [f, "與官方參考價差異>0.5%"] if isinstance(x, str) and x) if (s, d) in mm else f)
                  for s, d, f in zip(ca["stock_id"], ca["ex_date"], ca["flag"])]
    return ca.sort_values(["stock_id", "ex_date", "kind"]).reset_index(drop=True)
