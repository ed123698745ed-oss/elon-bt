"""068 快篩：資料準備（只讀到樣本內切點 2022-06-30，樣本外資料不載入）。
輸出 mats068.npz（日期×股票矩陣）與 meta068.pkl。
資料：elon-bt data-20261105r68（daily_k、calendar、listing_periods、corp_actions）；
      fin-20261107（未送驗收）financials（FinMind 現行值，時點未驗證）；
      data-phase2-20261110c3（待驗收）index_daily（加權指數）、fulldelivery（證交所變更交易名單）；
      月營收：revinst-20261111 month_revenue（FinMind 現行值，未驗收；只用營收月份 ≤2022-05）。
決策：D-068-20261104-1938-1、D-068-20261104-1947-1、D-068-20261111-0018-1～7。
"""
import glob, gzip, json, os, sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/elon-bt")
from framework.data import load, data_tags_used

IS_END = pd.Timestamp("2022-06-30")
cal = load("calendar")
dates = pd.DatetimeIndex(sorted(pd.to_datetime(cal["date"]).unique()))
dates = dates[dates <= IS_END]
T = len(dates)

k = load("daily_k", columns=["date", "stock_id", "open", "high", "low", "close", "volume", "amount",
                             "no_trade", "prev_close", "ref_price", "limit_src", "limit_up", "limit_down", "jump_flag"])
k = k[k["date"] <= IS_END]
sid = k["stock_id"]
common = sid.str.fullmatch(r"[1-9]\d{3}") & ~sid.str.startswith("91")   # 普通股：四碼、非 0 開頭、非 91xx 存託憑證
k = k[common & k["date"].isin(dates)].copy()
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
O, H, L, C = mat("open"), mat("high"), mat("low"), mat("close")
AMT = mat("amount", 0.0)
notrade = np.ones((T, N), bool); notrade[r, c] = k["no_trade"].fillna(True).to_numpy().astype(bool) | ~(k["volume"].to_numpy() > 0)
LU, LD = mat("limit_up"), mat("limit_down")
ls = k["limit_src"].fillna("").astype(str)
badlim = np.zeros((T, N), bool); badlim[r, c] = (ls.str.startswith("待查") | (ls == "缺參考價")).to_numpy()
nolim = np.zeros((T, N), bool); nolim[r, c] = ls.str.startswith("無漲跌幅").to_numpy()
JUMP = np.zeros((T, N), bool); JUMP[r, c] = k["jump_flag"].fillna(False).to_numpy().astype(bool)
PC, REF = mat("prev_close"), mat("ref_price")
# 時點一致調整因子（E-Test M1-ADJ）：參考價≠前收（公司行動日）時 f=ref/prev_close，累積 F；調整價＝收盤/F，只用當日以前資訊
f = np.where(np.isfinite(REF) & np.isfinite(PC) & (PC > 0) & (np.abs(REF - PC) > 1e-9), REF / PC, 1.0)
# r68 在減資／面額變更恢復買賣日的 ref_price 仍是停止買賣前收盤（退回-69 ④，r72 才修正）：
# 當日 daily_k 參考價＝前收、但 corp_actions 有換股比≠1 或現金時，改用 corp_actions 推得 f＝((前收−每股現金)÷換股比)÷前收
ca0 = load("corp_actions")
ca0 = ca0[ca0["stock_id"].isin(stocks)].copy()
ca0["date"] = pd.to_datetime(ca0["ex_date"])
ca0 = ca0[ca0["date"].isin(dates)]
ca0["bad"] = ca0["share_ratio"].isna() | ca0["cash"].isna()
agg = ca0.groupby(["stock_id", "date"]).agg(ratio=("share_ratio", lambda x: float(np.prod(x.fillna(1.0)))),
                                            cash=("cash", lambda x: float(x.fillna(0.0).sum())), bad=("bad", "any"),
                                            kinds=("kind", lambda x: "、".join(x))).reset_index()
F_FIX = []
for row in agg.itertuples():
    i, j = di[row.date], si[row.stock_id]
    if row.bad or abs(f[i, j] - 1.0) > 1e-12 or not (np.isfinite(PC[i, j]) and PC[i, j] > 0):
        continue
    if abs(row.ratio - 1.0) < 1e-12 and row.cash == 0:
        continue
    ff = ((PC[i, j] - row.cash) / row.ratio) / PC[i, j]
    if np.isfinite(ff) and ff > 0:
        f[i, j] = ff
        F_FIX.append((row.stock_id, row.date.date().isoformat(), row.kinds, row.ratio, row.cash, PC[i, j], ff))
F = np.cumprod(f, axis=0)
# 同一批減資恢復日的漲跌停價：r68 以停止買賣前收盤推算（錯），改以 corp_actions 推得的恢復參考價依規則推算（elon_tools.limit_prices）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elon_tools import limit_prices
for sid_, dstr, _k, _r, _c, pc_, ff in F_FIX:
    i, j = di[pd.Timestamp(dstr)], si[sid_]
    up, dn = limit_prices(round(pc_ * ff, 2), dstr)
    LU[i, j], LD[i, j] = up, dn
    nolim[i, j] = False
CT = np.where(present & ~notrade, C, np.nan)        # 有成交日的收盤價（無成交＝無收盤價，D-068-…-0018-5）
CADJ = CT / F

# 掛牌（官方逐日市場別區段，listing_periods 唯一入口）
lp = load("listing_periods")
lp = lp[lp["market"].isin(["上市", "上櫃"]) & lp["stock_id"].isin(stocks)]
listed = np.zeros((T, N), bool)
for row in lp.itertuples():
    a = dates.searchsorted(pd.Timestamp(row.start)); b = dates.searchsorted(pd.Timestamp(row.end), side="right")
    if b > a:
        listed[a:b, si[row.stock_id]] = True

# 證交所變更交易（全額交割）名單：2004-12-24 起，僅上市（上櫃全額交割名單資料層未含，列限制）
fd = load("fulldelivery", allow_candidate=True)
fd = fd[fd["code"].isin(stocks)].copy()
fd["date"] = pd.to_datetime(fd["date"])
fd = fd[fd["date"].isin(dates)]
FULLD = np.zeros((T, N), bool)
FULLD[di[fd["date"]].to_numpy(), si[fd["code"]].to_numpy()] = True

# 加權指數 20 日均線
ix = load("index_daily", allow_candidate=True)
ix["date"] = pd.to_datetime(ix["date"]); ix = ix.set_index("date").reindex(dates)
tc = ix["taiex_close"]
ma20 = tc.rolling(20, min_periods=20).mean()
mkt_ok = (tc >= ma20).to_numpy()
mkt_has = (ma20.notna() & tc.notna()).to_numpy()

# 前 20 個市場交易日平均成交金額（含訊號日，無成交日計 0）
AMT0 = np.where(present & ~notrade, np.nan_to_num(AMT), 0.0)
cs = np.cumsum(AMT0, axis=0)
ADV20 = np.full((T, N), np.nan)
ADV20[19:] = (cs[19:] - np.vstack([np.zeros((1, N)), cs[:-20]])) / 20

# 換股日：每月最後一個市場交易日；雙週＝ISO 雙數週最後一個市場交易日（D-068-…-0018-3）
ym = dates.year * 100 + dates.month
rebal_m = np.r_[ym[1:] != ym[:-1], True]
iso = dates.isocalendar()
wk = (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()
rebal_2w = np.r_[wk[1:] != wk[:-1], True] & (iso["week"].to_numpy().astype(int) % 2 == 0)
rebal_m[-1] = rebal_2w[-1] = False     # 資料最後一日（樣本內切點）之後無次一交易日，不換股


def avail_index(deadline):
    """法定期限（遇非交易日順延至次一交易日）之次一交易日起可用（D-068-…-0018-2）；回傳 dates 中的索引，超出回傳 T。"""
    dl = dates.searchsorted(pd.Timestamp(deadline))       # 期限日或順延後的交易日
    return dl + 1


# 財報：歸屬母公司淨利（單季）與歸屬母公司權益（D-068-…-0018-4）
fin = load("financials", allow_candidate=True)
fin = fin[(fin["date"] >= "2012-03-31") & (fin["date"] <= "2022-03-31") & fin["stock_id"].isin(stocks)]
inc = fin[fin["dataset"] == "TaiwanStockFinancialStatements"].pivot_table(index=["stock_id", "date"], columns="type", values="value", aggfunc="first")
bs = fin[fin["dataset"] == "TaiwanStockBalanceSheet"].pivot_table(index=["stock_id", "date"], columns="type", values="value", aggfunc="first")
ni_par, ni_tot = inc.get("EquityAttributableToOwnersOfParent"), inc.get("IncomeAfterTaxes")
nci = inc.get("NoncontrollingInterests")
# 無非控制權益拆分（FinMind 未列歸屬母公司欄、也未列非控制權益）時，本期淨利即歸屬母公司淨利
no_split = ni_par.isna() & (nci.isna() | (nci.fillna(0) == 0))
NI = ni_par.where(ni_par.notna(), ni_tot.where(no_split))
NI_src = pd.Series(np.where(ni_par.notna(), "歸屬母公司", np.where(NI.notna(), "本期淨利（無非控制權益拆分）", "資料不足")), index=NI.index)
eq_par, eq_tot = bs.get("EquityAttributableToOwnersOfParent"), bs.get("Equity")
nci_eq = bs.get("NoncontrollingInterests")
EQ = eq_par.where(eq_par.notna(), eq_tot.where(eq_par.isna() if nci_eq is None else (eq_par.isna() & (nci_eq.isna() | (nci_eq.fillna(0) == 0)))))
EQ_src = pd.Series(np.where(eq_par.notna(), "歸屬母公司", np.where(EQ.notna(), "權益總額（無非控制權益拆分）", "資料不足")), index=EQ.index)
fq = pd.DataFrame({"NI": NI, "NI_src": NI_src}).join(pd.DataFrame({"EQ": EQ, "EQ_src": EQ_src}), how="outer").reset_index()
fq["date"] = pd.to_datetime(fq["date"])
fq = fq[fq["date"].dt.year >= 2013]           # IFRS 起（D-068-20261104-1947-1②）；2012 年 ROC GAAP 不用

QEND = sorted(fq["date"].unique())
qpos = {d: n for n, d in enumerate(QEND)}


def deadline_of(qe):
    y, m = qe.year, qe.month
    return {3: f"{y}-05-15", 6: f"{y}-08-14", 9: f"{y}-11-14", 12: f"{y + 1}-03-31"}[m]


NIq = np.full((len(QEND), N), np.nan); EQq = np.full((len(QEND), N), np.nan)
q_i = fq["date"].map(qpos).to_numpy(); s_i = si[fq["stock_id"]].to_numpy()
NIq[q_i, s_i] = fq["NI"].to_numpy(float); EQq[q_i, s_i] = fq["EQ"].to_numpy(float)
# 近四季淨利合計（四季皆有才算）
NI4 = np.full_like(NIq, np.nan)
for n in range(3, len(QEND)):
    blk = NIq[n - 3:n + 1]
    # 四個季末必須連續（QEND 為完整季序列）
    NI4[n] = np.where(np.isfinite(blk).all(axis=0), blk.sum(axis=0), np.nan)
q_avail = np.array([avail_index(deadline_of(pd.Timestamp(q))) for q in QEND])
# 每個交易日可用的最近一季（以期限判定，不看個別公司實際公告日）
cur_q = np.full(T, -1)
for n, a in enumerate(q_avail):
    if a < T:
        cur_q[a:] = n
ROE_Q_POS = np.zeros((T, N), bool); ROE4_GT8 = np.zeros((T, N), bool); FIN_MISS = np.zeros((T, N), bool)
ROE4_MISS = np.zeros((T, N), bool); HAS_FIN = np.zeros(T, bool); HAS_FIN4 = np.zeros(T, bool)
for i in range(T):
    n = cur_q[i]
    if n < 0:
        continue
    HAS_FIN[i] = True
    ni, eq = NIq[n], EQq[n]
    ok = np.isfinite(ni) & np.isfinite(eq)
    FIN_MISS[i] = ~ok
    ROE_Q_POS[i] = ok & (ni > 0) & (eq > 0)
    if n >= 3:
        HAS_FIN4[i] = True
        n4 = NI4[n]
        ok4 = np.isfinite(n4) & np.isfinite(eq)
        ROE4_MISS[i] = ~ok4
        ROE4_GT8[i] = ok4 & (eq > 0) & (n4 / np.where(eq > 0, eq, np.nan) > 0.08)

# 月營收：最近一個可用月份（次月 10 日期限之次一交易日起可用）的年增 > 0
REV_YOY_POS = np.zeros((T, N), bool); REV_MISS = np.ones((T, N), bool); rev_rows = []
# 月營收：共用資料層 revinst-20261111 month_revenue.parquet（FinMind 現行值，未驗收；D-068-20261111-0055-1）
# 載入當下即只留營收月份 ≤ 2022-05（樣本內切點前可得者），樣本外月份不進記憶體後續流程
REV_PATH = "/tmp/dl_revinst/month_revenue.parquet"   # sha256 5fd58c5e8d29d434927ca6f00fc0a05d6e4300492c4988705954076e6fb38e7a
rev = pd.read_parquet(REV_PATH)
rev = rev[(rev["revenue_year"] * 100 + rev["revenue_month"]) <= 202205]
rev = rev.rename(columns={"revenue_year": "y", "revenue_month": "m"})[["stock_id", "y", "m", "revenue", "date"]]
rev["y"] = rev["y"].astype(int); rev["m"] = rev["m"].astype(int); rev["revenue"] = rev["revenue"].astype(float)
files = [REV_PATH]
rev = rev[rev["stock_id"].isin(stocks)].drop_duplicates(["stock_id", "y", "m"], keep="last")
months = pd.period_range("2011-01", "2022-05", freq="M")
mpos = {(p.year, p.month): n for n, p in enumerate(months)}
REVm = np.full((len(months), N), np.nan)
rk = [mpos.get((a, b), -1) for a, b in zip(rev["y"], rev["m"])]
rv = rev.assign(_k=rk)
rv = rv[rv["_k"] >= 0]
if len(rv):
    REVm[rv["_k"].to_numpy(), si[rv["stock_id"]].to_numpy()] = rv["revenue"].to_numpy(float)
m_avail = np.array([avail_index((p + 1).start_time + pd.Timedelta(days=9)) for p in months])
cur_m = np.full(T, -1)
for n, a in enumerate(m_avail):
    if a < T:
        cur_m[a:] = n
for i in range(T):
    n = cur_m[i]
    if n < 12:
        continue
    a, b = REVm[n], REVm[n - 12]
    okk = np.isfinite(a) & np.isfinite(b) & (b > 0)
    REV_MISS[i] = ~okk
    REV_YOY_POS[i] = okk & (a / np.where(b > 0, b, np.nan) - 1 > 0)

ca = load("corp_actions")
ca = ca[ca["stock_id"].isin(stocks)].copy()

np.savez_compressed("mats068.npz", present=present, O=O, H=H, L=L, C=C, CT=CT, CADJ=CADJ, notrade=notrade,
                    LU=LU, LD=LD, badlim=badlim, nolim=nolim, JUMP=JUMP, listed=listed, FULLD=FULLD,
                    mkt_ok=mkt_ok, mkt_has=mkt_has, ADV20=ADV20, rebal_m=rebal_m, rebal_2w=rebal_2w, F=F,
                    ROE_Q_POS=ROE_Q_POS, ROE4_GT8=ROE4_GT8, FIN_MISS=FIN_MISS, ROE4_MISS=ROE4_MISS, HAS_FIN=HAS_FIN,
                    HAS_FIN4=HAS_FIN4, REV_YOY_POS=REV_YOY_POS, REV_MISS=REV_MISS, cur_q=cur_q, cur_m=cur_m)
pickle.dump({"dates": dates, "stocks": stocks, "ca": ca, "tags": data_tags_used(), "QEND": QEND, "q_avail": q_avail,
             "months": months, "m_avail": m_avail, "rev_files": len(files), "rev_rows": len(rev),
             "ni_src": NI_src.value_counts().to_dict(), "eq_src": EQ_src.value_counts().to_dict(), "F_FIX": F_FIX},
            open("meta068.pkl", "wb"))
print(T, N, rebal_m.sum(), rebal_2w.sum(), len(files), data_tags_used())
