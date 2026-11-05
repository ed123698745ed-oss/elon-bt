"""舊版 044（data-20261105）實際用到推算換股比的部位與批次（Eve：勿將 1 筆差異推成整批均錯，交代實際使用數）。"""
import os
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("ELON_OUT_OLD", "/home/claude/raw_dl/out")
ca = pd.read_parquet(f"{OUT}/corp_actions.parquet")
cal = sorted(pd.read_parquet(f"{OUT}/calendar.parquet").date); idx = {d: i for i, d in enumerate(cal)}
B = pd.read_csv(f"{ROOT}/experiments/out_044/batches.csv"); P = pd.read_csv(f"{ROOT}/experiments/out_044/positions.csv", dtype={"stock_id": str})
done = set(B[B.status == "完成"].S)
lines = []
for name, df in [("減資換股比（官方參考價反推，185 筆）", ca[ca.flag.fillna("").str.contains("反推")]),
                 ("面額變更比率（變更前價÷參考價反推）", ca[ca.kind == "面額變更"])]:
    m = P[P.status == "完成"].merge(df[["stock_id", "ex_date"]], on="stock_id")
    m["Ed"] = pd.to_datetime(m.S).map(lambda d: cal[idx[d] + 1]); m["X"] = pd.to_datetime(m.exit)
    h = m[(m.ex_date > m.Ed) & (m.ex_date <= m.X)]
    lines.append(f"{name}：持有期間實際用到 {len(h)} 個部位、{h.S.nunique()} 批（其中列入主統計的完成批 {len(set(h.S) & done)} 批）")
    lines += ["  " + " ".join(map(str, r)) for r in h[["S", "side", "stock_id", "ex_date"]].itertuples(index=False)]
txt = "\n".join(lines) + "\n（只計報酬計算用到者；訊號排序用到的影響另見新舊橋接）\n"
open(f"{ROOT}/experiments/out_044/inferred_usage_old.txt", "w").write(txt); print(txt)
