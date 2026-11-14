"""070 R01 交件前自檢（elon-backtest selfcheck）。"""
import sys, json
import pandas as pd
sys.path.insert(0, ".")
from elon_tools import load_bt_stats, selfcheck, print_check
import pickle
bt = load_bt_stats("/root/btstats/bt_stats_v1.2.py")
dates = pickle.load(open("meta070.pkl", "rb"))["dates"]
card = pd.read_pickle("trades070_full.pkl"); et = pd.read_pickle("trades070_etest_full.pkl")
picks = [v for v in json.load(open("etest_picked.json")).values() if v]
ct = pd.read_pickle("card_ten.pkl"); cd = pd.read_pickle("card_dd.pkl")
kw = dict(bt=bt, cluster_unit="進場日", calendar=list(dates), split=("2022-06-30", "2022-10-01"))
cs = card[card["sample"].isin(["樣本內", "樣本外"]) | card.excluded_reason.notna()]
print("== 策略卡 11 組"); ok1 = print_check(selfcheck(cs, reported=ct, reported_dd=cd, by=("combo", "sample"), **kw))
ei = et[(et["sample"] == "樣本內") | et.excluded_reason.notna()]
print("== E-Test 樣本內 27 組"); ok2 = print_check(selfcheck(ei, reported=pd.read_pickle("e_ten.pkl"), reported_dd=pd.read_pickle("e_dd.pkl"), by=("combo",), etest=True, **kw))
eo = et[(et["sample"] == "樣本外") & et.combo.isin(picks)]
print("== E-Test 樣本外 被選組"); ok3 = print_check(selfcheck(eo, reported=pd.read_pickle("e_oos.pkl"), reported_dd=pd.read_pickle("e_oos_dd.pkl"), by=("combo",), etest=True, **kw))

# ---- 防錯清單可程式化的額外檢查 ----
import numpy as np
M = dict(np.load("mats070.npz")); di = {d.date().isoformat(): k for k, d in enumerate(dates)}
stocks = pickle.load(open("meta070.pkl", "rb"))["stocks"]; si = {s: k for k, s in enumerate(stocks)}
allt = pd.concat([card, et, pd.read_pickle("trades070_sens.pkl")])
inc = allt[allt.excluded_reason.isna()]
touch = sum(M["JUMP"][di[r.entry_date]:di[r.exit_date] + 1, si[r.symbol]].any() for r in inc.itertuples())
print("A10 納入交易持有期間（含首尾）碰到跳動列筆數：", touch)
sig_i = inc.signal_date.map(di).to_numpy(); sj = inc.symbol.map(si).to_numpy()
print("A14 納入交易訊號日在全額交割／變更交易名單上的筆數：", int(M["FULLD"][sig_i, sj].sum()))
print("A14 訊號日早於上櫃名單起點 2008-04-09 的筆數：", int((inc.signal_date < "2008-04-09").sum()))
lab = np.where(pd.to_datetime(allt.signal_date) >= pd.Timestamp("2022-10-01"), "樣本外",
      np.where((pd.to_datetime(allt.signal_date) <= pd.Timestamp("2022-06-30")) & (pd.to_datetime(allt.exit_date) <= pd.Timestamp("2022-06-30")), "樣本內", "隔離帶"))
print("D7 文件謂詞與明細 sample 欄差異筆數（已完成出場者）：", int(((lab != allt["sample"]) & allt.exit_date.notna()).sum()))
s = inc.assign(_e=pd.to_datetime(inc.entry_date), _x=pd.to_datetime(inc.exit_date)).sort_values(["combo", "symbol", "_e"])
print("C7 同組合同股票前筆出場日 ≥ 下筆進場日的筆數：", int((s["_e"] <= s.groupby(["combo", "symbol"])["_x"].shift()).sum()))
print("A3 時點未驗證：財報 fin-20261114r2、現金流量 fincf-20261111、月營收 revinst-20261111 皆為 FinMind 現行修訂值 → 全部組合")
