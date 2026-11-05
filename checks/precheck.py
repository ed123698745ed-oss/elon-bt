"""交件前自動檢查（交辦第五節）。FAIL＝不能交件；WARN＝須在注意事項說明。

用法（Python）：
    from checks.precheck import run, show
    res = run(trades, reported=結果表, split_path="split.json", report_text=全文,
              manifest_files=[清冊列的附件路徑], cluster_unit="進場日")
    show(res)
elon-backtest 技能的 selfcheck 也會一併執行（欄位、時點、重算一致等）。
"""
from __future__ import annotations

import os
import re

import pandas as pd

from framework import elon_tools, stats
from framework.core import load_frozen_split, overlaps
from framework.ledger import HOLD_STAMP, RET_STAMP

ASSERTIVE = ["時點未違反", "皆附樣本外", "唯一可執行", "必須", "無法成交"]


def run(trades: pd.DataFrame, reported=None, split_path=None, report_text=None, manifest_files=(),
        cluster_unit=None, by=("combo",), quick=False, etest=False):
    out = []

    def add(level, item, msg=""):
        out.append((level, item, msg))

    bt, sha = stats.current()
    inc = trades[trades["excluded_reason"].isna() | (trades["excluded_reason"] == "")]

    # 統計未經 bt_stats
    if reported is not None:
        ver = reported.get("bt_stats版本")
        ok = ver is not None and (ver.astype(str) == bt.VERSION).all()
        add("PASS" if ok else "FAIL", "統計經 bt_stats", "" if ok else "結果表缺 bt_stats版本 欄或版本不符")

    # 持有日、報酬未經框架函式
    bad = inc[(inc.get("ret_by") != RET_STAMP) | (inc.get("hold_by") != HOLD_STAMP)] if "ret_by" in inc else inc
    add("PASS" if bad.empty else "FAIL", "持有日與報酬由框架計算",
        "" if bad.empty else f"{len(bad)} 筆未經 framework.ledger.trade_row：{list(bad['trade_id'][:10])}")

    # 樣本內外：文件、程式、明細同一判定式，差異 0
    if split_path:
        sp = load_frozen_split(split_path)  # 雜湊不符會直接丟錯
        lab = trades["entry_date"].map(lambda d: {"IS": "樣本內", "OOS": "樣本外", "GAP": "隔離帶"}[sp.label(d)])
        diff = (lab != trades["sample"]).sum()
        add("PASS" if diff == 0 else "FAIL", "樣本內外判定式差異筆數為 0", f"{diff} 筆不一致" if diff else "")

    # 清冊附件
    miss = [f for f in manifest_files if not os.path.exists(f)]
    add("PASS" if not miss else "FAIL", "清冊列的附件都在", str(miss) if miss else "")

    # 代號文字格式
    sym = trades["symbol"]
    okid = sym.map(lambda x: isinstance(x, str) and bool(re.fullmatch(r"\d{4,6}[A-Z]?", x))).all()
    add("PASS" if okid else "FAIL", "代號欄為文字格式", "" if okid else "有非文字或缺前導零的代號")

    # 同一價格序列對到兩個事件
    if "price_series_hash" in trades and trades["price_series_hash"].notna().any():
        g = trades.dropna(subset=["price_series_hash"]).groupby("price_series_hash")["symbol"].nunique()
        dup = g[g > 1]
        add("PASS" if dup.empty else "FAIL", "價格序列不重複對到不同代號", str(list(dup.index[:5])) if len(dup) else "")
    else:
        add("WARN", "價格序列重複檢查", "明細未提供 price_series_hash")

    # 同股同參數持倉重疊
    ov = overlaps(list(inc[["symbol", "combo", "entry_date", "entry_session", "exit_date", "exit_session"]]
                       .itertuples(index=False, name=None)))
    add("PASS" if not ov else "FAIL", "同股同參數持倉不重疊", f"{len(ov)} 組，例 {ov[:2]}" if ov else "")

    # 群聚與聚合 p、聚合單位數
    if cluster_unit and reported is not None:
        need = reported[reported["聚合單位數"] < reported["樣本數"]] if "聚合單位數" in reported else reported
        okc = "聚合p" in reported and need["聚合p"].notna().all()
        add("PASS" if okc else "FAIL", "有群聚的組合已列聚合 p")
        if "聚合單位數" in reported:
            few = reported[reported["聚合單位數"] < 10]
            if len(few):
                add("WARN", "聚合單位少於 10", f"{list(few.iloc[:, 0][:10])}：說明須註明檢定力不足")
    elif cluster_unit is None:
        g = inc.groupby(inc["entry_date"]).size()
        if (g > 1).any():
            add("WARN", "同日多筆但未指定聚合單位", f"{int((g > 1).sum())} 個進場日有 2 筆以上")

    # 事件期間與訊號資料時點（B4，退回-52）：訊號所用資料的最後日期不得晚於訊號日；
    # 事件期間起點晚於公告日 60 天以上要說明（例：買回期間晚於公告一年）
    if "feature_end" in trades:
        sig = pd.to_datetime(trades["info_time"].astype(str).str[:10])
        late = trades[pd.to_datetime(trades["feature_end"]) > sig]
        add("PASS" if late.empty else "FAIL", "訊號所用資料不晚於訊號日",
            f"{len(late)} 筆用到訊號日後資料：{list(late['trade_id'][:10])}" if len(late) else "")
    if {"event_start", "announce_date"} <= set(trades.columns):
        gap = (pd.to_datetime(trades["event_start"]) - pd.to_datetime(trades["announce_date"])).dt.days
        far = trades[gap > 60]
        if len(far):
            add("WARN", "事件期間起點晚於公告日 60 天以上", f"{len(far)} 筆：{list(far['trade_id'][:10])}，須逐筆說明")

    # 斷言字眼
    if report_text:
        hits = [w for w in ASSERTIVE if w in report_text]
        add("WARN" if hits else "PASS", "斷言字眼須附證據位置", str(hits) if hits else "")

    # elon-backtest 技能原有自檢
    for lvl, item, msg in elon_tools.selfcheck(trades, bt, reported=reported, by=by, cluster_unit=cluster_unit,
                                               report_text=report_text, quick=quick, etest=etest):
        add(lvl, "[技能] " + item, msg)
    add("INFO", "bt_stats sha256", sha)
    return out


def show(res) -> bool:
    for lvl, item, msg in res:
        print(f"{lvl:4} {item}" + (f"：{msg}" if msg and lvl != "PASS" else ""))
    n = sum(1 for r in res if r[0] == "FAIL")
    print("交件前檢查：" + ("無 FAIL" if n == 0 else f"{n} 項 FAIL，不能交件"))
    return n == 0
