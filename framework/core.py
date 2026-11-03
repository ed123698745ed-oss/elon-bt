"""Elon 回測框架必經函式（第一期）。

每個函式對應防錯清單條目；報告與程式只能透過這裡計算持有日、報酬、樣本切分。
資料表（日曆、日K、公司行動、市場別）由 data layer 產生後傳入，本模組不自行下載。
"""
from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

# ---------------------------------------------------------------- 交易日曆（B3、C6）


class Calendar:
    """官方市場交易日曆。只接受官方交易日清單，不從個股日K推得。"""

    def __init__(self, trading_days):
        days = sorted({_d(x) for x in trading_days})
        if not days:
            raise ValueError("交易日曆為空")
        self.days = days

    def is_trading(self, d) -> bool:
        d = _d(d)
        i = bisect_left(self.days, d)
        return i < len(self.days) and self.days[i] == d

    def next_on_or_after(self, d) -> date:
        i = bisect_left(self.days, _d(d))
        if i >= len(self.days):
            raise ValueError(f"{d} 超出日曆範圍")
        return self.days[i]

    def shift(self, d, n: int) -> date:
        """d 為交易日；往後（n>0）或往前（n<0）第 n 個交易日。"""
        d = _d(d)
        if not self.is_trading(d):
            raise ValueError(f"{d} 不是交易日")
        i = bisect_left(self.days, d) + n
        if not 0 <= i < len(self.days):
            raise ValueError("超出日曆範圍")
        return self.days[i]

    def hold_days(self, entry, exit_) -> int:
        """持有交易日數，含首尾；同日進出計 1 日（C6）。"""
        a, b = _d(entry), _d(exit_)
        if b < a:
            raise ValueError("出場日早於進場日")
        if not (self.is_trading(a) and self.is_trading(b)):
            raise ValueError("進出場日必須是交易日")
        return bisect_right(self.days, b) - bisect_left(self.days, a)

    def exit_after_hold(self, entry, h: int) -> date:
        """持有 H 個交易日（含進場日）時的出場日，H>=1。"""
        if h < 1:
            raise ValueError("H 必須 >= 1")
        return self.shift(entry, h - 1)


def _d(x) -> date:
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    if isinstance(x, datetime):
        return x.date()
    return date.fromisoformat(str(x)[:10])


# ---------------------------------------------------------------- 代號（E2，退回-58）


def norm_id(x) -> str:
    """代號一律文字；數字讀入者補回前導零到 4 碼。"""
    if isinstance(x, float):
        if x != int(x):
            raise ValueError(f"代號不是整數: {x}")
        x = int(x)
    s = str(x).strip()
    if s.isdigit() and len(s) < 4:
        s = s.zfill(4)
    return s


# ---------------------------------------------------------------- 公司行動與報酬（A2）


@dataclass
class Action:
    """一筆公司行動。ex_date 當日開盤起適用。

    share_ratio：每 1 股變成幾股（配股 1+配股率；減資換股比；分割倍數）。
    cash：每持有 1 股（行動前）可得現金（現金股利、減資退還現金）。
    cash_date：現金實際入帳日（無資料時 None，報酬仍計入但標記）。
    """
    ex_date: date
    kind: str
    share_ratio: float = 1.0
    cash: float = 0.0
    cash_date: date | None = None
    source: str = ""


@dataclass
class TradeReturn:
    ret: float
    shares_end: float
    cash: float
    actions: list = field(default_factory=list)
    flags: list = field(default_factory=list)


def trade_return(direction: str, entry_px: float, exit_px: float, entry_date, exit_date,
                 actions: list[Action], entry_session: str = "open", exit_session: str = "close") -> TradeReturn:
    """固定股數＋實得現金報酬（A2；研究預設口徑 V03 第三節）。

    做多：期初 1 股，持有期間依公司行動調整股數並累計現金，期末 (股數×出場價＋現金)/進場價 − 1。
    做空：期初借 1 股，須返還調整後股數並支付現金股利，報酬為 1 − (股數×出場價＋現金)/進場價。
    除權息日 = 進場日（不論開盤或收盤）：已是除權息後價格，不適用該行動。
    除權息日 = 出場日：出場價已是除權息後價格，行動適用。
    不使用「除權息前價÷參考價」連乘。
    """
    if direction not in ("long", "short"):
        raise ValueError("direction 只能是 long／short")
    if entry_px <= 0 or exit_px <= 0:
        raise ValueError("價格必須 > 0")
    a, b = _d(entry_date), _d(exit_date)
    shares, cash, used, flags = 1.0, 0.0, [], []
    for act in sorted(actions, key=lambda x: x.ex_date):
        ex = _d(act.ex_date)
        # 除權息日當天的開盤與收盤都已是除權息後價格：進場日=除權息日不適用，出場日=除權息日適用
        if not (a < ex <= b):
            continue
        cash += shares * act.cash
        shares *= act.share_ratio
        used.append(act)
        if act.cash and act.cash_date and _d(act.cash_date) > b:
            flags.append(f"{act.kind} 現金於 {act.cash_date} 入帳，晚於出場日")
    gross = (shares * exit_px + cash) / entry_px
    r = gross - 1 if direction == "long" else 1 - gross
    return TradeReturn(r, shares, cash, used, flags)


# ---------------------------------------------------------------- 樣本切分（D5～D7）


@dataclass(frozen=True)
class Split:
    """單一謂詞：依進場日判定 IS／隔離帶／OOS。切點寫入凍結紀錄後才可算報酬。"""
    is_end: date
    oos_start: date

    def label(self, entry_date) -> str:
        d = _d(entry_date)
        if d <= self.is_end:
            return "IS"
        if d >= self.oos_start:
            return "OOS"
        return "GAP"


def freeze_split(split: Split, cal: Calendar, max_hold: int, min_gap: int, path: str, note: str = "") -> dict:
    """檢查隔離帶 ≥ max(min_gap, max_hold) 個交易日後，寫入凍結紀錄（時間＋雜湊）。"""
    gap = cal.hold_days(cal.next_on_or_after(split.is_end), cal.next_on_or_after(split.oos_start)) - 2
    need = max(min_gap, max_hold)
    if gap < need:
        raise ValueError(f"隔離帶 {gap} 個交易日 < 需要 {need}（D5）")
    rec = {"is_end": split.is_end.isoformat(), "oos_start": split.oos_start.isoformat(),
           "gap_trading_days": gap, "required": need, "predicate": "entry<=is_end→IS; entry>=oos_start→OOS; else GAP",
           "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "note": note}
    rec["sha256"] = hashlib.sha256(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    return rec


def load_frozen_split(path: str) -> Split:
    rec = json.load(open(path, encoding="utf-8"))
    h = rec.pop("sha256")
    if hashlib.sha256(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode()).hexdigest() != h:
        raise ValueError("凍結紀錄雜湊不符，切點可能被修改")
    return Split(_d(rec["is_end"]), _d(rec["oos_start"]))


# ---------------------------------------------------------------- 持倉重疊（C7）


def overlaps(trades) -> list:
    """trades: (stock_id, param, entry_date, entry_session, exit_date, exit_session)。

    同股同參數：後一筆進場時點不得早於或等於前一筆出場時點（同日收盤出、開盤進也算重疊）。
    回傳重疊配對清單。
    """
    order = {"open": 0, "close": 1}
    by = {}
    for t in trades:
        by.setdefault((norm_id(t[0]), t[1]), []).append(t)
    bad = []
    for k, ts in by.items():
        ts = sorted(ts, key=lambda t: (_d(t[2]), order[t[3]]))
        for p, q in zip(ts, ts[1:]):
            if (_d(q[2]), order[q[3]]) <= (_d(p[4]), order[p[5]]):
                bad.append((p, q))
    return bad
