"""070 快篩統計：只用樣本內；十項統計與回撤三項全部由 bt_stats 1.2（elon-backtest 技能 elon_tools）產出。
聚合單位＝進場日；Holm 以聚合 p 為輸入，家族＝優化組 9 組（不含原版 Q1）。
"""
import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/elon-bt")
sys.path.insert(0, "."); from elon_tools import load_bt_stats, ten_table, dd_table, baseline_check

bt = load_bt_stats("/root/btstats/bt_stats_v1.2.py")
assert baseline_check(bt)
VARIANTS = ["V-CAP50", "V-CAP200", "V-PR3", "V-PR8", "V-REV3", "V-TOP10", "V-QTR", "V-LIQ2000萬", "V-LIQ5000萬"]


def holm(s):
    o = s.dropna().sort_values(); m = len(o); out = {}; run = 0.0
    for k, (nm, v) in enumerate(o.items()):
        run = max(run, min(1.0, (m - k) * v)); out[nm] = run
    return pd.Series(out)


t = pd.read_pickle("trades070.pkl")
t["is_etest"] = False
t["info_time"] = t["signal_date"] + " 14:30"
t["entry_time"] = t["entry_date"] + " 09:00"
u = t[t["sample"] == "樣本內"]
order = list(dict.fromkeys(t.combo))
tt = ten_table(u, bt, by=("combo",), cluster_unit="進場日").set_index("combo").reindex(order).reset_index()
dd = dd_table(u, bt, by=("combo",)).set_index("combo").reindex(order).reset_index()
tt["Holm聚合p"] = tt.combo.map(holm(tt.set_index("combo").loc[VARIANTS, "聚合p"]))
tt.to_pickle("card_ten.pkl"); dd.to_pickle("card_dd.pkl"); t.to_pickle("trades070_full.pkl")
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
cols = ["combo", "樣本數", "平均報酬", "平均持有交易日數", "單利年化", "勝率", "賠率R", "凱利", "標準差", "t值", "雙尾p", "聚合單位數", "聚合p", "Holm聚合p"]
print(tt[cols].to_string())
print(dd[["combo", "最大回撤", "最差三次回撤平均", "最長回撤期筆數", "最長回撤期日曆日", "最長回撤期未回復", "需註記", "最長回撤期聚合單位數"]].to_string())
ex = t[t.excluded_reason.notna()].groupby(["combo", "excluded_reason"]).size()
print(ex.to_string())
