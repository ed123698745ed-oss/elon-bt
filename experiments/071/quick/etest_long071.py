"""071 E-Test（討論衍生，只用樣本內）：純做多、不避險、100% 資金做多，報酬＝多方等權期報酬 L。
Ed 2026-11-12 18:32「純做多的版本，不要避險 年化就用做多的那份資金算」。組合沿用快篩與減少持股 E-Test 已測的多方設定。"""
import pandas as pd
from elon_tools import load_bt_stats, ten_table, dd_table
import stats071 as ST
bt = load_bt_stats("共用統計函式_bt_stats_v1.2.py")
P = pd.read_pickle("periods071.pkl"); E = pd.read_pickle("etest_periods.pkl")
E = E[E.combo.str.endswith("|h30")].copy(); E["combo"] = E.combo.str.replace("|h30", "", regex=False)
P = P[~P.combo.isin(["V-H0", "V-H50", "V-H70"])]           # 這三組多方與 H1 相同
A = pd.concat([P, E], ignore_index=True)
A["combo"] = "L100|" + A.combo.replace({"H1": "原版20%"})
t = ST.as_trades(A, "L", "L"); t["is_etest"] = True
u = t[t.excluded_reason.isna()]
order = list(dict.fromkeys(A.combo))
tt = ten_table(u, bt, by=("combo",)).set_index("combo").reindex(order).reset_index()
tt["Holm p"] = tt.combo.map(ST.holm(tt.set_index("combo")["雙尾p"]))
dd = dd_table(u, bt, by=("combo",)).set_index("combo").reindex(order).reset_index()
tt["平均持股"] = tt.combo.map(A.groupby("combo").n_sel.mean())
tt.to_pickle("etest_long_ten.pkl"); dd.to_pickle("etest_long_dd.pkl")
m = tt.merge(dd, on="combo")
for _, r in m.iterrows():
    print(r.combo, f"{r.平均持股:.0f}", int(r.樣本數), f"{r.平均報酬*100:.2f}%", f"{r.平均持有交易日數:.1f}", f"{r.單利年化*100:.2f}%",
          f"{r.勝率*100:.1f}%", f"{r.賠率R:.2f}", f"{r.凱利:.3f}", f"{r.標準差*100:.2f}%", f"{r.t值:.2f}", f"{r.雙尾p:.4f}",
          f"{r['Holm p']:.3f}", f"{r.最大回撤*100:.1f}%", f"{r.最差三次回撤平均*100:.1f}%", f"{int(r.最長回撤期筆數)}季({int(r.最長回撤期日曆日)}天)")
