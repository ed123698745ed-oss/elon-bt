"""070 正式策略包 R01：資料準備（全期，樣本外已依 D-070-20261112-1519-1 開啟）。
輸出 mats070.npz（日期×股票矩陣）與 meta070.pkl。

資料（elon-bt 共用資料層）：
  data-20261110r72（已驗收；正式策略包開工時 2026-11-12 的預設驗收標籤；之後 r73 驗收，依手冊不追溯）daily_k、calendar、listing_periods、corp_actions
  data-phase2-20261111c5（已驗收）fulldelivery（上市 2004-12-24 起、上櫃 2008-04-09 起）
  fin-20261114r2（未送驗收）financials（FinMind 現行值，時點未驗證）
  fincf-20261111（未送驗收）cashflow（同上）、industry（現行產業別）
  revinst-20261111（未送驗收）month_revenue（同上）
決策：D-070-20261104-1938-1、1947-1；D-070-20261111-1014-1～4、1424-1。
"""
import os, sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/elon-bt")
# 資料標籤在載入處顯式指定（手冊 V32 第 4 節第 3 點：進行中案件沿用開工時標籤；防錯 E7）
P1, P2, FIN, FINCF, REVI = "data-20261110r72", "data-phase2-20261111c5", "fin-20261114r2", "fincf-20261111", "revinst-20261111"
from framework.data import load, data_tags_used
sys.path.insert(0, "."); from elon_tools import limit_prices

IS_END = pd.Timestamp(os.environ.get("END", "2026-11-10"))   # 全期資料終點（變數名沿用快篩）
cal = load("calendar", tag=P1)
dates = pd.DatetimeIndex(sorted(pd.to_datetime(cal["date"]).unique()))
dates = dates[dates <= IS_END]
T = len(dates)

k = load("daily_k", tag=P1, columns=["date", "stock_id", "open", "high", "low", "close", "volume", "amount",
                             "no_trade", "prev_close", "ref_price", "limit_src", "limit_up", "limit_down", "jump_flag"])
k = k[(k["date"] <= IS_END) & (k["date"] >= "2012-01-01")]
sid = k["stock_id"]
common = sid.str.fullmatch(r"[1-9]\d{3}") & ~sid.str.startswith("91")   # 普通股：四碼、非 0 開頭、非 91xx 存託憑證
k = k[common & k["date"].isin(dates)].copy()
dates = dates[dates >= "2012-01-01"]; T = len(dates)
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
O, C = mat("open"), mat("close")
AMT = mat("amount", 0.0)
notrade = np.ones((T, N), bool); notrade[r, c] = k["no_trade"].fillna(True).to_numpy().astype(bool) | ~(k["volume"].to_numpy() > 0)
LU, LD = mat("limit_up"), mat("limit_down")
ls = k["limit_src"].fillna("").astype(str)
badlim = np.zeros((T, N), bool); badlim[r, c] = (ls.str.startswith("待查") | (ls == "缺參考價")).to_numpy()
nolim = np.zeros((T, N), bool); nolim[r, c] = ls.str.startswith("無漲跌幅").to_numpy()
JUMP = np.zeros((T, N), bool); JUMP[r, c] = k["jump_flag"].fillna(False).to_numpy().astype(bool)
PC, REF = mat("prev_close"), mat("ref_price")
# r68 減資／面額變更恢復買賣日 ref_price 仍為停止買賣前收盤（退回-69④，r72 才修正）：比照 068 以 corp_actions 修正當日漲跌停
ca0 = load("corp_actions", tag=P1)
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
    if row.bad or not (np.isfinite(PC[i, j]) and PC[i, j] > 0):
        continue
    if not (np.isfinite(REF[i, j]) and abs(REF[i, j] - PC[i, j]) < 1e-9):
        continue
    if abs(row.ratio - 1.0) < 1e-12 and row.cash == 0:
        continue
    newref = round((PC[i, j] - row.cash) / row.ratio, 2)
    up, dn = limit_prices(newref, row.date.date().isoformat())
    LU[i, j], LD[i, j] = up, dn
    nolim[i, j] = False
    F_FIX.append((row.stock_id, row.date.date().isoformat(), row.kinds, row.ratio, row.cash, PC[i, j], newref))
CT = np.where(present & ~notrade, C, np.nan)        # 有成交日的收盤價（未還原）
# 時點一致調整因子（只供描述性組合淨值）：參考價≠前收（公司行動日）時 f＝ref／prev_close
f = np.where(np.isfinite(REF) & np.isfinite(PC) & (PC > 0) & (np.abs(REF - PC) > 1e-9), REF / PC, 1.0)
F = np.cumprod(f, axis=0)

# 掛牌（官方逐日市場別區段）
lp = load("listing_periods", tag=P1)
lp = lp[lp["market"].isin(["上市", "上櫃"]) & lp["stock_id"].isin(stocks)]
listed = np.zeros((T, N), bool)
for row in lp.itertuples():
    a = dates.searchsorted(pd.Timestamp(row.start)); b = dates.searchsorted(pd.Timestamp(row.end), side="right")
    if b > a:
        listed[a:b, si[row.stock_id]] = True

# 變更交易（全額交割）／管理股票：上市＋上櫃（c5）
fd = load("fulldelivery", tag=P2)
FD_START = fd.groupby("market")["date"].min().astype(str).to_dict()
fd = fd[fd["code"].isin(stocks)].copy()
fd["date"] = pd.to_datetime(fd["date"])
fd = fd[fd["date"].isin(dates)]
FULLD = np.zeros((T, N), bool)
FULLD[di[fd["date"]].to_numpy(), si[fd["code"]].to_numpy()] = True

# 金融保險業（現行產業別）；查無產業別（多為已下市）＝未知
ind = load("industry", allow_candidate=True, tag=FINCF).set_index("stock_id").reindex(stocks)
FINANCIAL = ind["is_financial"].fillna(False).to_numpy(bool)
IND_UNKNOWN = ind["is_financial"].isna().to_numpy()

# 前 20 個市場交易日平均成交金額（含訊號日，無成交日計 0）
AMT0 = np.where(present & ~notrade, np.nan_to_num(AMT), 0.0)
cs = np.cumsum(AMT0, axis=0)
ADV20 = np.full((T, N), np.nan)
ADV20[19:] = (cs[19:] - np.vstack([np.zeros((1, N)), cs[:-20]])) / 20

# 每月換股日：每月最後一個市場交易日
ym = dates.year * 100 + dates.month
rebal_m = np.r_[ym[1:] != ym[:-1], True]
rebal_m[-1] = False     # 資料最後一日之後無次一交易日


def fin_avail(deadline):
    """財報：法定期限（遇非交易日順延）之次一交易日起可用（D-070-…-1014-2）。"""
    return dates.searchsorted(pd.Timestamp(deadline)) + 1


def rev_avail(p):
    """月營收：次月 10 日之後的第一個交易日起可用（10 日當天不可用；D-070-…-1014-2）。"""
    return dates.searchsorted((p + 1).start_time + pd.Timedelta(days=9), side="right")


def deadline_of(qe):
    y, m = qe.year, qe.month
    return {3: f"{y}-05-15", 6: f"{y}-08-14", 9: f"{y}-11-14", 12: f"{y + 1}-03-31"}[m]


# ---------- 財報（單季）----------
QEND = list(pd.date_range("2012-03-31", "2026-09-30", freq="QE"))
qpos = {d: n for n, d in enumerate(QEND)}
Q = len(QEND)
if os.environ.get("DRYRUN_FIN"):      # 只供程式流程測試（已退回資料），產出不得使用
    fin = pd.read_parquet(os.environ["DRYRUN_FIN"], columns=["stock_id", "date", "dataset", "type", "value"])
else:
    fin = load("financials", allow_candidate=True, tag=FIN, columns=["stock_id", "date", "dataset", "type", "value"])
fin = fin[(fin["date"] >= "2012-03-31") & (fin["date"] <= "2026-09-30") & fin["stock_id"].isin(stocks)]
fin = fin[fin["type"].isin(["IncomeFromContinuingOperations", "OperatingIncome", "Equity", "OrdinaryShare"])]
# 欄位取用：繼續營業單位淨利、營業利益、權益總額、普通股股本；不使用 Eve 退回項（損益表 EquityAttributableToOwnersOfParent）
fin["date"] = pd.to_datetime(fin["date"])


def qmat(df, typ):
    x = df[df["type"] == typ].drop_duplicates(["stock_id", "date"], keep="last")
    m = np.full((Q, N), np.nan)
    x = x[x["date"].isin(qpos)]
    m[x["date"].map(qpos).to_numpy(), si[x["stock_id"]].to_numpy()] = x["value"].to_numpy(float)
    return m


CO = qmat(fin, "IncomeFromContinuingOperations")   # 單季（FinMind 綜合損益表為單季值，已核對 2330／2412）
OI = qmat(fin, "OperatingIncome")
EQ = qmat(fin, "Equity")                           # 權益總額
OS = qmat(fin, "OrdinaryShare")                    # 普通股股本（元）

cf = load("cashflow", allow_candidate=True, tag=FINCF, columns=["stock_id", "date", "type", "value"])
cf = cf[(cf["date"] >= "2012-03-31") & (cf["date"] <= "2026-09-30") & cf["stock_id"].isin(stocks)]
cf["date"] = pd.to_datetime(cf["date"])
OPC = qmat(cf, "CashFlowsFromOperatingActivities")   # 年內累計
INC = qmat(cf, "CashProvidedByInvestingActivities")  # 年內累計


def ytd_to_q(m):
    """年內累計轉單季：Q1＝Q1；Qn＝Qn累計−Q(n−1)累計；前一季缺→該季缺（不推估）。"""
    out = np.full_like(m, np.nan)
    for n, d in enumerate(QEND):
        if d.month == 3:
            out[n] = m[n]
        elif n > 0:
            out[n] = m[n] - m[n - 1]
    return out


FCFq = ytd_to_q(OPC) + ytd_to_q(INC)
FCF4 = np.full_like(FCFq, np.nan)
for n in range(3, Q):
    blk = FCFq[n - 3:n + 1]
    FCF4[n] = np.where(np.isfinite(blk).all(axis=0), blk.sum(axis=0), np.nan)
OIYOY_POS = np.full((Q, N), False); OIYOY_MISS = np.ones((Q, N), bool)
for n in range(4, Q):
    a, b = OI[n], OI[n - 4]
    ok = np.isfinite(a) & np.isfinite(b) & (b > 0)            # 分母 ≤ 0 不計算、不納入
    OIYOY_MISS[n] = ~ok
    OIYOY_POS[n] = ok & (a > b)
q_avail = np.array([fin_avail(deadline_of(q)) for q in QEND])
cur_q = np.full(T, -1)
for n, a in enumerate(q_avail):
    if a < T:
        cur_q[a:] = n

# 面額（D-070-20261112-1535-1）：官方公司基本資料「普通股每股面額」（證交所 t187ap03_L、櫃買 mopsfin_t187ap03_O，
# 2026-11-12 下載，raw_par/）＋共用層 corp_actions「面額變更」日期：
#   有面額變更紀錄：第一筆之前 10 元、最後一筆之後＝現行官方面額、兩筆之間＝資料不足；
#   無紀錄：現行面額 10 元→10；非 10 元且首次掛牌 ≥2014-01-01→全期現行面額；非 10 元且 2014 前掛牌→資料不足；
#   不在現行表（已下市）：首次掛牌 <2014-01-01→10，否則資料不足；非新台幣面額或無面額→資料不足。
import json, re
def _par(txt):
    t = str(txt).replace(" ", "")
    m = re.fullmatch(r"新台幣([0-9.]+)元", t)
    return float(m.group(1)) if m else None
PAR_NOW = {}
for x in json.load(open("raw_par/twse_t187ap03_L.json", encoding="utf-8")):
    PAR_NOW[str(x["公司代號"]).strip()] = (_par(x["普通股每股面額"]), x["普通股每股面額"])
for x in json.load(open("raw_par/tpex_t187ap03_O.json", encoding="utf-8")):
    PAR_NOW[str(x["SecuritiesCompanyCode"]).strip()] = (_par(x["ParValueOfCommonStock"]), x["ParValueOfCommonStock"])
pchg = ca0_all = load("corp_actions", tag=P1)
pchg = pchg[pchg["kind"].str.contains("面額變更")].copy()
pchg["d"] = pd.to_datetime(pchg["ex_date"])
PCHG = pchg.groupby("stock_id")["d"].apply(lambda x: sorted(x)).to_dict()
first_list = load("listing_periods", tag=P1).groupby("stock_id")["start"].min()
PAR_Q = np.full((Q, N), np.nan)              # 財報期末日適用面額；NaN＝資料不足
PAR_NOTE = {}
for j, s in enumerate(stocks):
    cur, raw = PAR_NOW.get(s, (None, None))
    fl = pd.Timestamp(first_list.get(s, pd.NaT))
    for n, qe in enumerate(QEND):
        if s in PCHG:
            ds = PCHG[s]
            if qe < ds[0]:
                v = 10.0
            elif qe >= ds[-1]:
                v = cur
            else:
                v = None
        elif s in PAR_NOW:
            if cur == 10.0:
                v = 10.0
            elif cur is not None and pd.notna(fl) and fl >= pd.Timestamp("2014-01-01"):
                v = cur
            else:
                v = None
        else:
            v = 10.0 if (pd.notna(fl) and fl < pd.Timestamp("2014-01-01")) else None
        PAR_Q[n, j] = np.nan if v is None else v
    if s in PCHG or (s in PAR_NOW and cur != 10.0) or (s not in PAR_NOW and not (pd.notna(fl) and fl < pd.Timestamp("2014-01-01"))):
        PAR_NOTE[s] = dict(現行面額=raw, 面額變更=[d.date().isoformat() for d in PCHG.get(s, [])],
                           首次掛牌=None if pd.isna(fl) else fl.date().isoformat())
PAR_BAD_LIST = [s for s in PAR_NOTE if np.isnan(PAR_Q[:, list(stocks).index(s)]).any()]

# ---------- 月營收 ----------
mr = load("month_revenue", allow_candidate=True, tag=REVI)
mr = mr[mr["stock_id"].isin(stocks)].drop_duplicates(["stock_id", "revenue_year", "revenue_month"], keep="last")
months = pd.period_range("2012-01", "2026-10", freq="M")
mpos = {(p.year, p.month): n for n, p in enumerate(months)}
REVm = np.full((len(months), N), np.nan)
kk = np.array([mpos.get((a, b), -1) for a, b in zip(mr["revenue_year"], mr["revenue_month"])])
sel = kk >= 0
REVm[kk[sel], si[mr["stock_id"][sel]].to_numpy()] = mr["revenue"][sel].to_numpy(float)
m_avail = np.array([rev_avail(p) for p in months])
cur_m = np.full(T, -1)
for n, a in enumerate(m_avail):
    if a < T:
        cur_m[a:] = n
REV4 = np.full((T, N), np.nan); REV3 = np.full((T, N), np.nan)
for i in range(T):
    n = cur_m[i]
    if n >= 3:
        b4 = REVm[n - 3:n + 1]; b3 = REVm[n - 2:n + 1]
        REV4[i] = np.where(np.isfinite(b4).all(axis=0), b4.sum(axis=0), np.nan)   # 缺月不沿用、不推估
        REV3[i] = np.where(np.isfinite(b3).all(axis=0), b3.sum(axis=0), np.nan)

# ---------- 每日可用的財報條件 ----------
FCF_POS = np.zeros((T, N), bool); ROE_POS = np.zeros((T, N), bool); OIG_POS = np.zeros((T, N), bool)
MCAP = np.full((T, N), np.nan); FIN_MISS = np.ones((T, N), bool); PARX = np.zeros((T, N), bool)
for i in range(T):
    n = cur_q[i]
    if n < 4:
        continue
    co, eq, os_ = CO[n], EQ[n], OS[n]
    f4 = FCF4[n]
    par = PAR_Q[n]
    ok = np.isfinite(co) & np.isfinite(eq) & np.isfinite(f4) & ~OIYOY_MISS[n] & np.isfinite(os_) & (os_ > 0)
    FIN_MISS[i] = ~ok
    FCF_POS[i] = ok & (f4 > 0)
    ROE_POS[i] = ok & (eq > 0) & (co > 0)
    OIG_POS[i] = ok & OIYOY_POS[n]
    MCAP[i] = CT[i] * os_ / par                    # 面額資料不足 → NaN（不納入）
    PARX[i] = ~np.isfinite(par)
q_rebal = np.zeros(T, bool)                         # 每季換股日：期限日之次一交易日（收盤判斷）
for a in q_avail:
    if a < T - 1:
        q_rebal[a] = True

ca = load("corp_actions", tag=P1)
ca = ca[ca["stock_id"].isin(stocks)].copy()

np.savez_compressed("mats070.npz", F=F, present=present, O=O, C=C, CT=CT, notrade=notrade, LU=LU, LD=LD, badlim=badlim,
                    nolim=nolim, JUMP=JUMP, listed=listed, FULLD=FULLD, FINANCIAL=FINANCIAL, IND_UNKNOWN=IND_UNKNOWN,
                    ADV20=ADV20, rebal_m=rebal_m, q_rebal=q_rebal, FCF_POS=FCF_POS, ROE_POS=ROE_POS, OIG_POS=OIG_POS,
                    MCAP=MCAP, FIN_MISS=FIN_MISS, PARX=PARX, REV4=REV4, REV3=REV3, cur_q=cur_q, cur_m=cur_m)
pickle.dump({"dates": dates, "stocks": stocks, "ca": ca, "tags": data_tags_used(), "QEND": QEND, "q_avail": q_avail,
             "months": months, "m_avail": m_avail, "F_FIX": F_FIX, "FD_START": FD_START,
             "PAR_BAD_LIST": PAR_BAD_LIST, "PAR_NOTE": PAR_NOTE, "n_fin": int(FINANCIAL.sum()), "n_ind_unknown": int(IND_UNKNOWN.sum())},
            open("meta070.pkl", "wb"))
print(T, N, rebal_m.sum(), q_rebal.sum(), "面額未驗證", len(PAR_BAD_LIST), PAR_BAD_LIST[:20], data_tags_used())
