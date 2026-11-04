"""以真實資料檢查資料層（需先跑 data_layer/build.py；設 ELON_OUT 指向輸出資料夾）。"""
import os
import pandas as pd
import pytest

OUT = os.environ.get("ELON_OUT", "/home/claude/raw_dl/out")
pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(OUT, "daily_k.parquet")), reason="需要 build 輸出")


def k(ids):
    return pd.read_parquet(os.path.join(OUT, "daily_k.parquet"), filters=[("stock_id", "in", ids)])


def test_r57_wangdao_emerging_rows_removed():
    """退回-57：王道銀 2897 官方上市日 2017-05-05 前的興櫃段（2006-12～2017-04）必須剔除。"""
    d = k(["2897"])
    assert d["date"].min() == pd.Timestamp("2017-05-05")


def test_a10_official_exright_limits_used():
    """A10、B6：除權息日參考價與漲跌停用官方值（台泥 2024-07-01：參考價 33.2、漲停 36.5、跌停 29.9）。"""
    r = k(["1101"]).set_index("date").loc["2024-07-01"]
    assert (r["ref_price"], r["limit_up"], r["limit_down"], r["limit_src"]) == (33.2, 36.5, 29.9, "官方除權息表")


def test_r13_capital_reduction_day_not_jump_once_action_known():
    """退回-13：1512 瑞利 2023-03-13 減資恢復買賣，價格 5.8→16.0。公司行動表已有該減資，不再標跳動。"""
    r = k(["1512"]).set_index("date").loc["2023-03-13"]
    assert not bool(r["jump_flag"])


def test_zero_price_rows_are_no_trade():
    d = k(["1475"])
    assert not ((d["close"] == 0) & ~d["no_trade"]).any()


def ca_rows():
    return pd.read_parquet(os.path.join(OUT, "corp_actions.parquet"))


def test_r13_1512_real_capital_reduction():
    """退回-13 真實資料：1512 瑞利 2023-03-01 收盤 5.8 進、2023-05-03 收盤 13.30 出。
    價格直接相除 +129%；固定股數（減資換股比 5.8/16.09）約 −17.3%（審查報告：應約 −17.4%）。"""
    from framework.core import actions_from_table, trade_return
    d = k(["1512"]).set_index("date")
    e, x = d.loc["2023-03-01", "close"], d.loc["2023-05-03", "close"]
    acts = actions_from_table(ca_rows(), "1512")
    r = trade_return("long", e, x, "2023-03-01", "2023-05-03", acts).ret
    assert x / e - 1 == pytest.approx(1.293, abs=0.002)
    assert r == pytest.approx(-0.174, abs=0.002)


def test_r38_8072_real_cash_dividend_fixed_shares():
    """退回-38 真實資料：陞泰 8072 2023-07-12 現金股利 1.0 元，固定股數＋現金，不連乘。"""
    from framework.core import actions_from_table, trade_return
    d = k(["8072"]).set_index("date")
    e, x = d.loc["2023-07-03", "close"], d.loc["2023-07-20", "close"]
    acts = actions_from_table(ca_rows(), "8072")
    r = trade_return("long", e, x, "2023-07-03", "2023-07-20", acts).ret
    assert r == pytest.approx((x + 1.0) / e - 1, abs=1e-12)
    prev = d.loc[:"2023-07-11", "close"].iloc[-1]
    chained = x * prev / (prev - 1.0) / e - 1
    assert abs(chained - r) > 1e-4


def test_insufficient_action_excludes_trade():
    """A5：持有期間碰到資料不足的公司行動 → 排除並寫原因，不推估。"""
    from framework.core import Action, Calendar
    from framework.ledger import trade_row
    import datetime as dt
    cal = Calendar(pd.read_parquet(os.path.join(OUT, "calendar.parquet"))["date"].dt.date)
    acts = [Action(dt.date(2024, 7, 1), "除權息未分類｜資料不足")]
    row = trade_row(cal, None, trade_id=1, combo="X", is_etest=False, symbol="1101", direction="long",
                    info_time="2024-06-27 14:30", entry_time="2024-06-28 09:00", entry_date="2024-06-28",
                    entry_session="open", entry_px=33, exit_date="2024-07-05", exit_session="close", exit_px=34,
                    actions=acts)
    assert row["ret"] is None and "資料不足" in row["excluded_reason"]
