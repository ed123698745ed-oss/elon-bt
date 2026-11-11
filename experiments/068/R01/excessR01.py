"""068 R01 描述性：相對加權報酬指數的近似超額報酬（只供判讀，不是策略卡指標）。
基準＝taiex_tri_close（c5），區間取進場日前一交易日收盤→出場日前一交易日收盤（個股為開盤進出，指數無開盤報酬指數，故為近似超額，防錯 C4）。
"""
import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/elon-bt")
from framework.data import load
from elon_tools import load_bt_stats, ten_table

bt = load_bt_stats("bt_stats_v1.2.py")
ix = load("index_daily", tag="data-phase2-20261111c5"); ix["date"] = pd.to_datetime(ix["date"])
tri = ix.set_index("date")["taiex_tri_close"].dropna()
d = tri.index


def prev_close(day):
    k = d.searchsorted(pd.Timestamp(day)) - 1
    return tri.iloc[k]


rows = []
for f in ("tradesR01.pkl", "etradesR01.pkl"):
    t = pd.read_pickle(f)
    u = t[t["excluded_reason"].isna() & t["sample"].isin(["樣本內", "樣本外"])].copy()
    u["bench"] = [prev_close(b) / prev_close(a) - 1 for a, b in zip(u.entry_date, u.exit_date)]
    u["ret_raw"] = u["ret"]; u["ret"] = u["ret_raw"] - u["bench"]
    tt = ten_table(u, bt, by=("combo", "sample"), cluster_unit="進場日")
    tt["基準平均"] = u.groupby(["combo", "sample"], sort=False)["bench"].mean().values
    rows.append(tt)
X = pd.concat(rows, ignore_index=True)
X.to_pickle("R01_excess.pkl")
pd.set_option("display.width", 250)
print(X[["combo／sample", "樣本數", "平均報酬", "基準平均", "勝率", "t值", "聚合p"]].to_string())
