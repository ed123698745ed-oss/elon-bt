"""以真實資料檢查資料層（需先跑 data_layer/build.py；設 ELON_OUT 指向輸出資料夾）。"""
import os
import pandas as pd
import pytest

OUT = os.environ.get("ELON_OUT", "/home/claude/raw_dl/out")
pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(OUT, "daily_k.parquet")), reason="需要 build 輸出")


def k(ids):
    return pd.read_parquet(os.path.join(OUT, "daily_k.parquet"), filters=[("stock_id", "in", ids)])


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
    換股比只用證交所減資表公告值（不用 5.8/16.09 反推）；資料層未取得官方值時本測試應失敗而非放行。"""
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


def test_r04_real_one_price_limit_up_not_filled():
    """退回-04 真實資料：找一天一價鎖漲停（開高低收皆為漲停價），開盤買進必須不成交。"""
    from framework.market import judge_fill
    d = pd.read_parquet(os.path.join(OUT, "daily_k.parquet"), filters=[("stock_id", "in", ["3260", "2603", "6147", "3105"])],
                        columns=["date", "stock_id", "open", "high", "low", "close", "volume", "limit_up", "limit_down"])
    locked = d[(d["open"] == d["high"]) & (d["high"] == d["low"]) & (d["low"] == d["close"]) & (d["close"] == d["limit_up"])]
    assert len(locked) > 0
    bar = locked.iloc[0].to_dict()
    f = judge_fill(bar, "long", "entry", "open")
    assert not f.ok and "一價鎖漲停" in f.reason


# ---------------------------------------------------------------- 退回-67（Eve 第一期審查）真實資料
def test_r36_zhongzhan_119_market_days():
    """退回-36 原案：中湛 6236 2011-06-27 進、2011-12-12 出＝119 個市場日（舊做法數個股有效日 K 得 40）。"""
    from framework.core import Calendar
    cal = Calendar(pd.read_parquet(os.path.join(OUT, "calendar.parquet"))["date"].dt.date)
    assert cal.hold_days("2011-06-27", "2011-12-12") == 119
    d = k(["6236"])
    rows = d[(d["date"] >= "2011-06-27") & (d["date"] <= "2011-12-12") & ~d["no_trade"]]
    assert len(rows) == 40


def test_r67_otc_period_before_transfer_kept():
    """退回-67：工信 5521 1999-11-18 上櫃、2012-12-18 轉上市 → 轉上市前的合法上櫃期間保留。
    FinMind 5521 行情自 2003-08-01 起（更早無資料），故主日K起點為 2003-08-01，且該段為上櫃。"""
    d = k(["5521"])
    assert d["date"].min() == pd.Timestamp("2003-08-01")
    assert set(d.loc[d["date"] < "2012-12-18", "market"]) == {"上櫃"}
    assert set(d.loc[d["date"] >= "2012-12-18", "market"]) == {"上市"}
    first5 = d[(d["date"] >= "2012-12-18")].head(5)
    assert not first5["limit_src"].str.startswith(("無漲跌幅", "待查")).any()   # 轉上市不是初次掛牌，照常有漲跌幅


def test_r57_wangdao_emerging_still_excluded():
    d = k(["2897"])
    assert d["date"].min() == pd.Timestamp("2017-05-05")


def test_r67_emerging_row_quarantined():
    """清惠 5259 2012-02-10 為興櫃 → 不在主日K，在隔離檔且原因為官方查無。"""
    assert not (k(["5259"])["date"] == "2012-02-10").any()
    q = pd.read_parquet(os.path.join(OUT, "daily_k_quarantine.parquet"), filters=[("stock_id", "in", ["5259"])])
    r = q[q["date"] == "2012-02-10"]
    assert len(r) == 1 and r.iloc[0]["quarantine_reason"].startswith("官方查無")


@pytest.mark.parametrize("sid,day", [("4728", "2012-01-12"), ("6821", "2023-05-23"), ("6913", "2024-10-04"), ("1776", "2016-05-10")])
def test_r67_first5_no_limit_not_jump(sid, day):
    r = k([sid]).set_index("date").loc[day]
    assert r["limit_src"] == "無漲跌幅（初次掛牌前五日）" and pd.isna(r["limit_up"]) and not bool(r["jump_flag"])


@pytest.mark.parametrize("sid,day,ref,up,dn", [("8938", "2003-07-31", 104.19, 111.0, 97.0), ("4126", "2004-09-02", 19.49, 20.80, 18.20)])
def test_r67_tpex_early_exright_official(sid, day, ref, up, dn):
    r = k([sid]).set_index("date").loc[day]
    assert (r["ref_price"], r["limit_up"], r["limit_down"], r["limit_src"]) == (ref, up, dn, "官方除權息表")
    assert not bool(r["jump_flag"])


def test_r67_inferred_ratios_not_in_share_ratio():
    """A5：反推換股比只在 share_ratio_inferred，share_ratio 必為官方公告值或空。"""
    c = ca_rows()
    red = c[c["kind"].isin(["減資", "面額變更"])]
    assert red.loc[red["ratio_basis"] != "官方公告值", "share_ratio"].isna().all()
