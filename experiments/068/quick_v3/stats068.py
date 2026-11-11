"""068 快篩統計：策略卡組合與 E-Test 分表；只用樣本內；全部由 bt_stats 1.2（elon-backtest 技能 elon_tools.py 出表）。
聚合單位＝進場日（換股執行日）；Holm 以聚合 p 為輸入，家族＝策略卡 10 組優化變體（＋合併組，若有）。
"""
import pickle
import numpy as np, pandas as pd
from elon_tools import load_bt_stats, ten_table, dd_table

bt = load_bt_stats("bt_stats_v1.2.py")
VARIANTS = ["V-L20", "V-L120", "V-TOP10", "V-FILT1ST", "V-ROE8", "V-REV", "V-LIQ0.5億", "V-LIQ2億", "V-2W", "V-MKT"]


def holm(s):
    o = s.dropna().sort_values(); m = len(o); out = {}; run = 0.0
    for k, (nm, v) in enumerate(o.items()):
        run = max(run, min(1.0, (m - k) * v)); out[nm] = run
    return pd.Series(out)


def tables(t, family):
    u = t[t["sample"] == "樣本內"]
    order = list(dict.fromkeys(t.combo))
    tt = ten_table(u, bt, by=("combo",), cluster_unit="進場日").set_index("combo").reindex(order).reset_index()
    dd = dd_table(u, bt, by=("combo",)).set_index("combo").reindex(order).reset_index()
    h = holm(tt.set_index("combo").loc[[c for c in family if c in set(tt.combo)], "聚合p"])
    tt["Holm聚合p"] = tt.combo.map(h)
    return tt, dd


if __name__ == "__main__":
    import sys
    card = pd.read_pickle("trades068.pkl")
    fam = VARIANTS + [c for c in card.combo.unique() if c.startswith("V-MERGE")]
    tt, dd = tables(card, fam)
    tt.to_pickle("card_ten.pkl"); dd.to_pickle("card_dd.pkl")
    pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
    cols = ["combo", "樣本數", "平均報酬", "平均持有交易日數", "單利年化", "勝率", "賠率R", "凱利", "標準差", "t值", "雙尾p", "聚合單位數", "聚合p", "Holm聚合p"]
    print(tt[cols].to_string())
    print(dd[["combo", "最大回撤", "最差三次回撤平均", "最長回撤期筆數", "最長回撤期日曆日", "最長回撤期未回復", "需註記", "最長回撤期聚合單位數"]].to_string())
    try:
        et = pd.read_pickle("etrades068.pkl")
        ett, edd = tables(et, [c for c in et.combo.unique()])
        ett.to_pickle("et_ten.pkl"); edd.to_pickle("et_dd.pkl")
        print(ett[cols].to_string())
        print(edd[["combo", "最大回撤", "最差三次回撤平均", "最長回撤期筆數", "最長回撤期日曆日", "需註記"]].to_string())
    except FileNotFoundError:
        pass
