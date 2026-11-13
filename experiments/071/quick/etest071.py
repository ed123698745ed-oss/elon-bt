"""071 E-Test（討論衍生，只用樣本內）：減少持股檔數。Ed 2026-11-12 12:22「持股有辦法減少嗎」。
事前固定網格：持股上限 N∈{10,20,30,50}（原版低淨值比 20% 名單內，依淨值比由低到高取 N 檔）×
濾網 {無, 前20日均額≥2,000萬, 品質（官方本益比有值）, 品質＋≥2,000萬}，共 16 組；
空方 h＝0.3（原版）與 h＝0（純多 70%）各算一次，共 32 列；Holm 家族＝32 列、以雙尾 p 為輸入。其餘規則同 sim071.py。"""
import pickle
import numpy as np, pandas as pd
import sim071 as S
from elon_tools import load_bt_stats, ten_table, dd_table
import stats071 as ST

bt = load_bt_stats("共用統計函式_bt_stats_v1.2.py")
GRID = {}
for n in (10, 20, 30, 50):
    for f, kw in (("無", {}), ("均額2000萬", dict(liq=2e7)), ("品質", dict(qual=True)), ("品質+均額2000萬", dict(liq=2e7, qual=True))):
        GRID[f"N{n}|{f}"] = dict(q=0.20, h=0.30, top=n, **kw)
P = []
for name, p in GRID.items():
    periods, _, cancels, nsel = S.run(name, p)
    P += periods
    print(name, "平均檔數", round(np.mean([x[1] for x in nsel]), 1), "最少", min(x[1] for x in nsel), flush=True)
P = pd.DataFrame(P)
P0 = P.copy(); P0["R"] = 0.7 * P0["L"]; P0["combo"] = P0.combo + "|h0"
P["combo"] = P.combo + "|h30"
A = pd.concat([P, P0], ignore_index=True)
t = ST.as_trades(A, "R", "E"); t["is_etest"] = True
u = t[t.excluded_reason.isna()]
order = list(dict.fromkeys(A.combo))
tt = ten_table(u, bt, by=("combo",)).set_index("combo").reindex(order).reset_index()
tt["Holm p"] = tt.combo.map(ST.holm(tt.set_index("combo")["雙尾p"]))
dd = dd_table(u, bt, by=("combo",)).set_index("combo").reindex(order).reset_index()
ns = A.groupby("combo").n_sel.mean()
tt["平均持股"] = tt.combo.map(ns)
tt.to_pickle("etest_ten.pkl"); dd.to_pickle("etest_dd.pkl"); A.to_pickle("etest_periods.pkl")
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 30)
print(tt[["combo", "平均持股", "樣本數", "平均報酬", "平均持有交易日數", "單利年化", "勝率", "賠率R", "凱利", "標準差", "t值", "雙尾p", "Holm p"]].to_string())
print(dd[["combo", "最大回撤", "最差三次回撤平均", "最長回撤期筆數", "最長回撤期日曆日"]].to_string())
