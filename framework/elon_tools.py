# 來源：elon-backtest 技能 SKILL.md「程式（存成 elon_tools.py）」原文照錄，未修改。
"""elon_tools — Elon 回測作業工具（elon-backtest 技能）。
統計一律呼叫 Drive 上的 bt_stats 原檔；本檔不重算統計，只做資料處理、出表與自檢。
"""
import importlib.util, math, subprocess, sys
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
import numpy as np
import pandas as pd

# ---------- 1. 載入 bt_stats ----------
def load_bt_stats(path):
    """載入 Drive 下載的 bt_stats 原檔；selftest 未通過就停止。"""
    r = subprocess.run([sys.executable, path, "--selftest"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("bt_stats selftest 未通過，停止計算並回報 Ed：\n" + r.stdout[-2000:])
    spec = importlib.util.spec_from_file_location("bt_stats", path)
    bt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bt)
    return bt

# ---------- 2. 價格工具 ----------
def share_return(entry_date, entry_px, exit_date, exit_px, events):
    """含息報酬：固定股數加實得現金（研究預設口徑 V03 第三節）。
    events：該股公司行動清單，每筆為 dict：
      date   除權息日或減資恢復買賣日
      cash   每股現金股利實額（來源記載值，不用參考價差反推）
      stock  每股配股數（例：配股 1 元、面額 10 元＝0.1）
      swap   減資換股比（例：每 1 股換 0.7 股＝0.7）
      refund 減資每股退還現金
    只計入 entry_date < date <= exit_date 的事件：進場時已除權的不算，出場當天才除權的要算。
    同一天的現金與配股都以事件前持股計算。不做股息再投資，不計稅。
    報酬＝（出場持股×出場價＋累計現金）÷進場價－1。
    """
    shares, cash = 1.0, 0.0
    for ev in sorted(events, key=lambda e: pd.Timestamp(e["date"])):
        if pd.Timestamp(entry_date) < pd.Timestamp(ev["date"]) <= pd.Timestamp(exit_date):
            pre = shares
            cash += pre * (ev.get("cash", 0.0) + ev.get("refund", 0.0))
            shares = pre * (1.0 + ev.get("stock", 0.0)) * ev.get("swap", 1.0)
    return (shares * exit_px + cash) / entry_px - 1

TICK_CHANGE = pd.Timestamp("2005-03-01")  # 證交所 introduce004.pdf「調整股價升降單位－自94年3月1日實施－」


def tick_size(price, kind="stock", date=None):
    """升降單位。kind='stock' 股票，'etf' ETF（受益憑證）。
    股票：2005-03-01 起現行表（<10 0.01、<50 0.05、<100 0.1、<500 0.5、<1000 1、≥1000 5）；
    之前為舊表（<5 0.01、<15 0.05、<50 0.1、<150 0.5、<1000 1、≥1000 5），來源同上 PDF 新舊對照表。
    ETF：<50 0.01、≥50 0.05；0050 自 2004 年起成交價即為此級距（資料實證），故全期適用。
    退回-69（外部審查）：原本所有日期都套現行表，2005-03-01 前會差一檔。"""
    p = Decimal(str(price))
    if kind == "etf":
        return Decimal("0.01") if p < 50 else Decimal("0.05")
    old = date is not None and pd.Timestamp(date) < TICK_CHANGE
    table = ((5, "0.01"), (15, "0.05"), (50, "0.1"), (150, "0.5"), (1000, "1")) if old else \
        ((10, "0.01"), (50, "0.05"), (100, "0.1"), (500, "0.5"), (1000, "1"))
    for bound, tick in table:
        if p < bound:
            return Decimal(tick)
    return Decimal("5")


def security_kind(stock_id: str) -> str:
    """代號以 00 開頭者為 ETF（含槓反、債券 ETF）；其餘視為股票。"""
    return "etf" if str(stock_id).startswith("00") else "stock"


# 跌幅限制縮小為 3.5%（漲幅不變）的官方期間：證交所 60 週年特刊（89 年兩段）、央行國內經濟金融日誌（97 年 10 月）
DOWN_35 = [(pd.Timestamp("2000-10-20"), pd.Timestamp("2000-11-07")),
           (pd.Timestamp("2000-11-21"), pd.Timestamp("2000-12-31")),
           (pd.Timestamp("2008-10-13"), pd.Timestamp("2008-10-24"))]


def limit_pcts(date):
    d = pd.Timestamp(date)
    up = Decimal("0.07") if d < pd.Timestamp("2015-06-01") else Decimal("0.10")
    dn = Decimal("0.035") if any(a <= d <= b for a, b in DOWN_35) else up
    return up, dn


def limit_prices(ref, date, kind="stock"):
    """依官方規則推算漲跌停價（只在判斷能否成交時用；事件由漲跌停定義時必須用官方逐日值）。
    2015-06-01 前漲跌幅 7%，之後 10%；DOWN_35 期間跌幅 3.5%。漲停向下取到升降單位，跌停向上取；升降單位依日期與證券種類。
    除權息日、減資恢復買賣日請傳入官方參考價；新上市（櫃）前五日無漲跌幅限制，不要呼叫本函式。
    """
    pu, pdn = limit_pcts(date)
    r = Decimal(str(ref))
    up_raw, dn_raw = r * (1 + pu), r * (1 - pdn)
    tu, td = tick_size(up_raw, kind, date), tick_size(dn_raw, kind, date)
    up = (up_raw / tu).to_integral_value(rounding=ROUND_FLOOR) * tu
    dn = (dn_raw / td).to_integral_value(rounding=ROUND_CEILING) * td
    return float(up), float(dn)

REF_BIDASK_FROM = pd.Timestamp("2011-03-28")  # 證交所 60 週年特刊：開盤競價基準決定原則修正，100-03-28 實施


def next_base(base, close, bid, ask, next_date):
    """次一營業日開盤競價基準（＝漲跌幅計算基準）。
    有收盤價→收盤價。無收盤價：2011-03-28 起，收盤時最高買進申報價高於當日基準→該買價；最低賣出申報價低於基準→該賣價；
    否則沿用當日基準。2011-03-28 前沿用當日基準（舊制「連續 2 日漲／跌至限度揭示價得為基準」未納入，見注意事項）。"""
    if close is not None and close == close and close > 0:
        return close
    if base is None or base != base:
        return None
    if pd.Timestamp(next_date) >= REF_BIDASK_FROM:
        if bid is not None and bid == bid and bid > base:
            return bid
        if ask is not None and ask == ask and 0 < ask < base:
            return ask
    return base


def compare_limits(sample):
    """sample 欄位：ref, date, kind, official_up, official_dn。回傳不一致的列；應為空才可用推算值。"""
    bad = []
    for row in sample.itertuples():
        up, dn = limit_prices(row.ref, row.date, getattr(row, "kind", "stock"))
        if abs(up - row.official_up) > 1e-9 or abs(dn - row.official_dn) > 1e-9:
            bad.append((row.date, row.ref, up, row.official_up, dn, row.official_dn))
    return bad

# ---------- 3. 出表 ----------
TEN = ["樣本數", "平均報酬", "平均持有交易日數", "單利年化", "勝率", "賠率R", "凱利", "標準差", "t值", "雙尾p"]
AGG = ["聚合單位", "聚合單位數", "聚合p"]
REPORT_NAMES = {"單利年化": "單筆資金周轉年化報酬（單利）", "賠率R": "賠率 R", "雙尾p": "雙尾 p 值", "t值": "t 值"}

def ten_table(trades, bt, by=("combo",), cluster_unit=None):
    """以 bt_stats 產出十項統計表（不含半凱利）。trades 只放策略卡組合或只放討論衍生組合（E-Test），兩種分表。
    by 可加 'sample' 讓樣本內、樣本外、最新年度並列。"""
    t = trades[trades["excluded_reason"].isna() | (trades["excluded_reason"] == "")].copy()
    if t["is_etest"].nunique() > 1:
        raise ValueError("策略卡組合與討論衍生組合要分表，不可放在同一張表")
    t["_key"] = t[list(by)].astype(str).agg("｜".join, axis=1)
    use_cluster = cluster_unit is not None and t["cluster"].notna().all()
    res = bt.summarize_df(t, ret="ret", hold="hold_days",
                          cluster="cluster" if use_cluster else None,
                          cluster_unit=cluster_unit if use_cluster else None, by="_key")
    cols = ["_key"] + TEN + (AGG if use_cluster else []) + ["N/A原因", "bt_stats版本"]
    out = res[cols].rename(columns={"_key": "／".join(by)})
    return out

def to_markdown(table, pct_cols=("平均報酬", "單利年化", "勝率", "標準差")):
    """報告用顯示格式；比對與自檢一律用未四捨五入的原表。"""
    d = table.copy()
    for c in d.columns:
        if c in pct_cols:
            d[c] = d[c].map(lambda v: "N/A" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v*100:.2f}%")
        elif d[c].dtype.kind == "f":
            d[c] = d[c].map(lambda v: "N/A" if v is None or math.isnan(v) else f"{v:.4g}")
    d = d.rename(columns=REPORT_NAMES).fillna("N/A")
    return d.to_markdown(index=False)

# ---------- 4. 交件前自檢 ----------
REQUIRED = ["trade_id", "combo", "is_etest", "symbol", "info_time", "entry_time", "entry_date",
            "entry_px", "exit_date", "exit_px", "ret", "hold_days", "cluster", "sample", "excluded_reason"]

def selfcheck(trades, bt, reported=None, by=("combo",), cluster_unit=None, report_text=None, tol=1e-4, etest=False, quick=False):
    """回傳 [(PASS/FAIL/WARN, 項目, 說明)]。FAIL 全部處理完才交件。
    reported：報告中的結果表（ten_table 同格式、未四捨五入）；report_text：報告全文。
    etest=False 核對策略卡組合表，etest=True 核對討論衍生組合表；有 E-Test 時兩張表各跑一次。
    quick=True 表示快篩：納入的交易不得有樣本外或最新年度。"""
    out = []
    def add(ok, item, msg="", warn=False):
        out.append(("PASS" if ok else ("WARN" if warn else "FAIL"), item, msg))
    miss = [c for c in REQUIRED if c not in trades.columns]
    add(not miss, "明細欄位齊全", f"缺 {miss}" if miss else "")
    if miss:
        return out
    ex = trades["excluded_reason"].fillna("").astype(str).str.len() > 0
    t = trades[~ex]
    if quick:
        oos = t["sample"].astype(str).isin(["樣本外", "最新年度"])
        add(not oos.any(), "快篩未用到樣本外", f"{int(oos.sum())} 筆屬樣本外或最新年度，快篩只能用樣本內")
    add(t["ret"].notna().all(), "納入交易的報酬無缺值", "有缺值時不得推估，改列排除原因")
    add(trades.loc[ex, "ret"].isna().all(), "排除列不帶報酬", "排除的交易 ret 留空")
    add((t["ret"].abs() < 1).all(), "報酬為小數口徑", "有 |ret|≥1，確認不是百分數", warn=True)
    h = t["hold_days"]
    add(((h >= 1) & (h == h.round())).all(), "持有交易日數為 ≥1 的整數")
    late = pd.to_datetime(t["entry_time"]) <= pd.to_datetime(t["info_time"])
    add(not late.any(), "進場晚於資料可用時點", f"{int(late.sum())} 筆違反時點規則：{list(t.loc[late,'trade_id'][:10])}")
    back = pd.to_datetime(t["exit_date"]) < pd.to_datetime(t["entry_date"])
    add(not back.any(), "出場日不早於進場日", f"{int(back.sum())} 筆")
    add(trades["trade_id"].is_unique, "交易編號不重複")
    formal = t[t["is_etest"].astype(bool) == etest]
    if cluster_unit is not None:
        add(formal["cluster"].notna().all(), "群聚標籤齊全", "有群聚時每筆都要有聚合單位標籤")
    if reported is not None:
        mine = ten_table(formal, bt, by=by, cluster_unit=cluster_unit)
        key = mine.columns[0]
        other_keys = set(t[t["is_etest"].astype(bool) != etest][list(by)].astype(str).agg("｜".join, axis=1))
        mixed = set(reported[key].astype(str)) & (other_keys - set(mine[key]))
        add(not mixed, "策略卡組合與 E-Test 組合分表", str(sorted(mixed)))
        m = reported.merge(mine, on=key, how="outer", suffixes=("_報告", "_重算"), indicator=True)
        add((m["_merge"] == "both").all(), "結果表組合與明細一一對應",
            str(m.loc[m["_merge"] != "both", key].tolist()))
        for c in TEN + (["聚合p"] if cluster_unit else []):
            a, b = m.get(c + "_報告"), m.get(c + "_重算")
            if a is None or b is None:
                add(False, f"報告缺欄位：{c}")
                continue
            both_na = a.isna() & b.isna()
            diff = (a.astype(float) - b.astype(float)).abs()
            bad = ~(both_na | (diff <= tol))
            add(not bad.any(), f"重算一致：{c}", str(m.loc[bad, key].tolist()))
        if cluster_unit is not None:
            need = mine[mine["聚合單位數"] < mine["樣本數"]][key].tolist()
            add(True if not need else reported.set_index(key).loc[need, "聚合p"].notna().all(),
                "有群聚的組合已列聚合 p", str(need))
    if report_text is not None:
        head = report_text.strip()[:600]
        add(all(s in head for s in ("①", "②", "③")), "開頭有三行決策摘要")
        add("未計入" in report_text, "有成本聲明（未計入稅、交易成本與滑價）")
        add("決策紀錄" in report_text, "引用了決策紀錄", "核准依據應引用策略總表「決策紀錄」對應列", warn=True)
        add("半凱利" not in report_text, "報告未列半凱利")
        no_cand = "沒有值得執行的候選組合" in report_text or "沒有值得續做的組合" in report_text
        add(no_cand or "敏感度測試" in report_text, "有候選組合時已附敏感度測試", "快篩報告可忽略；正式策略包有候選組合時依 Elon 手冊第 4-B 節補做", warn=True)
        hits = [w for w in ("推估", "估計值", "假設為", "約略") if w in report_text]
        add(not hits, "沒有推估值字樣", f"出現 {hits}，確認不是用推估值補缺", warn=True)
    return out

def print_check(res):
    for s, item, msg in res:
        print(f"{s:4} {item}" + (f"：{msg}" if msg and s != "PASS" else ""))
    n_fail = sum(s == "FAIL" for s, _, _ in res)
    print("自檢結果：" + ("全部通過" if n_fail == 0 else f"{n_fail} 項 FAIL，修正後再交件"))
    return n_fail == 0
