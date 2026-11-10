"""退回-69（外部審查）：升降單位依日期、ETF 另表、3.5% 跌幅期間、基準價鏈、減資恢復日參考價、成交量缺值、股利公告整列取值。"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework.elon_tools import limit_prices, tick_size, next_base, security_kind  # noqa: E402
from framework.market import judge_fill  # noqa: E402

OUT = os.environ.get("ELON_OUT", "/home/claude/raw_dl/out")
need_out = pytest.mark.skipif(not os.path.exists(os.path.join(OUT, "daily_k.parquet")), reason="需要 build 輸出")


# ---------- 規則（不需資料） ----------
def test_old_tick_table_before_2005_03_01():
    """外部審查案例（官方除權息表值）：8938 2003-07-31 參考價 104.19 → 111.0／97.0；4126 2004-09-02 參考價 19.49 → 20.8／18.2。"""
    assert limit_prices(104.19, "2003-07-31") == (111.0, 97.0)
    assert limit_prices(19.49, "2004-09-02") == (20.8, 18.2)


def test_tick_table_boundaries():
    assert float(tick_size(14.99, "stock", "2005-02-28")) == 0.05 and float(tick_size(15, "stock", "2005-02-28")) == 0.1
    assert float(tick_size(149.5, "stock", "2005-02-28")) == 0.5 and float(tick_size(150, "stock", "2005-02-28")) == 1
    assert float(tick_size(15, "stock", "2005-03-01")) == 0.05 and float(tick_size(100, "stock", "2005-03-01")) == 0.5
    assert float(tick_size(49.99, "etf", "2004-01-02")) == 0.01 and float(tick_size(55, "etf", "2004-01-02")) == 0.05


def test_etf_kind_and_limits():
    assert security_kind("0050") == "etf" and security_kind("00632R") == "etf" and security_kind("2330") == "stock"
    assert limit_prices(55.0, "2010-01-04", "etf") == (58.85, 51.15)


def test_down_limit_35pct_window():
    """2008-10-13～10-24 跌幅 3.5%（央行日誌）；10-27 恢復 7%。"""
    assert limit_prices(5.80, "2008-10-13") == (6.2, 5.6)
    assert limit_prices(5.80, "2008-10-27") == (6.2, 5.4)
    assert limit_prices(100.0, "2000-11-01")[1] == 96.5


def test_next_base_rule():
    """無收盤：2011-03-28 起依收盤時最高買價／最低賣價；之前沿用當日基準。"""
    assert next_base(20.0, 21.0, None, None, "2010-01-05") == 21.0
    assert next_base(20.0, float("nan"), 20.5, 21.0, "2011-03-25") == 20.0
    assert next_base(20.0, float("nan"), 20.5, 21.0, "2011-03-28") == 20.5
    assert next_base(20.0, float("nan"), 19.0, 19.5, "2012-01-02") == 19.5
    assert next_base(20.0, float("nan"), 19.0, 20.5, "2012-01-02") == 20.0


def test_judge_fill_nan_volume_is_insufficient():
    bar = dict(open=10, high=10, low=10, close=10, volume=float("nan"), limit_up=10.7, limit_down=9.3, limit_src="規則")
    f = judge_fill(bar, "long", "entry", "open")
    assert not f.ok and f.insufficient


def test_dividend_dedupe_takes_whole_latest_row(monkeypatch, tmp_path):
    from data_layer import corp_actions as ca
    rows = [dict(stock_id="1234", CashEarningsDistribution=1.0, CashStatutorySurplus=0, StockEarningsDistribution=0,
                 StockStatutorySurplus=0, CashExDividendTradingDate="2020-07-01", CashDividendPaymentDate="2020-07-20",
                 AnnouncementDate="2020-05-01", AnnouncementTime="10:00:00"),
            dict(stock_id="1234", CashEarningsDistribution=1.2, CashStatutorySurplus=0, StockEarningsDistribution=0,
                 StockStatutorySurplus=0, CashExDividendTradingDate="2020-07-01", CashDividendPaymentDate=None,
                 AnnouncementDate="2020-06-01", AnnouncementTime="10:00:00")]
    monkeypatch.setattr(ca.glob, "glob", lambda p: ["x"])
    monkeypatch.setattr(ca, "_jl", lambda p: {"data": rows})
    d = ca.dividends()
    r = d[d["kind"] == "現金股利"].iloc[0]
    assert r["cash"] == 1.2 and (r["cash_date"] is None or pd.isna(r["cash_date"]))   # 不混入舊公告的發放日


# ---------- 資料（需 build 輸出） ----------
def _k(ids):
    return pd.read_parquet(os.path.join(OUT, "daily_k.parquet"), filters=[("stock_id", "in", ids)])


@need_out
def test_limit_src_values_known():
    s = pd.read_parquet(os.path.join(OUT, "daily_k.parquet"), columns=["limit_src"])["limit_src"].unique()
    allowed = {"官方除權息表", "官方行情表（櫃買次日漲跌停）", "規則（官方基準價鏈）", "官方減資參考價＋規則", "規則",
               "無漲跌幅（初次掛牌前五日）", "無漲跌幅（櫃買官方）", "待查（過渡期初次掛牌前五日）",
               "待查（前一交易日無成交，基準價未驗證）", "缺參考價", "待查（盤中價超出推算漲跌停）", "待查（開高低為0）"}
    assert set(s) <= allowed, set(s) - allowed


@need_out
def test_plain_rule_only_before_official_quotes():
    """「規則」（前收推算）只出現在官方逐日行情之前：上市 2004-02-11、上櫃 2007-07-02。"""
    d = pd.read_parquet(os.path.join(OUT, "daily_k.parquet"), columns=["date", "market", "limit_src"])
    r = d[d["limit_src"] == "規則"]
    assert (r.loc[r["market"] == "上市", "date"] < "2004-02-11").all()
    assert (r.loc[r["market"] == "上櫃", "date"] < "2007-07-03").all()


@need_out
def test_reduction_resume_day_uses_official_ref():
    """外部審查：1512 瑞利 2023-03-13 減資恢復買賣，漲跌停不得以停止買賣前收盤推算。"""
    r = _k(["1512"]).set_index("date").loc["2023-03-13"]
    assert r["limit_src"] in ("官方減資參考價＋規則", "規則（官方基準價鏈）", "官方除權息表", "官方行情表（櫃買次日漲跌停）")
    assert r["limit_down"] > 5.8 * 1.1      # 停止買賣前收盤 5.8，若誤用則跌停約 5.2


@need_out
def test_tpex_official_limit_used_example():
    """櫃買 3147 2018-11-21：前一日無成交，官方次日漲停 21.00、跌停 17.20（非以最後成交 19.30 推算）。"""
    d = _k(["3147"])
    r = d.set_index("date").loc["2018-11-21"]
    assert (r["limit_up"], r["limit_down"]) == (21.0, 17.2)


@need_out
def test_daily_k_no_duplicate_keys():
    """外部審查「日K列數差 1」：舊標籤 data-20261105 有 1 列重複（3454 2011-07-27），r67 起已無；此後每版都要檢查。"""
    d = pd.read_parquet(os.path.join(OUT, "daily_k.parquet"), columns=["date", "stock_id"])
    assert not d.duplicated().any()



def test_r70_low_price_limit_at_least_one_tick():
    """Eve 退回 r69：1450 2005-06-16 基準 0.13，7% 取整後漲跌停都等於基準；應以一個升降單位計 → 0.14／0.12。"""
    from framework.elon_tools import limit_prices
    assert limit_prices(0.13, "2005-06-16") == (0.14, 0.12)
    assert limit_prices(0.04, "2003-05-01") == (0.05, 0.03)
    assert limit_prices(10, "2005-06-16") == (10.7, 9.3)            # 一般價位不受影響
    for ref in (0.05, 0.08, 0.1, 0.13, 0.14):
        u, d = limit_prices(ref, "2005-06-16")
        assert u > ref and d < ref



@need_out
def test_r70_no_unflagged_price_outside_limits():
    """自查（退回-70）：凡成交價超出推算漲跌停的列，必須已標跳動或限價來源為待查／缺參考價／無漲跌幅；開高低不得為 0。"""
    d = pd.read_parquet(os.path.join(OUT, "daily_k.parquet"),
                        columns=["open", "high", "low", "close", "limit_up", "limit_down", "limit_src", "jump_flag", "no_trade", "price_note"])
    t = d[~d["no_trade"]]
    assert not ((t["open"] <= 0) | (t["high"] <= 0) | (t["low"] <= 0)).any()
    out = (t["high"] > t["limit_up"] + 1e-9) | (t["low"] < t["limit_down"] - 1e-9)
    ok = t["jump_flag"] | t["limit_src"].str.startswith("待查") | (t["limit_src"] == "缺參考價") | t["limit_src"].str.startswith("無漲跌幅")
    assert not (out & ~ok).any(), int((out & ~ok).sum())


def test_r70_judge_fill_insufficient_for_new_pending_sources():
    from framework.market import judge_fill
    for src in ("待查（盤中價超出推算漲跌停）", "待查（開高低為0）"):
        bar = {"open": 10, "high": 10, "low": 10, "close": 10, "volume": 1000, "limit_up": 11, "limit_down": 9, "limit_src": src}
        f = judge_fill(bar, "long", "entry", "open")
        assert f.insufficient and not f.ok
