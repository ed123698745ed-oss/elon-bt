"""估值組建置檢查（PBR_OUT＝build_pbr 輸出資料夾）。"""
import os

import pandas as pd
import pytest

OUT = os.environ.get("PBR_OUT", "out")
pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(OUT, "valuation_daily.parquet")), reason="無建置輸出")


@pytest.fixture(scope="module")
def v():
    return pd.read_parquet(os.path.join(OUT, "valuation_daily.parquet"))


@pytest.fixture(scope="module")
def cv():
    return pd.read_parquet(os.path.join(OUT, "valuation_coverage.parquet"))


def test_keys_unique(v):
    assert not v.duplicated(["date", "market", "stock_id"]).any()


def test_codes_are_text(v):
    assert v.stock_id.map(type).eq(str).all()
    assert not v.stock_id.str.contains(r"\s").any()


def test_pbr_nonnegative_or_missing(v):
    x = v.pbr.dropna()
    assert (x >= 0).all()


def test_start_dates(v):
    assert v[v.market == "上市"].date.min() == pd.Timestamp("2005-09-02")
    assert v[v.market == "上櫃"].date.min() == pd.Timestamp("2007-01-02")


def test_coverage_rows_match_data(v, cv):
    ok = cv[cv.status == "ok"].set_index(["date", "market"]).index
    got = v.drop_duplicates(["date", "market"]).set_index(["date", "market"]).index
    assert set(ok) == set(got)


def test_month_end_complete(cv):
    assert not ((cv.status == "missing") & cv.month_end).any()


def test_known_values(v):
    """抽核：官方原檔 2005-09-02 台泥 1.07、2008-04-10 上櫃恩得利 0.98、2026-01-30 台泥 0.91。"""
    def g(d, s, m):
        r = v[(v.date == d) & (v.stock_id == s) & (v.market == m)]
        return None if r.empty else float(r.pbr.iloc[0])
    for d, s, m, want in [("2005-09-02", "1101", "上市", 1.07), ("2008-04-10", "1333", "上櫃", 0.98),
                          ("2026-01-30", "1101", "上市", 0.91)]:
        got = g(pd.Timestamp(d), s, m)
        if got is not None:
            assert abs(got - want) < 1e-9, (d, s, got, want)
