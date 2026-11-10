"""當時母體（A1、A7）與成交判定（B5、C3）。

輸入表格由 data layer 產生：
- status：stock_id, status(興櫃/上櫃/上市/下市), start_date, end_date(含), verified(bool)
- bar：單一股票單日 dict：open, high, low, close, volume, limit_up, limit_down, halted(bool)
"""
from __future__ import annotations

import pandas as pd

from dataclasses import dataclass
from datetime import date

from framework.core import _d, norm_id

TRADABLE = ("上市", "上櫃")


def universe_on(periods, d, include_unverified=False) -> list[str]:
    """訊號日 d 當時在官方上市或上櫃的代號（含之後才下市者）；不用現行清單回填。

    退回-68（Eve R02）：唯一入口，只接受資料層 listing_periods.parquet 的列
    （欄位 stock_id、market、start、end、basis），與主日K用同一份歷史市場區段；
    轉板前的合法上櫃期間、已下市者都在內，興櫃與官方查無期間不在內。
    傳入 status.parquet（現行掛牌日，只有一段）會直接報錯，避免漏掉歷史段。
    include_unverified 參數保留相容，listing_periods 只含官方證實期間，故無作用。
    """
    d = _d(d)
    out = set()
    for r in periods:
        if "basis" not in r or "status" in r:
            raise ValueError("universe_on 只接受 listing_periods.parquet 的列（status.parquet 只有現行掛牌日，會漏歷史段）")
        if r["market"] not in TRADABLE:
            continue
        if _d(r["start"]) <= d <= _d(r["end"]):
            out.add(norm_id(r["stock_id"]))
    return sorted(out)


@dataclass
class Fill:
    ok: bool
    price: float | None
    reason: str = ""
    warn: str = ""
    insufficient: bool = False   # True＝資料不足（不是不能成交），交易須排除、批次列未完成


def judge_fill(bar, direction: str, action: str, session: str, prev_close: float | None = None,
               day=None, downtick_rule_end: date = date(2013, 9, 23)) -> Fill:
    """單筆成交判定，多空分開（不得拿多方結果取負）。

    direction: long／short；action: entry／exit；session: open／close。
    做多進場、放空回補＝買；做多出場、放空進場＝賣。
    - 無資料或停牌 → 不成交「停牌或無資料」
    - 成交量 0 → 不成交「零量」
    - 一價鎖漲停（開高低收皆為漲停價）時買不到；一價鎖跌停時賣不到
    - 開盤／收盤剛好在漲（跌）停但非一價：可成交，附 WARN「價位在漲（跌）停，排隊未驗證」
    - 放空進場在平盤下（價格 < 前收）且日期早於平盤下限制放寬日：WARN「平盤下放空限制待查」
    """
    if direction not in ("long", "short") or action not in ("entry", "exit") or session not in ("open", "close"):
        raise ValueError("參數錯誤")
    # 退回-68（Eve R03）：限幅狀態必須傳到成交結果。待查與缺參考價時無法判斷是否鎖漲跌停 → 資料不足（不得當可成交）；
    # 已證實無漲跌幅（初次掛牌前五日）正常放行並註記。
    ls = str(bar.get("limit_src") or "") if bar is not None else ""
    if ls.startswith("待查") or ls == "缺參考價":
        return Fill(False, None, f"資料不足：{ls}，無法判斷是否鎖漲跌停", "可成交性未驗證", insufficient=True)
    if bar is None or bar.get("halted"):
        return Fill(False, None, "停牌或無資料")
    vol = bar.get("volume")
    if vol is None or pd.isna(vol):   # 退回-69：NaN 的布林值為真，原寫法會把成交量缺值當成有成交
        return Fill(False, None, "資料不足：成交量缺值", "可成交性未驗證", insufficient=True)
    if vol <= 0:
        return Fill(False, None, "零量")
    buy = (direction == "long") == (action == "entry")
    px = bar["open"] if session == "open" else bar["close"]
    if px is None or pd.isna(px):     # 退回-70：開高低為 0 已改空值，不得以空值成交
        return Fill(False, None, f"資料不足：{'開盤' if session == 'open' else '收盤'}價缺值", "可成交性未驗證", insufficient=True)
    up, dn = bar.get("limit_up"), bar.get("limit_down")
    one = bar["open"] == bar["high"] == bar["low"] == bar["close"]
    if buy and up is not None and one and px == up:
        return Fill(False, None, "一價鎖漲停，買不到")
    if not buy and dn is not None and one and px == dn:
        return Fill(False, None, "一價鎖跌停，賣不到")
    warn = []
    if ls.startswith("無漲跌幅"):
        warn.append(f"{ls}，不判鎖定")
    if buy and up is not None and px == up:
        warn.append("價位在漲停，排隊未驗證")
    if not buy and dn is not None and px == dn:
        warn.append("價位在跌停，排隊未驗證")
    if direction == "short" and action == "entry" and prev_close is not None and px < prev_close:
        if day is None or _d(day) < downtick_rule_end:
            warn.append("平盤下放空限制待查")
    return Fill(True, px, "", "；".join(warn))
