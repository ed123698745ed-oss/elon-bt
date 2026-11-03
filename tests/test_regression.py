"""回歸測試：過去退回案例（交辦第六節）。舊做法會算錯，框架必須算對或擋下。

標記 DATA 的案例需要資料層（日K／市場別／事件表），資料建置完成後以真實資料補測。
"""
import json, os, sys, tempfile
from datetime import date, timedelta
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from framework.core import Action, Calendar, Split, freeze_split, load_frozen_split, norm_id, overlaps, trade_return


def weekday_cal(start="2023-01-02", n=400, holidays=()):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5 and d.isoformat() not in holidays:
            out.append(d)
        d += timedelta(days=1)
    return Calendar(out)


def test_r13_capital_reduction_fixed_shares():
    """退回-13：1512 瑞利跨減資。價格直接相除得 +129.17%，固定股數應約 −17.4%。"""
    entry, exit_ = 5.8, 5.8 * 2.2917
    naive = exit_ / entry - 1
    act = Action(date(2023, 3, 13), "減資", share_ratio=5.8 / 16.09, source="FinMind CapitalReductionReferencePrice 1512")
    r = trade_return("long", entry, exit_, "2023-02-01", "2023-04-10", [act]).ret
    assert naive == pytest.approx(1.2917, abs=1e-4)
    assert r == pytest.approx(-0.174, abs=0.002)


def test_r38_cash_dividend_not_chained():
    """退回-38：現金股利用固定股數＋現金，不用前收÷參考價連乘（連乘隱含再投資）。"""
    entry, prev_close, cash, exit_ = 100.0, 102.0, 5.0, 96.0
    ref = prev_close - cash
    chained = exit_ * (prev_close / ref) / entry - 1
    r = trade_return("long", entry, exit_, "2024-06-03", "2024-07-15",
                     [Action(date(2024, 7, 1), "現金股利", cash=cash)]).ret
    assert r == pytest.approx(0.01, abs=1e-12)
    assert abs(chained - r) > 1e-4


def test_ex_date_on_entry_not_applied():
    r = trade_return("long", 97.0, 97.0, "2024-07-01", "2024-07-05", [Action(date(2024, 7, 1), "現金股利", cash=5)]).ret
    assert r == 0.0


def test_short_pays_dividend():
    r = trade_return("short", 100.0, 95.0, "2024-06-03", "2024-07-15", [Action(date(2024, 7, 1), "現金股利", cash=5)]).ret
    assert r == pytest.approx(0.0, abs=1e-12)


def test_r30_hold_days_inclusive():
    """退回-30：持有日含首尾；日期索引相減漏 +1（41 應 42）。"""
    cal = weekday_cal()
    a = cal.days[10]
    b = cal.exit_after_hold(a, 42)
    assert cal.hold_days(a, b) == 42
    assert cal.days.index(b) - cal.days.index(a) == 41
    assert cal.hold_days(a, a) == 1


def test_r36_count_market_days_not_stock_rows():
    """退回-36：先刪無成交列再數日會錯。持有日只用市場日曆。"""
    cal = weekday_cal()
    a = cal.days[0]
    stock_rows = [d for i, d in enumerate(cal.days[:200]) if not (20 <= i < 99)]  # 停牌 79 日無成交列
    wrong_exit = stock_rows[39]               # 舊做法：個股第 40 根
    assert cal.hold_days(a, wrong_exit) == 119
    assert cal.exit_after_hold(a, 40) == cal.days[39]


def test_calendar_rejects_non_trading_day():
    cal = weekday_cal(holidays={"2023-01-23"})
    with pytest.raises(ValueError):
        cal.hold_days("2023-01-23", "2023-02-01")


def test_r11_overlap_same_day_close_then_open():
    """退回-11：同股同參數前筆收盤出、後筆同日開盤進＝重疊。"""
    t = [("2330", "H5", "2024-01-02", "open", "2024-01-08", "close"),
         ("2330", "H5", "2024-01-08", "open", "2024-01-12", "close"),
         ("2330", "H5", "2024-01-15", "open", "2024-01-19", "close")]
    bad = overlaps(t)
    assert len(bad) == 1 and bad[0][1][2] == "2024-01-08"


def test_r58_leading_zero():
    """退回-58：代號前導零遺失。"""
    assert norm_id(81) == "0081" and norm_id(81.0) == "0081" and norm_id("0050") == "0050" and norm_id(2330) == "2330"


def test_split_freeze_and_tamper():
    """D5～D7：隔離帶不得短於最長持有；凍結後改切點會被擋下。"""
    cal = weekday_cal(n=600)
    sp = Split(cal.days[200], cal.days[200 + 70])
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "split.json")
        with pytest.raises(ValueError):
            freeze_split(sp, cal, max_hold=74, min_gap=40, path=p)
        freeze_split(sp, cal, max_hold=60, min_gap=40, path=p)
        assert load_frozen_split(p) == sp
        rec = json.load(open(p)); rec["is_end"] = cal.days[210].isoformat(); json.dump(rec, open(p, "w"))
        with pytest.raises(ValueError):
            load_frozen_split(p)
    assert sp.label(cal.days[200]) == "IS" and sp.label(cal.days[201]) == "GAP" and sp.label(cal.days[270]) == "OOS"


PENDING = {
    "退回-14": "015 浮點殘值算成勝負：需 bt_stats 原檔（Drive 載入）",
    "退回-04": "003 一價鎖漲停仍以開盤成交：DATA（日K＋成交判定）",
    "退回-52": "038 買回期間晚於公告：DATA（事件期間攔截）",
    "退回-55": "055 兩事件同一價格序列：DATA（序列重複檢查）",
    "退回-57": "040 王道銀興櫃段殘留：DATA（市場別表）",
}


@pytest.mark.parametrize("case", sorted(PENDING))
def test_pending(case):
    pytest.skip(PENDING[case])
