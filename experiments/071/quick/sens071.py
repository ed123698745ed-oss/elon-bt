"""071 快篩補充：0050 2008-10-16 跳動旗標（3.5% 跌幅期間規則推算跌停 39.16，官方成交 39.15，差一檔）造成 2008Q4 放空腿列未完成；
此表把該季放空腿照實計算（不改共用資料層），只作對照，不取代主表。"""
import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/elon-bt")
from framework.core import actions_from_table, trade_return
from elon_tools import load_bt_stats, ten_table, dd_table
import sim071 as S
bt = load_bt_stats("共用統計函式_bt_stats_v1.2.py")
P = pd.read_pickle("periods071.pkl")
j = S.J50
rows = []
for idx in P.index[P.short_excl.notna()]:
    r = P.loc[idx]
    a = S.dates.get_loc(r.entry_date); b = S.first_mark(S.dates.get_loc(r.exit_date), j)
    tr = trade_return("short", S.M["O"][a, j], S.M["O"][b, j], S.dates[a], S.dates[b], actions_from_table(S.ca, "0050"), "open", "open")
    P.loc[idx, "S"] = tr.ret
    h = S.COMBOS[r.combo]["h"]
    P.loc[idx, "R"] = 0.7 * r.L + h * tr.ret if h > 0 else 0.7 * r.L
    rows.append((r.combo, r.entry_date.date(), tr.ret))
print(pd.DataFrame(rows, columns=["combo", "entry", "S"]).drop_duplicates("entry"))
import stats071 as ST  # noqa: 只借用 as_trades
m = ST.as_trades(P, "R", "Q"); m = m[m.excluded_reason.isna()]
t = ten_table(m, bt, by=("combo",)); d = dd_table(m, bt, by=("combo",))
t.to_pickle("sens_ten.pkl"); d.to_pickle("sens_dd.pkl")
pd.set_option("display.width", 300)
print(t[["combo", "樣本數", "平均報酬", "勝率", "賠率R", "凱利", "標準差", "t值", "雙尾p"]].to_string())
