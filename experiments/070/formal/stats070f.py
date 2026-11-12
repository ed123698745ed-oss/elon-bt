"""070 R01 統計：策略卡 11 組（樣本內／樣本外並列）＋E-Test 27 組（樣本內全揭露，依 freeze_etest.json 挑選後只對被選組開樣本外）。
十項統計與回撤三項全部由 bt_stats 1.2（elon-backtest 技能 elon_tools）產出；聚合單位＝進場日；Holm 以聚合 p 為輸入。
"""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "."); sys.path.insert(0, "/home/claude/elon-bt")
from elon_tools import load_bt_stats, ten_table, dd_table, baseline_check

bt = load_bt_stats("/root/btstats/bt_stats_v1.2.py")
assert baseline_check(bt)


def holm(s):
    o = s.dropna().sort_values(); m = len(o); out = {}; run = 0.0
    for k, (nm, v) in enumerate(o.items()):
        run = max(run, min(1.0, (m - k) * v)); out[nm] = run
    return pd.Series(out)


def prep(t, etest):
    t = t.copy(); t["is_etest"] = etest
    t["info_time"] = t["signal_date"] + " 14:30"; t["entry_time"] = t["entry_date"] + " 09:00"
    return t


card = prep(pd.read_pickle("trades070.pkl"), False)
et = prep(pd.read_pickle("trades070_etest.pkl"), True)
order_c = list(dict.fromkeys(card.combo)); order_e = list(dict.fromkeys(et.combo))

# ---- 策略卡組合：樣本內、樣本外並列 ----
cs = card[card["sample"].isin(["樣本內", "樣本外"])]
card_ten = ten_table(cs, bt, by=("combo", "sample"), cluster_unit="進場日")
card_dd = dd_table(cs, bt, by=("combo", "sample"))
key = card_ten.columns[0]
for smp in ("樣本內", "樣本外"):
    sel = card_ten[key].str.endswith("｜" + smp)
    fam = card_ten[sel & ~card_ten[key].str.startswith("Q1｜")].set_index(key)["聚合p"]
    card_ten.loc[sel, "Holm聚合p"] = card_ten.loc[sel, key].map(holm(fam))

# ---- E-Test：樣本內 27 組 ----
ei = et[et["sample"] == "樣本內"]
e_ten = ten_table(ei, bt, by=("combo",), cluster_unit="進場日").set_index("combo").reindex(order_e).reset_index()
e_ten["Holm聚合p"] = e_ten.combo.map(holm(e_ten.set_index("combo")["聚合p"]))
e_dd = dd_table(ei, bt, by=("combo",)).set_index("combo").reindex(order_e).reset_index()

# ---- 依凍結規則挑選（freeze_etest.json；只看樣本內）----
g = e_ten.set_index("combo")
NS, LS = [5, 10, 20], [0, 1000, 2000]
picked = {}
for sch in ("M", "Q", "B"):
    def nm(n, l): return f"E-{sch}-N{n}-L{l}"
    elig = {(n, l): (g.loc[nm(n, l), "樣本數"] >= 100) and (g.loc[nm(n, l), "聚合p"] < 0.05) for n in NS for l in LS}
    stable = []
    for a, n in enumerate(NS):
        for b, l in enumerate(LS):
            nb = [(NS[a + d], l) for d in (-1, 1) if 0 <= a + d < 3] + [(n, LS[b + d]) for d in (-1, 1) if 0 <= b + d < 3]
            if elig[(n, l)] and all(elig[x] for x in nb):
                stable.append((n, l))
    if stable:
        best = sorted(stable, key=lambda x: (-g.loc[nm(*x), "單利年化"], -x[0], -x[1]))[0]
        picked[sch] = nm(*best)
    else:
        picked[sch] = None
picks = [v for v in picked.values() if v]
eo = et[et["sample"] == "樣本外"]
eo = eo[eo.combo.isin(picks)]
e_oos = ten_table(eo, bt, by=("combo",), cluster_unit="進場日") if len(eo) else pd.DataFrame()
e_oos_dd = dd_table(eo, bt, by=("combo",)) if len(eo) else pd.DataFrame()

for nm_, df in [("card_ten", card_ten), ("card_dd", card_dd), ("e_ten", e_ten), ("e_dd", e_dd), ("e_oos", e_oos), ("e_oos_dd", e_oos_dd)]:
    df.to_pickle(f"{nm_}.pkl")
json.dump(picked, open("etest_picked.json", "w"), ensure_ascii=False)
card.to_pickle("trades070_full.pkl"); et.to_pickle("trades070_etest_full.pkl")
print("picked:", picked)
