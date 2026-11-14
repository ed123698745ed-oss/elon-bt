"""070 R01 敏感度測試（手冊 4-B；格點見 freeze_sens.json）。沿用 sim070f 的選股、成交與報酬函式，只改參數。"""
import sys, json, itertools
import pandas as pd
sys.path.insert(0, "."); sys.path.insert(0, "/home/claude/elon-bt")
import sim070f as S
from elon_tools import load_bt_stats, ten_table, dd_table

bt = load_bt_stats("/root/btstats/bt_stats_v1.2.py")
G = json.load(open("freeze_sens.json", encoding="utf-8"))["candidates_and_grids"]
BASE = {"V-LIQ2000萬": dict(pr=5, rev=4), "V-MERGE": dict(pr=3, rev=3, quarterly=True),
        "E-Q-N20-L0": dict(cap=100e8, rev=4, quarterly=True), "E-B-N20-L0": dict(cap=100e8, rev=4, buffer=True)}
KEYMAP = {"liq_元": "liq", "cap_元": "cap", "top": "top", "pr": "pr"}
rows = []
for cand, g in G.items():
    (k1, v1), (k2, v2) = list(g["vary"].items())
    for a, b in itertools.product(v1, v2):
        p = dict(BASE[cand]); p[KEYMAP[k1]] = a; p[KEYMAP[k2]] = b
        name = f"{cand}|{KEYMAP[k1]}={a:g}|{KEYMAP[k2]}={b:g}"
        r, _, _ = S.run(name, p)
        rows += S.finalize(r)
t = pd.DataFrame(rows)
t["is_etest"] = False
t["info_time"] = t["signal_date"] + " 14:30"; t["entry_time"] = t["entry_date"] + " 09:00"
t.to_pickle("trades070_sens.pkl")
ts = t[t["sample"].isin(["樣本內", "樣本外"])]
ten = ten_table(ts, bt, by=("combo", "sample"), cluster_unit="進場日")
ten.to_pickle("sens_ten.pkl")
print(len(G), "候選", t.combo.nunique(), "組")
