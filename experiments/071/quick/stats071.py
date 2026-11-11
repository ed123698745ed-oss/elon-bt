"""071 快篩統計：只用樣本內；十項統計與回撤三項全部由 bt_stats 1.2（elon-backtest 技能 elon_tools）產出。
主表：一期組合報酬為一筆（無群聚，cluster_unit=None）；Holm 以雙尾 p 為輸入，家族＝優化組 9 組（不含原版 H1）。
拆解：多方持有段（聚合單位＝進場日）、多方期報酬、0050 放空腿期報酬。
"""
import pickle
import numpy as np, pandas as pd
from elon_tools import load_bt_stats, ten_table, dd_table, baseline_check

bt = load_bt_stats("共用統計函式_bt_stats_v1.2.py")
assert baseline_check(bt)
VARIANTS = ["V-P10", "V-P30", "V-H0", "V-H50", "V-H70", "V-MON", "V-TOP20", "V-LIQ", "V-QUAL"]


def holm(s):
    o = s.dropna().sort_values(); m = len(o); out = {}; run = 0.0
    for k, (nm, v) in enumerate(o.items()):
        run = max(run, min(1.0, (m - k) * v)); out[nm] = run
    return pd.Series(out)


P = pd.read_pickle("periods071.pkl")
order = list(dict.fromkeys(P.combo))


def as_trades(df, col, tag):
    t = pd.DataFrame({
        "trade_id": [f"{c}-{tag}{n+1:04d}" for n, c in enumerate(df.combo)], "combo": df.combo.values, "is_etest": False,
        "symbol": tag, "info_time": df.sig_date.dt.strftime("%Y-%m-%d 17:00").values,
        "entry_time": df.entry_date.dt.strftime("%Y-%m-%d 09:00").values,
        "entry_date": df.entry_date.dt.strftime("%Y-%m-%d").values, "entry_px": np.nan,
        "exit_date": df.exit_date.dt.strftime("%Y-%m-%d").values, "exit_px": np.nan,
        "ret": df[col].values, "hold_days": df.hold_days.values, "cluster": None, "sample": df["sample"].values,
        "excluded_reason": None})
    bad = ~np.isfinite(t["ret"].astype(float))
    t.loc[bad, "excluded_reason"] = "期報酬無法計算（腿報酬缺）"; t.loc[bad, "ret"] = np.nan
    t.loc[(t["sample"] != "樣本內") & ~bad, "excluded_reason"] = "跨越隔離帶，不列入任一段"
    t.loc[t["sample"] != "樣本內", "ret"] = np.nan
    return t


main = as_trades(P, "R", "Q")
u = main[main.excluded_reason.isna()]
tt = ten_table(u, bt, by=("combo",)).set_index("combo").reindex(order).reset_index()
tt["Holm p"] = tt.combo.map(holm(tt.set_index("combo").loc[VARIANTS, "雙尾p"]))
dd = dd_table(u, bt, by=("combo",)).set_index("combo").reindex(order).reset_index()

legL = as_trades(P, "L", "L"); legL = legL[legL.excluded_reason.isna()]
ttL = ten_table(legL, bt, by=("combo",)).set_index("combo").reindex(order).reset_index()
Pq = P[P.combo.isin(["H1", "V-MON"])]
legS = as_trades(Pq, "S", "S"); legS = legS[legS.excluded_reason.isna()]
legS["combo"] = legS.combo.map({"H1": "0050空方（季）", "V-MON": "0050空方（月）"})
ttS = ten_table(legS, bt, by=("combo",))

sg = pd.read_pickle("segs071.pkl"); sg["is_etest"] = False
sg["info_time"] = sg["signal_date"] + " 17:00"; sg["entry_time"] = sg["entry_date"] + " 09:00"
ug = sg[sg.excluded_reason.isna() & (sg["sample"] == "樣本內")]
ttG = ten_table(ug, bt, by=("combo",), cluster_unit="進場日").set_index("combo").reindex(order).reset_index()

# 描述性組合淨值（期報酬連乘，只供與 FinLab 對照）
nav = []
for c in order:
    g = u[u.combo == c].sort_values("entry_date")
    v = np.cumprod(1 + g.ret.astype(float).values)
    yrs = (pd.Timestamp(g.exit_date.iloc[-1]) - pd.Timestamp(g.entry_date.iloc[0])).days / 365.25
    peak = np.maximum.accumulate(np.r_[1.0, v])[1:]
    ns = P[(P.combo == c) & (P["sample"] == "樣本內")].n_sel
    nav.append(dict(combo=c, 年化=v[-1] ** (1 / yrs) - 1, 期末回撤最大=(v / peak - 1).min(), 平均持股數=ns.mean(),
                    最少持股=ns.min(), 期末淨值=v[-1]))
nav = pd.DataFrame(nav)
for nm, d in [("card_ten", tt), ("card_dd", dd), ("legL", ttL), ("legS", ttS), ("seg", ttG), ("nav", nav)]:
    d.to_pickle(f"{nm}.pkl")
main.to_pickle("main071.pkl"); sg.to_pickle("segs071_full.pkl")
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
cols = ["combo", "樣本數", "平均報酬", "平均持有交易日數", "單利年化", "勝率", "賠率R", "凱利", "標準差", "t值", "雙尾p", "Holm p"]
print(tt[cols].to_string()); print(dd[["combo", "最大回撤", "最差三次回撤平均", "最長回撤期筆數", "最長回撤期日曆日", "最長回撤期未回復"]].to_string())
print(ttL[cols[:-1]].to_string()); print(ttS[cols[:-1]].to_string())
print(ttG[cols[:-1] + ["聚合單位數", "聚合p"]].to_string()); print(nav.to_string())
print(P[P["sample"] == "樣本內"].groupby("combo")[["n_cancel", "n_excl"]].sum().to_string())
print("0050 旗標", P["flags"].dropna().unique(), "放空腿缺", P.short_excl.dropna().unique())
