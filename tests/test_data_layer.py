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


def test_r13_capital_reduction_day_is_flagged_until_action_known():
    """退回-13：1512 瑞利 2023-03-13 減資恢復買賣，價格 5.8→16.0。公司行動表未接上前，必須標跳動、不得直接算報酬。"""
    r = k(["1512"]).set_index("date").loc["2023-03-13"]
    assert bool(r["jump_flag"])


def test_zero_price_rows_are_no_trade():
    d = k(["1475"])
    assert not ((d["close"] == 0) & ~d["no_trade"]).any()
