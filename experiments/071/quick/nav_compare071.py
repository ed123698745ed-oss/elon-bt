"""071 結案前對照：實際資金口徑（期報酬連乘、只看季末淨值）比較避險與否的年化與最大回撤（只用樣本內）。"""
import numpy as np, pandas as pd
P = pd.read_pickle("periods071.pkl")
g = P[(P.combo == "H1") & (P["sample"] == "樣本內")].sort_values("entry_date").dropna(subset=["L"])
S = g.S
yrs = (g.exit_date.iloc[-1] - g.entry_date.iloc[0]).days / 365.25
rows = []
for nm, r in [("100%做多", g.L), ("70%做多+30%現金", 0.7 * g.L), ("50%做多+50%現金", 0.5 * g.L),
              ("70%做多+空0050 30%（H1）", 0.7 * g.L + 0.3 * S), ("70%做多+空0050 50%", 0.7 * g.L + 0.5 * S),
              ("70%做多+空0050 70%", 0.7 * g.L + 0.7 * S), ("直接做多0050", -S)]:
    r = r.dropna(); v = np.cumprod(1 + r.values); pk = np.maximum.accumulate(np.r_[1, v])[1:]
    ann = v[-1] ** (1 / yrs) - 1; dd = (v / pk - 1).min()
    rows.append(dict(配置=nm, 季數=len(r), 年化=ann, 最大回撤季末=dd, 年化除回撤=ann / -dd, 單季最大虧損=r.min()))
out = pd.DataFrame(rows); out.to_pickle("nav_compare.pkl"); print(out.to_string())
