"""逐日檢核平盤下名單「前日」星號的語意：星號檔前一交易日是跌停，還是未跌停而跌幅≥3.5%。
用法：P2_OUT=<第二期輸出> K=<第一期 daily_k.parquet> python experiments/validate_ban_rule.py
輸出：每個名單日、市場的星號數、其中前日跌停數、前日未跌停且跌幅≥3.5% 數，與 ban_rule 是否一致。"""
import os
import pandas as pd

dl = pd.read_parquet(os.path.join(os.environ["P2_OUT"], "downtick_list.parquet"))
k = pd.read_parquet(os.environ["K"], columns=["date", "stock_id", "close", "prev_close", "limit_down"])
k = k[k["date"] >= "2013-09-01"]
cal = sorted(k["date"].unique())
prev = dict(zip(cal[1:], cal[:-1]))
k["drop"] = k["close"] / k["prev_close"] - 1
k["ld"] = k["close"] <= k["limit_down"]
s = dl[dl["downtick_ban_prev_limit"]].copy()
s["pd"] = s["date"].map(prev)
m = s.merge(k.rename(columns={"date": "pd", "stock_id": "code"})[["pd", "code", "drop", "ld"]], on=["pd", "code"], how="left")
m["nonld35"] = (~m["ld"].fillna(False).astype(bool)) & (m["drop"] <= -0.035)
g = m.groupby(["date", "market"]).agg(stars=("code", "size"), prev_limit_down=("ld", "sum"),
                                       nonld_drop35=("nonld35", "sum"), ban_rule=("ban_rule", "first")).reset_index()
g["consistent"] = ~((g["ban_rule"] == "跌停") & (g["nonld_drop35"] > 0))
# 剩餘不一致若前日 limit_down 為空（缺參考價：減資／面額變更恢復日），屬第一期限價缺值，不是名單語意問題
miss = m[m["nonld35"]].merge(k.rename(columns={"date": "pd", "stock_id": "code"})[["pd", "code", "limit_down"]], on=["pd", "code"])
print("不一致星號中前日限價缺值（缺參考價）者：", int(miss["limit_down"].isna().sum()), "／", len(miss[miss["date"].isin(g.loc[~g["consistent"], "date"])]))
print("跌停期卻有『未跌停且跌幅≥3.5%』星號的日：")
print(g[~g["consistent"]].to_string(index=False))
for a, b in (("2020-03-16", "2020-03-24"), ("2020-06-05", "2020-06-12"), ("2022-10-19", "2022-10-26"), ("2023-02-20", "2023-03-01")):
    print(g[(g["date"] >= a) & (g["date"] <= b)].to_string(index=False))
