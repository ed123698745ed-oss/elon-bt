"""068 R03 準備：V-TOP10 每個換股日的前 10 名候選（ROE 濾網前）與所用財報季、NI、EQ、通過與否。
用途：①界定需要核對訊號當時財報版本的股季；②標出 fin-20261107 被 Eve 指出混入綜合損益的列。"""
import sys, pickle
import numpy as np, pandas as pd
sys.argv = ["x"]
import simR01 as S
sys.path.insert(0, "/home/claude/elon-bt")
from framework.data import load
M, meta, dates, stocks = S.M, S.meta, S.dates, S.stocks
QEND = meta["QEND"]
p = S.COMBOS["V-TOP10"]
rows = []
for i in np.where(M["rebal_m"])[0]:
    if dates[i] < S.SIG_START: continue
    pre = dict(p); pre["filt"] = None
    top = S.selection(i, pre)          # 動能前 10 名（濾網前）
    n = int(M["cur_q"][i])
    for r, j in enumerate(top):
        rows.append(dict(sig_date=dates[i], rank=r + 1, stock_id=stocks[j], q=pd.Timestamp(QEND[n]) if n >= 0 else pd.NaT,
                         passed=bool(M["ROE_Q_POS"][i, j]), fin_miss=bool(M["FIN_MISS"][i, j])))
D = pd.DataFrame(rows)
fin = pd.read_parquet("/root/.elon_data/fin-20261107/financials.parquet")   # 診斷用：R01 實際使用的已退回標籤，只用來界定影響範圍，不作結果
fin["date"] = pd.to_datetime(fin["date"])
inc = fin[fin.dataset == "TaiwanStockFinancialStatements"]
ni = inc[inc.type == "EquityAttributableToOwnersOfParent"][["stock_id", "date", "value", "origin_name"]].rename(columns={"date": "q", "value": "NI_par", "origin_name": "NI_origin"})
D = D.merge(ni, on=["stock_id", "q"], how="left")
D["mixed_ci"] = D["NI_origin"].fillna("").str.contains("綜合損益")
D.to_pickle("decisions068.pkl")
print(len(D), "列；換股日", D.sig_date.nunique(), "；唯一股季", D[["stock_id", "q"]].drop_duplicates().shape[0])
print("通過", int(D.passed.sum()), "；資料缺", int(D.fin_miss.sum()), "；NI 欄為綜合損益（Eve 指出的混入）", int(D.mixed_ci.sum()))
print(D[D.mixed_ci][["sig_date", "stock_id", "q", "NI_par", "passed"]].to_string())
