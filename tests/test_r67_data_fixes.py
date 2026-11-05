"""退回-67（Eve 2026-11-05 第一期審查）逐點回歸測試。固定輸入取自官方原始回應（tests/fixtures_r67）。"""
import importlib
import json
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "data_layer"))
FIX = os.path.join(ROOT, "tests", "fixtures_r67")


@pytest.fixture()
def raw_env(monkeypatch):
    monkeypatch.setenv("RAW_DIR", FIX)
    import data_layer.market_history as mh
    import data_layer.corp_actions as ca
    import data_layer.build as b
    for m in (mh, ca, b):
        importlib.reload(m)
    return mh, ca, b


def test_fallback_response_rejected():
    """櫃買舊端點查 2003-07 回傳當日資料 → 日期核對不過，不得存檔。"""
    import fetch_market as f
    j = json.load(open(os.path.join(FIX, "fallback_200307.json"), encoding="utf-8"))
    ok, got = f.check(j, ("date_prefix", "20030701"))
    assert not ok and not got.startswith("2003")


def test_tpex_old_table_ming_an_tai_yi(raw_env):
    """明安 8938 2003-07-31、太醫 4126 2004-09-02 官方參考價與漲跌停（Eve 抽查 D 組）。"""
    _, _, b = raw_env
    ex = b.official_exright()
    a = ex[(ex.stock_id == "8938") & (ex.date == "2003-07-31")].iloc[0]
    assert (a.ref, a.limit_up, a.limit_down) == (104.19, 111.0, 97.0)
    t = ex[(ex.stock_id == "4126") & (ex.date == "2004-09-02")].iloc[0]
    assert (t.ref, t.limit_up, t.limit_down) == (19.49, 20.80, 18.20)
    assert 97.0 <= 105.0 <= 111.0 and 18.20 <= 19.40 <= 20.80  # 收盤在界線內 → 不是跳動


def test_official_reduction_ratio_and_refund(raw_env):
    """同協 5460 2021-11-01 現金減資：每仟股換 960 股、每股退 0.4 元（官方表原值，不用參考價反推）。"""
    _, ca, _ = raw_env
    off = ca.official_reductions()
    r = off[(off.stock_id == "5460")].iloc[0]
    assert r.per_k == 960.0 and r.refund == 0.4 and str(r.ex_date.date()) == "2021-11-01"


def test_xunjie_inferred_ratio_not_used():
    """迅杰 6243：反推 484.5580405 ≠ 公告 484.4551 → 反推值不得進 share_ratio（A5）。"""
    inferred, announced = 484.5580405 / 1000, 484.4551 / 1000
    assert abs(inferred - announced) * 1000 == pytest.approx(0.1029405, abs=1e-7)


def test_otc_history_restored_and_transfer_not_initial(raw_env):
    """工信 5521：1999-11-18 首日上櫃（官方個股月成交），2012-12-18 轉上市 → 轉板不是初次掛牌，不給無限幅。"""
    mh, _, _ = raw_env
    st = pd.DataFrame([dict(stock_id="5521", status="上市", start_date=pd.Timestamp("2012-12-18"), verified=True),
                       dict(stock_id="4728", status="上櫃", start_date=pd.Timestamp("2012-01-10"), verified=True)])
    cal = list(pd.bdate_range("1999-11-01", "2013-01-31"))
    seg = mh.segments(cal, {})
    g = seg[seg.stock_id == "5521"].sort_values("start")
    assert g.iloc[0].start == pd.Timestamp("1999-11-18") and g.iloc[0].market == "上櫃"
    px = pd.DataFrame({"stock_id": ["5521", "5521", "5521"],
                       "date": pd.to_datetime(["1999-11-18", "1999-11-17", "2012-12-17"])})
    assert list(mh.lookup(px, seg)) == ["上櫃", None, "上櫃"]
    ev = mh.listing_events(seg, st)
    e = ev[ev.stock_id == "5521"].sort_values("start")
    assert list(e.market) == ["上櫃", "上市"] and list(e.initial) == [True, False]
    nl = mh.first5_no_limit(ev, cal)
    assert not ((nl.stock_id == "5521") & (nl.date >= "2012-12-18")).any()


def test_initial_listing_first5_no_limit(raw_env):
    """雙美 4728 2012-01-10 初次上櫃：2012-01-12 在前五日內 → 無漲跌幅、不判跳動。"""
    mh, _, _ = raw_env
    st = pd.DataFrame([dict(stock_id="4728", status="上櫃", start_date=pd.Timestamp("2012-01-10"), verified=True)])
    ev = mh.listing_events(pd.DataFrame(columns=["stock_id", "market", "start", "end", "days", "src"]), st)
    cal = pd.bdate_range("2012-01-02", "2012-02-28")
    nl = mh.first5_no_limit(ev, list(cal))
    days = list(nl[nl.stock_id == "4728"].date)
    assert pd.Timestamp("2012-01-12") in days and len(days) == 5
    assert set(nl.no_limit_status) == {"無漲跌幅"}


def test_transition_period_marked_pending(raw_env):
    mh, _, _ = raw_env
    st = pd.DataFrame([dict(stock_id="9999", status="上櫃", start_date=pd.Timestamp("2005-06-01"), verified=True)])
    ev = mh.listing_events(pd.DataFrame(columns=["stock_id", "market", "start", "end", "days", "src"]), st)
    nl = mh.first5_no_limit(ev, list(pd.bdate_range("2005-05-01", "2005-07-29")))
    assert nl.no_limit_status.str.startswith("待查").all()


def test_pre_rule_listing_keeps_limits(raw_env):
    mh, _, _ = raw_env
    st = pd.DataFrame([dict(stock_id="9998", status="上市", start_date=pd.Timestamp("2004-06-01"), verified=True)])
    ev = mh.listing_events(pd.DataFrame(columns=["stock_id", "market", "start", "end", "days", "src"]), st)
    assert mh.first5_no_limit(ev, list(pd.bdate_range("2004-05-01", "2004-07-30"))).empty


def test_etf_not_common_stock(raw_env):
    mh, _, _ = raw_env
    st = pd.DataFrame([dict(stock_id="00981A", status="上市", start_date=pd.Timestamp("2025-05-20"), verified=True)])
    ev = mh.listing_events(pd.DataFrame(columns=["stock_id", "market", "start", "end", "days", "src"]), st)
    assert mh.first5_no_limit(ev, list(pd.bdate_range("2025-05-01", "2025-06-30"))).empty
