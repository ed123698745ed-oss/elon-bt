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
    """退回-13 原案（Eve 第一期審查引述）：1512 瑞利進場 6、出場 13.75、減資換股比 0.3603560129。
    價格直接相除 +129.1667%；固定股數 13.75×0.3603560129÷6−1＝−17.4184%（交件曾列 −17.3%，係用反推換股比）。"""
    entry, exit_, ratio = 6.0, 13.75, 0.3603560129
    naive = exit_ / entry - 1
    act = Action(date(2023, 3, 13), "減資", share_ratio=ratio, source="原案換股比")
    r = trade_return("long", entry, exit_, "2023-02-01", "2023-04-10", [act]).ret
    assert round(naive * 100, 4) == 129.1667
    assert r == pytest.approx(13.75 * ratio / 6 - 1, abs=1e-15)
    assert round(r * 100, 4) == -17.4184


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


def test_r58_ids_match_by_original_code():
    """退回-58（Eve 補充）：0081、帶字母、非四碼代號須按原識別碼配對，不得截斷或改寫。"""
    for raw, want in [("0081", "0081"), ("00981A", "00981A"), ("00690", "00690"), ("2330", "2330"),
                      (" 6488 ", "6488"), ("1256", "1256"), ("01006T", "01006T"), ("2888A", "2888A")]:
        assert norm_id(raw) == want
    events = [81, "00981A", "690"]                       # 事件表誤讀成數字或去零
    prices = {"0081": 1, "00981A": 2, "0690": 3, "00690": 4}
    got = [prices.get(norm_id(x)) for x in events]
    assert got[0] == 1 and got[1] == 2
    assert got[2] == 3 and got[2] != prices["00690"]       # 3 碼數字只補到 4 碼；5 碼 ETF 不可由去零代號還原 → 須以原字串讀入
    with pytest.raises(ValueError):
        norm_id(81.5)


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


BT_PATH = os.environ.get("BT_STATS_PATH", "/home/claude/vendor/bt_stats_v1.0.py")
need_bt = pytest.mark.skipif(not os.path.exists(BT_PATH), reason="需要 Drive 原版 bt_stats（設 BT_STATS_PATH）")


@need_bt
def test_r14_float_residual_not_counted_as_win():
    """退回-14 機制測試（合成資料，非原案重現）：浮點殘值（±1e-16）被算成勝負。經 bt_stats 視為 0，不算勝。
    原案 015 V03 R01 勝率 61.76%→60.294118%（41/68）的逐筆重現另列待補（明細檔 21MB，尚未取得）。"""
    from framework import stats
    bt = stats.load(BT_PATH)
    r = [0.01, -0.01, 1e-16, -1e-16, 0.02]
    naive = sum(x > 0 for x in r) / len(r)
    s = bt.summarize(r)
    assert naive == pytest.approx(0.6) and s["勝率"] == pytest.approx(0.4)


def test_r04_one_price_limit_up_not_filled():
    """退回-04：一價鎖漲停仍以開盤價成交。"""
    from framework.market import judge_fill
    bar = dict(open=11.0, high=11.0, low=11.0, close=11.0, volume=50, limit_up=11.0, limit_down=9.0)
    f = judge_fill(bar, "long", "entry", "open")
    assert not f.ok and "一價鎖漲停" in f.reason
    assert judge_fill(bar, "short", "entry", "open").ok          # 賣方可成交，多空分開判定
    bar2 = dict(bar, low=10.5)
    f2 = judge_fill(bar2, "long", "entry", "open")
    assert f2.ok and "排隊未驗證" in f2.warn
    assert not judge_fill(dict(bar, volume=0), "long", "entry", "open").ok
    assert not judge_fill(None, "long", "exit", "close").ok


def test_r57_universe_uses_status_on_date():
    """退回-57（合成資料）：興櫃段不得進母體；下市前仍在母體。"""
    from framework.market import universe_on
    rows = [dict(stock_id="2897", status="興櫃", start_date="2008-12-01", end_date="2017-05-08", verified=True),
            dict(stock_id="2897", status="上市", start_date="2017-05-09", end_date=None, verified=True),
            dict(stock_id=1234, status="上櫃", start_date="2005-01-03", end_date="2012-06-30", verified=True),
            dict(stock_id="9999", status="上市", start_date="2000-01-01", end_date=None, verified=False)]
    assert universe_on(rows, "2010-01-04") == ["1234"]
    assert universe_on(rows, "2018-01-02") == ["2897"]
    assert "9999" in universe_on(rows, "2018-01-02", include_unverified=True)


@need_bt
def test_precheck_end_to_end():
    """退回-55／11／58 與框架章：交件前檢查要擋下。"""
    import pandas as pd
    from framework import stats
    from framework.ledger import trade_row
    from checks.precheck import run
    stats.load(BT_PATH)
    cal = weekday_cal(n=500)
    sp = Split(cal.days[200], cal.days[270])
    rows = []
    for i, (sym, a, b, h) in enumerate([("2330", 5, 9, "h1"), ("2317", 5, 9, "h2"), ("2454", 9, 14, "h1"), ("2330", 9, 12, "h3")]):
        rows.append(trade_row(cal, sp, trade_id=i, combo="H5", is_etest=False, symbol=sym, direction="long",
                              info_time=f"{cal.days[a-1]} 14:30", entry_time=f"{cal.days[a]} 09:00",
                              entry_date=cal.days[a], entry_session="open", entry_px=100,
                              exit_date=cal.days[b], exit_session="close", exit_px=101 + i, actions=[],
                              cluster=str(cal.days[a]), price_series_hash=h))
    df = pd.DataFrame(rows)
    df["symbol"] = df["symbol"].astype(object); df.loc[1, "symbol"] = 2317   # 代號變數字
    res = run(df, report_text="①…②…③… 時點未違反")
    fails = {item for lvl, item, _ in res if lvl == "FAIL"}
    warns = {item for lvl, item, _ in res if lvl == "WARN"}
    assert "價格序列不重複對到不同代號" in fails                # h1 對到 2330 與 2454
    assert "同股同參數持倉不重疊" in fails                       # 2330 第 9 日收盤出、第 9 日開盤進
    assert "代號欄為文字格式" in fails
    assert "斷言字眼須附證據位置" in warns
    df2 = df.copy(); df2.loc[0, "ret"] = 0.5; df2.loc[0, "ret_by"] = "hand"
    fails2 = {item for lvl, item, _ in run(df2) if lvl == "FAIL"}
    assert "持有日與報酬由框架計算" in fails2


@need_bt
def test_r52_event_period_after_announcement():
    """退回-52：038 凱碩 8059 買回期間晚於公告一年，占量用到未來成交量 → 必須擋下。"""
    import pandas as pd
    from framework import stats
    from framework.ledger import trade_row
    from checks.precheck import run
    stats.load(BT_PATH)
    cal = weekday_cal(n=500)
    r = trade_row(cal, None, trade_id="8059-1", combo="T1", is_etest=False, symbol="8059", direction="short",
                  info_time=f"{cal.days[10]} 14:30", entry_time=f"{cal.days[11]} 09:00", entry_date=cal.days[11],
                  entry_session="open", entry_px=50, exit_date=cal.days[20], exit_session="close", exit_px=48,
                  actions=[], announce_date=str(cal.days[10]), event_start=str(cal.days[260]),
                  feature_end=str(cal.days[300]), price_series_hash="x")
    res = run(pd.DataFrame([r]))
    lv = {item: lvl for lvl, item, _ in res}
    assert lv["訊號所用資料不晚於訊號日"] == "FAIL"
    assert lv["事件期間起點晚於公告日 60 天以上"] == "WARN"


# 退回-57、退回-04 的真實資料版在 tests/test_data_layer.py；
# 退回-55（美股 GGP／GM 同序列）不在台股資料層，以 test_precheck_end_to_end 的價格序列雜湊檢查覆蓋。


def test_r38_original_case_8072_cash_reduction():
    """退回-38 原案：陞泰 8072 現金減資（2017-09-08 除權），每舊股換 0.8 股並退還 2 元。
    進場 20.05、出場 22.85（2017-09-20 收盤）；原案正確值 (22.85×0.8＋2)÷20.05−1＝+1.147132%，
    R03 錯值 0.769%（價格比例連乘）。數值依 Eve 第一期審查引述之原案（防錯清單退回-38）。"""
    act = Action(date(2017, 9, 8), "現金減資", share_ratio=0.8, cash=2.0, source="025 R04 原案")
    r = trade_return("long", 20.05, 22.85, "2017-08-17", "2017-09-20", [act]).ret
    assert r == pytest.approx(22.85 * 0.8 / 20.05 + 2 / 20.05 - 1, abs=1e-15)
    assert round(r * 100, 6) == 1.147132
    assert abs(r - 0.00769) > 0.003
