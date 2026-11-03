"""當時母體（A1、A7）與成交判定（B5、C3）。

輸入表格由 data layer 產生：
- status：stock_id, status(興櫃/上櫃/上市/下市), start_date, end_date(含), verified(bool)
- bar：單一股票單日 dict：open, high, low, close, volume, limit_up, limit_down, halted(bool)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from framework.core import _d, norm_id

TRADABLE = ("上市", "上櫃")


def universe_on(status_rows, d, include_unverified=False) -> list[str]:
    """訊號日 d 當時合格（上市或上櫃）的代號，含之後才下市者；不用現行清單回填。

    身分未驗證（verified=False）預設排除，報告須另做放回敏感度（A9）。
    """
    d = _d(d)
    out = set()
    for r in status_rows:
        if r["status"] not in TRADABLE:
            continue
        if not include_unverified and not r.get("verified", False):
            continue
        s, e = _d(r["start_date"]), (_d(r["end_date"]) if r.get("end_date") else date.max)
        if s <= d <= e:
            out.add(norm_id(r["stock_id"]))
    return sorted(out)


@dataclass
class Fill:
    ok: bool
    price: float | None
    reason: str = ""
    warn: str = ""


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
    if bar is None or bar.get("halted"):
        return Fill(False, None, "停牌或無資料")
    if not bar.get("volume"):
        return Fill(False, None, "零量")
    buy = (direction == "long") == (action == "entry")
    px = bar["open"] if session == "open" else bar["close"]
    up, dn = bar.get("limit_up"), bar.get("limit_down")
    one = bar["open"] == bar["high"] == bar["low"] == bar["close"]
    if buy and up is not None and one and px == up:
        return Fill(False, None, "一價鎖漲停，買不到")
    if not buy and dn is not None and one and px == dn:
        return Fill(False, None, "一價鎖跌停，賣不到")
    warn = []
    if buy and up is not None and px == up:
        warn.append("價位在漲停，排隊未驗證")
    if not buy and dn is not None and px == dn:
        warn.append("價位在跌停，排隊未驗證")
    if direction == "short" and action == "entry" and prev_close is not None and px < prev_close:
        if day is None or _d(day) < downtick_rule_end:
            warn.append("平盤下放空限制待查")
    return Fill(True, px, "", "；".join(warn))
