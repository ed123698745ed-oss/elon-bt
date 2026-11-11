"""071 快篩：資料準備（只讀到樣本內／隔離帶第一個交易日 2020-07-01；樣本外資料不載入）。

資料（elon-bt 共用資料層）：
  data-20261110r72（已驗收）daily_k、calendar、listing_periods、corp_actions
  data-phase2-20261111c5（已驗收）fulldelivery、margin_flags、downtick_list
  pbr-20261112m（未送驗收；官方每日本益比／殖利率／股價淨值比，D-071-20261111-2354-1）valuation_daily
決策：D-071-20261104-1938-1、1947-1；D-071-20261111-2354-1～5。切點凍結：071_切點凍結紀錄_sha256-5daf3f5f.json。
"""
import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/elon-bt")
from framework.data import load, data_tags_used

LAST = pd.Timestamp("2020-07-01")          # 隔離帶第一個交易日（樣本內最後一季開盤出場日）
START = pd.Timestamp("2008-03-01")         # ADV20 需前 20 個交易日；研究起點 2008-04-09（D-071-…-2354-2）
RESEARCH_START = pd.Timestamp("2008-04-09")

cal = load("calendar")
dates = pd.DatetimeIndex(sorted(pd.to_datetime(cal["date"]).unique()))
dates = dates[(dates >= START) & (dates <= LAST)]
T = len(dates)
k = load("daily_k", columns=["date", "stock_id", "open", "close", "volume", "amount", "no_trade",
                             "limit_src", "limit_up", "limit_down", "jump_flag"])
k = k[(k["date"] >= START) & (k["date"] <= LAST) & k["date"].isin(dates)]
sid = k["stock_id"]
common = sid.str.fullmatch(r"[1-9]\d{3}") & ~sid.str.startswith("91")
k = k[common | (sid == "0050")].copy()
stocks = np.array(sorted(k["stock_id"].unique()))
N = len(stocks)
di = pd.Series(np.arange(T), index=dates)
si = pd.Series(np.arange(N), index=stocks)
r = di[k["date"]].to_numpy(); c = si[k["stock_id"]].to_numpy()


def mat(col, fill=np.nan, dtype=float):
    m = np.full((T, N), fill, dtype=dtype)
    m[r, c] = k[col].to_numpy(dtype=dtype)
    return m


present = np.zeros((T, N), bool); present[r, c] = True
O, C, AMT = mat("open"), mat("close"), mat("amount", 0.0)
notrade = np.ones((T, N), bool)
notrade[r, c] = k["no_trade"].fillna(True).to_numpy().astype(bool) | ~(k["volume"].to_numpy() > 0)
LU, LD = mat("limit_up"), mat("limit_down")
ls = k["limit_src"].fillna("").astype(str)
badlim = np.zeros((T, N), bool); badlim[r, c] = (ls.str.startswith("待查") | (ls == "缺參考價")).to_numpy()
nolim = np.zeros((T, N), bool); nolim[r, c] = ls.str.startswith("無漲跌幅").to_numpy()
JUMP = np.zeros((T, N), bool); JUMP[r, c] = k["jump_flag"].fillna(False).to_numpy().astype(bool)

# 掛牌（官方逐日市場別區段）
lp = load("listing_periods")
lp = lp[lp["market"].isin(["上市", "上櫃"]) & lp["stock_id"].isin(stocks)]
listed = np.zeros((T, N), bool)
for row in lp.itertuples():
    a = dates.searchsorted(pd.Timestamp(row.start)); b = dates.searchsorted(pd.Timestamp(row.end), side="right")
    if b > a:
        listed[a:b, si[row.stock_id]] = True

# 變更交易（全額交割）／管理股票：上市 2004-12-24 起、上櫃 2008-04-09 起（A14）
fd = load("fulldelivery")
FD_RANGE = fd.groupby("market")["date"].agg(["min", "max"]).astype(str).to_dict("index")
fd = fd[fd["code"].isin(stocks)].copy()
fd["date"] = pd.to_datetime(fd["date"])
fd = fd[fd["date"].isin(dates)]
FULLD = np.zeros((T, N), bool)
FULLD[di[fd["date"]].to_numpy(), si[fd["code"]].to_numpy()] = True

# 前 20 個市場交易日平均成交金額（含訊號日，無成交日計 0）
AMT0 = np.where(present & ~notrade, np.nan_to_num(AMT), 0.0)
cs = np.cumsum(AMT0, axis=0)
ADV20 = np.full((T, N), np.nan)
ADV20[19:] = (cs[19:] - np.vstack([np.zeros((1, N)), cs[:-20]])) / 20

# 官方每日淨值比、本益比（訊號日收盤後公布，次一交易日開盤可用）
v = load("valuation_daily", allow_candidate=True, columns=["date", "stock_id", "market", "pbr", "pe"])
v = v[(v["date"] >= START) & (v["date"] < LAST) & v["stock_id"].isin(stocks) & v["date"].isin(dates)]
v = v.drop_duplicates(["date", "stock_id"], keep="last")
PBR = np.full((T, N), np.nan); PE = np.full((T, N), np.nan)
rv, cv = di[v["date"]].to_numpy(), si[v["stock_id"]].to_numpy()
PBR[rv, cv] = v["pbr"].to_numpy(float); PE[rv, cv] = v["pe"].to_numpy(float)
vc = load("valuation_coverage", allow_candidate=True)
vc = vc[(vc["date"] >= RESEARCH_START) & (vc["date"] < LAST)]

# 換股日：每季／每月最後一個交易日（≥ 研究起點；最後一個訊號須有次一交易日）
ym = dates.year * 100 + dates.month
is_me = np.r_[ym[1:] != ym[:-1], False]
is_qe = is_me & np.isin(dates.month, [3, 6, 9, 12])
is_me &= dates >= RESEARCH_START; is_qe &= dates >= RESEARCH_START

# 0050 放空腿 L2：停券（margin_flags，effective 生效日）、平盤下不得融（借）券（downtick_list，2013-09-18 起）
mf = load("margin_flags")
mf = mf[(mf["code"] == "0050") & mf["stop_short"].astype(bool)]
STOP_SHORT = set(pd.to_datetime(mf["effective"]).dt.normalize())
dl = load("downtick_list")
dl50 = dl[dl["code"] == "0050"]
ca = load("corp_actions")
ca = ca[ca["stock_id"].isin(stocks)].copy()

np.savez_compressed("mats071.npz", present=present, O=O, C=C, notrade=notrade, LU=LU, LD=LD, badlim=badlim, nolim=nolim,
                    JUMP=JUMP, listed=listed, FULLD=FULLD, ADV20=ADV20, PBR=PBR, PE=PE, is_me=is_me, is_qe=is_qe)
pickle.dump({"dates": dates, "stocks": stocks, "ca": ca, "tags": data_tags_used(), "FD_RANGE": FD_RANGE,
             "STOP_SHORT": STOP_SHORT, "dl50": dl50, "vcov": vc}, open("meta071.pkl", "wb"))
print(T, N, "季換股", int(is_qe.sum()), "月換股", int(is_me.sum()), data_tags_used())
print(vc.groupby(["market", "status"]).size().to_string())
