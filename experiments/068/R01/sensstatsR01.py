"""068 R01 敏感度統計與判讀（freeze_068_R01.md 第 5 節）。"""
import pandas as pd
from elon_tools import load_bt_stats, ten_table

bt = load_bt_stats("bt_stats_v1.2.py")
t = pd.read_pickle("sensR01_trades.pkl"); meta = pd.read_pickle("sensR01_meta.pkl")
u = t[t["excluded_reason"].isna() & t["sample"].isin(["樣本內", "樣本外"])].copy()
rows = []
for et in (False, True):
    g = u[u["is_etest"] == et]
    tt = ten_table(g, bt, by=("combo", "sample"), cluster_unit="進場日")
    tt[["cid", "sample"]] = tt["combo／sample"].str.split("｜(?=樣本)", regex=True, expand=True)
    rows.append(tt)
S = pd.concat(rows, ignore_index=True).merge(meta, on="cid")
S.to_pickle("sensR01_stats.pkl")

# 中心格與主結果一致性檢查
main = pd.concat([pd.read_pickle("R01_card_ten.pkl"), pd.read_pickle("R01_et_ten.pkl")])
chk = S[S.center].merge(main, left_on=["combo", "sample"], right_on=["combo", "sample"], suffixes=("_s", "_m"))
bad = chk[(chk["樣本數_s"] != chk["樣本數_m"]) | ((chk["平均報酬_s"] - chk["平均報酬_m"]).abs() > 1e-12)]
print("center cells", len(chk), "mismatch", len(bad))

out = []
for name, g in S.groupby("combo", sort=False):
    i = g[g["sample"] == "樣本內"]; o = g[g["sample"] == "樣本外"]
    same_dir = int(((i.set_index("cid")["平均報酬"] > 0) == (o.set_index("cid")["平均報酬"] > 0)).sum())
    out.append(dict(combo=name, 格數=len(i), 樣本內正報酬格=int((i["平均報酬"] > 0).sum()), 樣本內聚合p顯著格=int((i["聚合p"] < 0.05).sum()),
                    樣本外正報酬格=int((o["平均報酬"] > 0).sum()), 樣本外聚合p顯著格=int((o["聚合p"] < 0.05).sum()), 內外同方向格=same_dir,
                    判讀="穩健" if ((i["聚合p"] < 0.05).sum() >= 5 and (o["聚合p"] < 0.05).sum() >= 5 and same_dir == 9) else
                         ("樣本內穩健、樣本外未顯著" if (i["聚合p"] < 0.05).sum() >= 5 and (o["平均報酬"] > 0).sum() >= 5 else "不穩健／尖峰")))
J = pd.DataFrame(out); J.to_pickle("sensR01_judge.pkl")
pd.set_option("display.width", 250)
print(J.to_string())
