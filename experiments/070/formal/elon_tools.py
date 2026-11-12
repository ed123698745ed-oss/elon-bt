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

def tick_size(price, kind="stock"):
    """現行升降單位。kind='stock' 股票，'etf' ETF。更早期間使用前先與官方值比對。"""
    p = Decimal(str(price))
    if kind == "etf":
        return Decimal("0.01") if p < 50 else Decimal("0.05")
    for bound, tick in ((10, "0.01"), (50, "0.05"), (100, "0.1"), (500, "0.5"), (1000, "1")):
        if p < bound:
            return Decimal(tick)
    return Decimal("5")

def limit_prices(ref, date, kind="stock"):
    """依官方規則推算漲跌停價（只在判斷能否成交時用；事件由漲跌停定義時必須用官方逐日值）。
    2015-06-01 前漲跌幅 7%，之後 10%。漲停向下取到升降單位，跌停向上取。
    除權息日、減資恢復買賣日請傳入官方參考價；新上市（櫃）前五日無漲跌幅限制，不要呼叫本函式。
    """
    pct = Decimal("0.07") if pd.Timestamp(date) < pd.Timestamp("2015-06-01") else Decimal("0.10")
    r = Decimal(str(ref))
    up_raw, dn_raw = r * (1 + pct), r * (1 - pct)
    tu, td = tick_size(up_raw, kind), tick_size(dn_raw, kind)
    up = (up_raw / tu).to_integral_value(rounding=ROUND_FLOOR) * tu
    dn = (dn_raw / td).to_integral_value(rounding=ROUND_CEILING) * td
    return float(up), float(dn)

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

DD = ["最大回撤", "最差三次回撤平均", "最長回撤期筆數", "最長回撤期日曆日", "最長回撤期未回復", "最長回撤期聚合單位數"]

def dd_table(trades, bt, by=("combo",), sd=None, sd_source=None):
    """以 bt_stats.drawdown3 產出回撤三項；與 ten_table 一樣，策略卡組合與討論衍生組合分表。"""
    if not hasattr(bt, "drawdown3"):
        raise RuntimeError("bt_stats 版本不含 drawdown3，請下載 v1.1 以上")
    t = trades[trades["excluded_reason"].isna() | (trades["excluded_reason"] == "")].copy()
    if t["is_etest"].nunique() > 1:
        raise ValueError("策略卡組合與討論衍生組合要分表，不可放在同一張表")
    t["_key"] = t[list(by)].astype(str).agg("｜".join, axis=1)
    rows = []
    for key, g in t.groupby("_key", sort=False):
        cl = g["cluster"].tolist() if g["cluster"].notna().all() else g["entry_date"].astype(str).tolist()
        o = bt.drawdown3(g["ret"].to_numpy(), g["entry_date"], g["exit_date"], cluster=cl, sd=sd, sd_source=sd_source)
        row = {"／".join(by): key}
        row.update(o)
        n, u = o.get("最長回撤期筆數"), o.get("最長回撤期聚合單位數")
        row["需註記"] = bool(n and u and n >= 2 * u)
        rows.append(row)
    return pd.DataFrame(rows)

def dd_markdown(dd):
    """回撤三項顯示格式。"""
    d = pd.DataFrame()
    d[dd.columns[0]] = dd[dd.columns[0]]
    f = lambda v: "N/A" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v*100:.1f}%"
    d["最大回撤"] = dd["最大回撤"].map(f)
    d["最差三次回撤平均"] = dd["最差三次回撤平均"].map(f)
    def lab(r):
        if r["最長回撤期筆數"] is None or (isinstance(r["最長回撤期筆數"], float) and math.isnan(r["最長回撤期筆數"])):
            return "N/A"
        if r["最長回撤期筆數"] == 0:
            return "無回撤"
        s = f"{int(r['最長回撤期筆數']):,}筆（{int(r['最長回撤期日曆日']):,}天" + ("，未回復" if r["最長回撤期未回復"] else "") + "）"
        return s
    d["最長回撤期"] = dd.apply(lab, axis=1)
    d["註記（聚合單位數）"] = dd.apply(lambda r: f"{int(r['最長回撤期筆數'])} 筆 = {int(r['最長回撤期聚合單位數'])} 個聚合單位" if r["需註記"] else "", axis=1)
    return d.to_markdown(index=False)

# ---------- 4. 交件前自檢 ----------
REQUIRED = ["trade_id", "combo", "is_etest", "symbol", "info_time", "entry_time", "entry_date",
            "entry_px", "exit_date", "exit_px", "ret", "hold_days", "cluster", "sample", "excluded_reason"]

def selfcheck(trades, bt, reported=None, by=("combo",), cluster_unit=None, report_text=None, tol=1e-4, etest=False, quick=False, reported_dd=None, sd=None, sd_source=None,
              calendar=None, split=None, current_r=None):
    """回傳 [(PASS/FAIL/WARN, 項目, 說明)]。FAIL 全部處理完才交件。
    reported：報告中的結果表（ten_table 同格式、未四捨五入）；report_text：報告全文。
    reported_dd：報告中的回撤表（dd_table 同格式、未四捨五入）；sd／sd_source 與出表時相同。
    etest=False 核對策略卡組合表，etest=True 核對討論衍生組合表；有 E-Test 時兩張表各跑一次。
    quick=True 表示快篩：納入的交易不得有樣本外或最新年度。
    calendar：官方交易日清單（防錯 B3／C6）；有傳就以它重算持有交易日數（含首尾）並核對。
    split：(樣本內末日, 樣本外首日)（防錯 D5／D7、口徑第五節）；有傳就核對樣本標籤與切點、隔離帶。
    current_r：現行修訂號，例如 "R05"（防錯 E4）；有傳就檢查報告開頭沒有殘留其他 R。"""
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
    # 防錯 C7：同組合同股票持倉不重疊（前筆出場當日不得再進場）
    s = t.assign(_e=pd.to_datetime(t["entry_date"]), _x=pd.to_datetime(t["exit_date"])).sort_values(["combo", "symbol", "_e"])
    prev_x = s.groupby(["combo", "symbol"])["_x"].shift()
    ov = s.loc[s["_e"] <= prev_x, "trade_id"]
    add(ov.empty, "同組合同股票持倉不重疊", f"{len(ov)} 筆：{list(ov[:10])}；策略卡明文允許重疊時在注意事項說明", warn=True)
    # 防錯 B3／C6：持有交易日數依官方交易日曆含首尾計算
    if calendar is not None:
        cal = pd.DatetimeIndex(pd.to_datetime(sorted(set(calendar))))
        e = cal.searchsorted(pd.to_datetime(t["entry_date"]).values)
        x = cal.searchsorted(pd.to_datetime(t["exit_date"]).values, side="right")
        bad = t.loc[(x - e) != t["hold_days"].to_numpy(), "trade_id"]
        add(bad.empty, "持有日數與交易日曆一致", f"{len(bad)} 筆不符：{list(bad[:10])}（不得數個股有效日K）")
    # 防錯 D5／D7、口徑第五節：樣本內須在切點前出場，樣本外須在隔離帶後進場
    if split is not None:
        is_end, oos_start = pd.Timestamp(split[0]), pd.Timestamp(split[1])
        lab = t["sample"].astype(str)
        b1 = t.loc[(lab == "樣本內") & (pd.to_datetime(t["exit_date"]) > is_end), "trade_id"]
        b2 = t.loc[lab.isin(["樣本外", "最新年度"]) & (pd.to_datetime(t["entry_date"]) < oos_start), "trade_id"]
        add(b1.empty and b2.empty, "樣本標籤與切點一致", f"樣本內出場晚於切點 {len(b1)} 筆、樣本外早於隔離帶 {len(b2)} 筆：{list(b1[:5]) + list(b2[:5])}")
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
    if reported_dd is not None:
        mine_dd = dd_table(formal, bt, by=by, sd=sd, sd_source=sd_source)
        key = mine_dd.columns[0]
        m = reported_dd.merge(mine_dd, on=key, how="outer", suffixes=("_報告", "_重算"), indicator=True)
        add((m["_merge"] == "both").all(), "回撤表組合與明細一一對應", str(m.loc[m["_merge"] != "both", key].tolist()))
        for c, tl in (("最大回撤", tol), ("最差三次回撤平均", tol), ("最長回撤期筆數", 0), ("最長回撤期日曆日", 0)):
            a, b = m.get(c + "_報告"), m.get(c + "_重算")
            if a is None or b is None:
                add(False, f"回撤表缺欄位：{c}")
                continue
            bad = ~((a.isna() & b.isna()) | ((a.astype(float) - b.astype(float)).abs() <= tl))
            add(not bad.any(), f"回撤重算一致：{c}", str(m.loc[bad, key].tolist()))
    elif not quick and reported is not None:
        add(False, "已附回撤三項", "正式策略包結果表須含回撤三項（Elon 手冊第 6 節 ③）", warn=True)
    if report_text is not None:
        head = report_text.strip()[:600]
        add(all(s in head for s in ("①", "②", "③")), "開頭有三行決策摘要")
        add("未計入" in report_text, "有成本聲明（未計入稅、交易成本與滑價）")
        add("決策紀錄" in report_text, "引用了決策紀錄", "核准依據應引用策略總表「決策紀錄」對應列", warn=True)
        add("半凱利" not in report_text, "報告未列半凱利")
        add("最大回撤" in report_text, "報告列了回撤三項", "十項統計之後應列最大回撤、最差三次回撤平均、最長回撤期")
        no_cand = "沒有值得執行的候選組合" in report_text or "沒有值得續做的組合" in report_text
        add(no_cand or "敏感度測試" in report_text, "有候選組合時已附敏感度測試", "快篩報告可忽略；正式策略包有候選組合時依 Elon 手冊第 4-B 節補做", warn=True)
        # 防錯 E4：格式字串未替換、決策摘要殘留舊版號
        import re
        left = sorted(set(re.findall(r"\{[A-Za-z_][A-Za-z0-9_]*\}", report_text)))
        add(not left, "報告沒有未替換的變數", f"出現 {left[:10]}")
        if current_r:
            old = sorted(set(re.findall(r"R\d{2}", head)) - {current_r})
            add(not old, "決策摘要沒有殘留舊版號", f"開頭出現 {old}，現行為 {current_r}；確屬比較說明時在注意事項寫理由", warn=True)
        hits = [w for w in ("推估", "估計值", "假設為", "約略") if w in report_text]
        add(not hits, "沒有推估值字樣", f"出現 {hits}，確認不是用推估值補缺", warn=True)
    return out

def print_check(res):
    for s, item, msg in res:
        print(f"{s:4} {item}" + (f"：{msg}" if msg and s != "PASS" else ""))
    n_fail = sum(s == "FAIL" for s, _, _ in res)
    print("自檢結果：" + ("全部通過" if n_fail == 0 else f"{n_fail} 項 FAIL，修正後再交件"))
    return n_fail == 0

# ---------- 5. 基準案例（技能或 bt_stats 改動後必跑） ----------
# 固定 18 筆交易；預期值由 bt_stats 1.2 與本檔於 2026-11-05 產生後凍結。
BASE_ROWS = [  # trade_id, combo, symbol, entry, exit, hold_days, ret
    ("T01","A","1101","2024-01-02","2024-01-04",3,0.0210), ("T02","A","2330","2024-01-02","2024-01-03",2,-0.0150),
    ("T03","A","2317","2024-01-08","2024-01-08",1,0.0000), ("T04","A","1101","2024-01-10","2024-01-16",5,0.0320),
    ("T05","A","2454","2024-01-10","2024-01-12",3,-0.0080), ("T06","A","2603","2024-01-10","2024-01-11",2,0.0110),
    ("T07","A","2330","2024-01-18","2024-01-22",3,-0.0270), ("T08","A","2317","2024-01-24","2024-01-26",3,0.0140),
    ("T09","A","2882","2024-01-29","2024-02-01",4,-0.0060), ("T10","A","1101","2024-02-02","2024-02-06",3,0.0190),
    ("T11","A","2454","2024-02-05","2024-02-05",1,-0.0310), ("T12","A","2603","2024-02-07","2024-02-08",2,0.0250),
    ("T13","B","3008","2024-01-03","2024-01-05",3,0.0050), ("T14","B","3008","2024-01-09","2024-01-10",2,0.0120),
    ("T15","B","2412","2024-01-09","2024-01-11",3,0.0030), ("T16","B","2412","2024-01-17","2024-01-19",3,0.0210),
    ("T17","B","3008","2024-01-23","2024-01-23",1,0.0080), ("T18","B","2412","2024-01-30","2024-02-02",4,0.0160),
]
BASE_EXPECT = {
    "A": {"樣本數": 12, "平均報酬": 0.0029166666666666677, "平均持有交易日數": 2.6666666666666665, "單利年化": 0.2756250000000001,
          "勝率": 0.5, "賠率R": 1.1685823754789273, "凱利": 0.07213114754098365, "標準差": 0.0206285694799198,
          "t值": 0.48978819014345604, "雙尾p": 0.6339053665465506, "聚合單位數": 9, "聚合p": 0.8859433065610491,
          "最大回撤": -0.014973678233494714, "最差三次回撤平均": -0.006007599733477013, "最長回撤期筆數": 6, "最長回撤期日曆日": 21},
    "B": {"樣本數": 6, "平均報酬": 0.010833333333333334, "平均持有交易日數": 2.6666666666666665, "單利年化": 1.0237500000000002,
          "勝率": 1.0, "賠率R": None, "凱利": None, "標準差": 0.006853223086013374,
          "t值": 3.872066989079671, "雙尾p": 0.011735687271193587, "聚合單位數": 5, "聚合p": 0.018734407673253035,
          "最大回撤": 0.0, "最差三次回撤平均": 0.0, "最長回撤期筆數": 0, "最長回撤期日曆日": 0},
}

def baseline_trades():
    d = pd.DataFrame(BASE_ROWS, columns=["trade_id", "combo", "symbol", "entry_date", "exit_date", "hold_days", "ret"])
    d["is_etest"] = False
    d["info_time"] = (pd.to_datetime(d["entry_date"]) - pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d 14:30")
    d["entry_time"] = d["entry_date"] + " 09:00"
    d["entry_px"], d["exit_px"] = 100.0, 100.0 * (1 + d["ret"])
    d["cluster"], d["sample"], d["excluded_reason"] = d["entry_date"], "樣本內", None
    return d

def baseline_check(bt, tol=1e-10):
    """① 數值與凍結值一致；② 正確資料自檢全過；③ 故意改錯的資料，自檢要抓到。全部 True 才算通過。"""
    cal = list(pd.bdate_range("2024-01-02", "2024-02-29"))
    t = baseline_trades()
    tt = ten_table(t, bt, by=("combo",), cluster_unit="進場日").set_index("combo")
    dd = dd_table(t, bt, by=("combo",)).set_index("combo")
    bad = []
    for k, exp in BASE_EXPECT.items():
        for c, v in exp.items():
            got = tt.loc[k, c] if c in tt.columns else dd.loc[k, c]
            na = got is None or (isinstance(got, float) and math.isnan(got))
            if (v is None) != na or (v is not None and abs(float(got) - v) > tol):
                bad.append(f"{k}.{c}: 得 {got}，應為 {v}")
    print("① 數值一致" if not bad else "① 數值不一致：\n  " + "\n  ".join(bad))
    ok_clean = all(s != "FAIL" and s != "WARN" for s, _, _ in selfcheck(t, bt, calendar=cal, quick=True))
    print("② 正確資料自檢全過" if ok_clean else "② 正確資料出現 FAIL／WARN")
    w = t.copy()
    w.loc[w.trade_id == "T04", "hold_days"] = 4                 # 持有日與日曆不符
    w.loc[w.trade_id == "T14", ["entry_date", "entry_time"]] = ["2024-01-05", "2024-01-05 09:00"]  # 與 T13 重疊
    hit = {i for s, i, _ in selfcheck(w, bt, calendar=cal, report_text="①②③ 未計入 決策紀錄 最大回撤 {R04_DIFF}") if s != "PASS"}
    need = {"持有日數與交易日曆一致", "同組合同股票持倉不重疊", "報告沒有未替換的變數"}
    print("③ 改錯資料全部抓到" if need <= hit else f"③ 漏抓：{need - hit}")
    return not bad and ok_clean and need <= hit
