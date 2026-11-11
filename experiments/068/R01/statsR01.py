"""068 R01 統計：樣本內／樣本外／最新年度（樣本外中訊號日在 2026 年者）並列；bt_stats 1.2。
Holm（聚合 p 為輸入）：家族一＝策略卡 10 組變體＋V-MERGE，家族二＝4 組 E-Test；樣本內、樣本外各自修正（freeze_068_R01.md 第 4 節）。
"""
import pandas as pd
from elon_tools import load_bt_stats, ten_table, dd_table

bt = load_bt_stats("bt_stats_v1.2.py")
FAM1 = ["V-L20", "V-L120", "V-TOP10", "V-FILT1ST", "V-ROE8", "V-REV", "V-LIQ0.5億", "V-LIQ2億", "V-2W", "V-MKT", "V-MERGE"]


def holm(s):
    o = s.dropna().sort_values(); m = len(o); out = {}; run = 0.0
    for k, (nm, v) in enumerate(o.items()):
        run = max(run, min(1.0, (m - k) * v)); out[nm] = run
    return pd.Series(out, dtype=float)


def with_latest(t):
    u = t[t["excluded_reason"].isna() & t["sample"].isin(["樣本內", "樣本外"])].copy()
    lat = u[(u["sample"] == "樣本外") & (pd.to_datetime(u["signal_date"]).dt.year == 2026)].copy()
    lat["sample"] = "最新年度"
    return pd.concat([u, lat], ignore_index=True)


def tables(t, family):
    u = with_latest(t)
    order = list(dict.fromkeys(t.combo))
    tt = ten_table(u, bt, by=("combo", "sample"), cluster_unit="進場日")
    tt[["combo", "sample"]] = tt["combo／sample"].str.split("｜", expand=True)
    dd = dd_table(u, bt, by=("combo", "sample"))
    dd[["combo", "sample"]] = dd["combo／sample"].str.split("｜", expand=True)
    tt["Holm聚合p"] = float("nan")
    for smp in ("樣本內", "樣本外"):
        sub = tt[(tt["sample"] == smp) & tt["combo"].isin(family)].set_index("combo")["聚合p"]
        h = holm(sub)
        m = (tt["sample"] == smp) & tt["combo"].isin(h.index)
        tt.loc[m, "Holm聚合p"] = tt.loc[m, "combo"].map(h)
    key = {c: i for i, c in enumerate(order)}; sk = {"樣本內": 0, "樣本外": 1, "最新年度": 2}
    tt = tt.sort_values(by=["combo", "sample"], key=lambda s: s.map(key) if s.name == "combo" else s.map(sk)).reset_index(drop=True)
    dd = dd.sort_values(by=["combo", "sample"], key=lambda s: s.map(key) if s.name == "combo" else s.map(sk)).reset_index(drop=True)
    return tt, dd


if __name__ == "__main__":
    card = pd.read_pickle("tradesR01.pkl"); et = pd.read_pickle("etradesR01.pkl")
    tt, dd = tables(card, FAM1); ett, edd = tables(et, list(et.combo.unique()))
    for n, x in (("R01_card_ten", tt), ("R01_card_dd", dd), ("R01_et_ten", ett), ("R01_et_dd", edd)):
        x.to_pickle(n + ".pkl")
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 30)
    cols = ["combo", "sample", "樣本數", "平均報酬", "平均持有交易日數", "單利年化", "勝率", "賠率R", "凱利", "標準差", "t值", "雙尾p", "聚合單位數", "聚合p", "Holm聚合p"]
    print(pd.concat([tt, ett])[cols].to_string())
    print(pd.concat([dd, edd])[["combo", "sample", "最大回撤", "最差三次回撤平均", "最長回撤期筆數", "最長回撤期日曆日", "最長回撤期未回復", "需註記"]].to_string())
