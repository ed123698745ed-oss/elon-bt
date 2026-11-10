"""端到端驗證：用候選版（未驗收）共用資料實際產出一份報告，確認首頁資料層標籤與警示由程式寫入。
這是流程驗證用示範，不是策略研究；統計數字不得引用。

用法：BT_STATS_PATH=/path/bt_stats_v1.0.py OUT=experiments/out_e2e python experiments/candidate_report_e2e.py
"""
import os, sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework import data, report, stats  # noqa: E402

OUT = os.environ.get("OUT", "experiments/out_e2e")
stats.load(os.environ["BT_STATS_PATH"])

k = data.load("daily_k", columns=["date", "stock_id", "open", "close", "no_trade"])            # 第一期：已驗收 r68
sv = data.load("surveillance", allow_candidate=True)                                           # 第二期：候選 c2
cal = sorted(data.load("calendar")["date"])

ev = sv[(sv["kind"] == "處置") & (sv["sec_kind"] == "普通股") & (sv["period_flag"] == "") &
        sv["start"].between("2024-01-01", "2024-12-31")].drop_duplicates(["code", "start"])
idx = {d: i for i, d in enumerate(cal)}
k = k[k["date"] >= "2023-12-01"].set_index(["stock_id", "date"]).sort_index()
rows = []
for r in ev.itertuples():
    i = np.searchsorted(cal, r.start)                       # 處置起日（含）當日開盤進場、第 5 個交易日收盤出場
    if i + 4 >= len(cal):
        continue
    d0, d1 = cal[i], cal[i + 4]
    try:
        a, b = k.loc[(r.code, d0)], k.loc[(r.code, d1)]
    except KeyError:
        continue
    if a["no_trade"] or b["no_trade"] or not (a["open"] > 0):
        continue
    rows.append({"combo": "示範｜處置起日買進持有5日", "ret": b["close"] / a["open"] - 1, "hold_days": 5,
                 "entry": d0, "cluster": d0, "excluded_reason": None, "is_etest": False})
trades = pd.DataFrame(rows)
_, md = report.result_table(trades, by=("combo",), cluster_unit="進場日")
body = "\n".join([
    "## 一、說明", "", "本報告只用來驗證「資料層標籤自動寫入首頁」的流程，不是策略研究，數字不得引用。",
    f"事件：2024 年處置起日（普通股、無期間旗標），進場＝處置起日開盤，出場＝第 5 個交易日收盤；未計成本與滑價。樣本 {len(trades)} 筆。", "",
    "## 二、十項統計（bt_stats）", "", md, "",
    "回撤三項（最大回撤、最差三次回撤平均、最長回撤期）：N/A，原因：流程驗證示範，未跑等風險回撤。", ""])
p = report.write_report(os.path.join(OUT, "候選版報告_端到端驗證.md"), "共用資料端到端驗證報告（示範）",
                        "共用資料層", "V—", "R—", body)
errs = report.check_report(p)
print(open(p, encoding="utf-8").read()[:900])
print("check_report:", errs or "通過")
sys.exit(1 if errs else 0)
