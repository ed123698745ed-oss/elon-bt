"""第二期資料層（候選）：日期一致、處置起迄、註記代碼覆蓋。需 P2_OUT 指向 build_phase2 輸出。"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_layer.phase2_tools import DOWNTICK_35_PERIODS, ban_rule, detail_period, disposal_intervals, sec_kind, sec_kind_series

OUT = os.environ.get("P2_OUT", "/home/claude/raw_p2/out")
CALP = os.environ.get("CAL", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jobs", "trading_days.txt"))
need = pytest.mark.skipif(not os.path.exists(os.path.join(OUT, "index_daily.parquet")), reason="需要第二期 build 輸出")


def _cal():
    return set(pd.to_datetime(open(CALP).read().split()))


@need
def test_index_daily_dates_and_ohlc():
    ix = pd.read_parquet(os.path.join(OUT, "index_daily.parquet"))
    cal = _cal()
    assert not ix["date"].duplicated().any()
    inside = ix[ix["date"] <= max(cal)]
    assert inside["date"].isin(cal).all()
    for p in ("taiex", "tpex"):
        x = ix.dropna(subset=[f"{p}_close"])
        assert ((x[f"{p}_low"] <= x[f"{p}_close"] + 1e-9) & (x[f"{p}_close"] <= x[f"{p}_high"] + 1e-9)).all()
    assert ix.loc[ix["date"] >= "2003-01-02", "taiex_tri_close"].notna().all()


@need
def test_index_every_trading_day_present():
    """每個交易日都要有指數（防整月漏抓）：加權 1999-01-05 起、櫃買 2000-01 起、報酬指數 2003-01 起。"""
    ix = pd.read_parquet(os.path.join(OUT, "index_daily.parquet")).set_index("date")
    cal = sorted(_cal())
    for col, start in (("taiex_close", "1999-01-05"), ("tpex_close", ix["tpex_close"].dropna().index.min()), ("taiex_tri_close", "2003-01-02")):
        days = [d for d in cal if d >= pd.Timestamp(start)]
        miss = [d for d in days if not (d in ix.index and pd.notna(ix.at[d, col]))]
        assert not miss, (col, miss[:5], len(miss))
    assert ix["tpex_close"].dropna().index.min() <= pd.Timestamp("2000-01-31")


@need
def test_disposal_periods_valid():
    sv = pd.read_parquet(os.path.join(OUT, "surveillance.parquet"))
    p = sv[sv["kind"] == "處置"]
    ok = p.dropna(subset=["start", "end"])
    assert (ok["start"] <= ok["end"]).all()
    far = ok["parse_note"].str.contains("逾 3 個交易日")
    assert far.sum() <= 20                                 # 起日距公告超過 3 個交易日者逐筆標註、不推估
    allowed = {"", "處置迄日非交易日（官方規定遇休市順延，實際日期未核）", "處置起日非交易日（官方規定遇休市順延，實際日期未核）",
               "公告內容為取消措施，起迄與措施需人工核對", "撮合間隔未解析",
               "處置起日距公告逾 3 個交易日（原公告待核）"}
    notes = set(n for s in sv["parse_note"] for n in s.split("；"))
    assert notes <= allowed, notes - allowed
    assert not sv.duplicated(["market", "kind", "announce", "code", "start", "reason"]).any()


@need
def test_margin_codes_covered_and_effective_next_day():
    m = pd.read_parquet(os.path.join(OUT, "margin_flags.parquet"), columns=["market", "data_date", "effective", "unknown_codes"])
    assert set("".join(m["unknown_codes"].unique())) <= {"$", "E"}       # 官方說明未列的只有櫃買早年 $、E
    cal = sorted(_cal())
    nxt = dict(zip(cal, cal[1:]))
    s = m.dropna(subset=["effective"]).drop_duplicates(["data_date"])
    assert (s["effective"] == s["data_date"].map(nxt)).all()


@need
def test_margin_flags_every_trading_day_present():
    m = pd.read_parquet(os.path.join(OUT, "margin_flags.parquet"), columns=["market", "data_date", "code"])
    assert not m.duplicated(["market", "data_date", "code"]).any()
    cal = sorted(_cal())
    for market, start in (("上市", "2001-01-02"), ("上櫃", "2007-01-02")):
        have = set(m.loc[m["market"] == market, "data_date"])
        miss = [d for d in cal if d >= pd.Timestamp(start) and d not in have]
        assert not miss, (market, miss[:5], len(miss))


@need
def test_downtick_list_keys():
    d = pd.read_parquet(os.path.join(OUT, "downtick_list.parquet"))
    assert not d.duplicated(["date", "market", "code"]).any()
    assert d["date"].isin(_cal()).all()
    assert d["date"].min() >= pd.Timestamp("2013-09-18")


KNOWN_MARK_GAPS = {(pd.Timestamp("2019-10-02"), "上櫃")}      # 官方回覆只有日期佔位列（2026-11-07 重抓仍相同），另一市場同日有名單


@need
def test_downtick_coverage_gaps_are_declared_and_have_no_rows():
    c = pd.read_parquet(os.path.join(OUT, "downtick_coverage.parquet"))
    d = pd.read_parquet(os.path.join(OUT, "downtick_list.parquet"), columns=["date", "market"])
    cal = sorted(_cal())
    for market, start in (("上市", "2013-09-23"), ("上櫃", "2013-09-18")):
        days = {x for x in cal if x >= pd.Timestamp(start)}
        assert days <= set(c.loc[c["market"] == market, "date"])      # 每個交易日都有覆蓋狀態
    bad = c[c["status"] != "有名單"]
    assert {(r.date, r.market) for r in bad.itertuples()} == KNOWN_MARK_GAPS, bad
    assert bad["status"].str.startswith("資料缺口").all()
    gap = d.merge(bad[["date", "market"]], on=["date", "market"])
    assert gap.empty                                              # 缺口日不可有任何名單列


@need
def test_downtick_ban_rule_periods():
    d = pd.read_parquet(os.path.join(OUT, "downtick_list.parquet"), columns=["date", "ban_rule"])
    u = d.drop_duplicates("date")
    in35 = u["date"].map(lambda x: any(a <= x <= b for a, b in DOWNTICK_35_PERIODS))
    assert (u.loc[in35, "ban_rule"] == "跌幅達3.5%").all() and (u.loc[~in35, "ban_rule"] == "跌停").all()
    assert in35.sum() == 135                                      # 櫃買標題改字 134 日＋2023-02-23（措施當日仍有效）
    assert ban_rule("2020-03-19") == "跌停" and ban_rule("2020-03-20") == "跌幅達3.5%" and ban_rule("2020-06-10") == "跌停"
    assert ban_rule("2022-10-24") == "跌幅達3.5%" and ban_rule("2023-02-23") == "跌幅達3.5%" and ban_rule("2023-02-24") == "跌停"


@need
def test_fulldelivery_keys():
    p = os.path.join(OUT, "fulldelivery.parquet")
    d = pd.read_parquet(p)
    if not len(d):
        pytest.skip("尚未下載")
    assert not d.duplicated(["date", "code"]).any()
    assert d["date"].isin(_cal()).all() and d["date"].min() >= pd.Timestamp("2004-12-24")
    miss = [x for x in sorted(_cal()) if x >= pd.Timestamp("2004-12-24") and x not in set(d["date"])]
    assert not miss, miss[:5]
    pre = d["date"] < pd.Timestamp("2007-11-01")                 # 官方欄位自 2007-11-01 才有分盤欄：之前未知，不可當 False
    assert d.loc[pre, "period_auction"].isna().all() and d.loc[~pre, "period_auction"].notna().all()


@need
def test_sec_kind_on_all_tables():
    limits = {"surveillance": 100, "margin_flags": 0, "downtick_list": 0, "fulldelivery": 0}   # 「其他」容許列數
    for name, cap in limits.items():
        p = os.path.join(OUT, f"{name}.parquet")
        if not os.path.exists(p):
            continue
        t = pd.read_parquet(p, columns=["code", "sec_kind"])
        assert t["sec_kind"].notna().all()
        assert (sec_kind_series(t["code"]) == t["sec_kind"]).all()
        assert (t["sec_kind"] == "其他").sum() <= cap, t.loc[t["sec_kind"] == "其他", "code"].value_counts().head()
    assert {sec_kind(c) for c in ["2330", "0050", "006208", "00631L", "00636", "24091", "910322", "07396P", "01001T", "2887Z1"]} == \
        {"普通股", "ETF", "可轉債", "TDR", "權證", "受益證券", "特別股／字尾代號"}
    assert sec_kind("2330") == "普通股" and sec_kind("006208") == "ETF" and sec_kind("24091") == "可轉債" and sec_kind("230a") == "其他"


@need
def test_disposal_period_flags_and_merge():
    sv = pd.read_parquet(os.path.join(OUT, "surveillance.parquet"))
    p = sv[sv["kind"] == "處置"].dropna(subset=["start", "end"])
    assert (p.loc[p["end"] == p["start"], "period_flag"].str.contains("起訖同日")).all()
    assert (p.loc[p["period_days"] > 60, "period_flag"].str.contains("期間逾60日")).all()
    assert (p.loc[p["period_days"] <= 60, "period_flag"].str.contains("期間逾60日") == False).all()
    assert sv.loc[sv["kind"] != "處置", "period_flag"].eq("").all() and not sv.loc[sv["kind"] != "處置", "overlap_prev"].any()
    iv = disposal_intervals(sv)
    assert not iv.empty and (iv["start"] <= iv["end"]).all()
    for _, g in iv.groupby(["market", "code"]):                    # 合併後同檔區間互不重疊
        g = g.sort_values("start")
        assert (g["start"].iloc[1:].values > g["end"].iloc[:-1].values).all()


def test_disposal_intervals_merges_overlap_and_drops_cancel():
    t = pd.Timestamp
    sv = pd.DataFrame({"kind": ["處置"] * 4, "market": ["上市"] * 4, "code": ["2330"] * 4,
                       "start": [t("2024-01-02"), t("2024-01-10"), t("2024-02-01"), t("2024-03-01")],
                       "end": [t("2024-01-15"), t("2024-01-25"), t("2024-02-10"), t("2024-03-01")],
                       "period_flag": ["", "", "", "取消／恢復公告；起訖同日"]})
    sv["period_days"] = (sv["end"] - sv["start"]).dt.days + 1
    iv = disposal_intervals(sv)
    assert iv.values.tolist() == [["上市", "2330", t("2024-01-02"), t("2024-01-25")], ["上市", "2330", t("2024-02-01"), t("2024-02-10")]]



def test_detail_period_parsing():
    t = pd.Timestamp
    assert detail_period("自民國一百零九年三月二十七日起至一百零九年四月十三日﹝十個營業日") == (t("2020-03-27"), t("2020-04-13"))
    assert detail_period("爰自96年7月30日起五個營業日（96年7月30日至8月3日，如遇休市則順延執行）") == (t("2007-07-30"), t("2007-08-03"))
    assert detail_period("（１１４年１２月２９日至１月６日）") == (t("2025-12-29"), t("2026-01-06"))
    assert detail_period("無日期") == (None, None)


@need
def test_disposal_table_vs_detail_conflicts_flagged():
    """Eve 退回 c2：櫃買 2410 2007-07-27 表格 7/27～8/02、內文 7/30～8/03，必須標待核，合併區間預設取聯集。"""
    sv = pd.read_parquet(os.path.join(OUT, "surveillance.parquet"))
    p = sv[sv["kind"] == "處置"]
    cf = p["detail_start"].notna() & ((p["detail_start"] != p["start"]) | (p["detail_end"] != p["end"]))
    assert (p.loc[cf, "period_flag"].str.contains("表格與內文日期不符")).all()
    assert not p.loc[~cf, "period_flag"].str.contains("表格與內文日期不符").any()
    r = p[(p["code"] == "2410") & (p["announce"] == "2007-07-27")]
    assert len(r) == 1 and "表格與內文日期不符" in r["period_flag"].iloc[0]
    iv = disposal_intervals(sv)
    g = iv[(iv["code"] == "2410") & (iv["start"] <= "2007-08-03") & (iv["end"] >= "2007-07-27")]
    assert (g["end"] >= pd.Timestamp("2007-08-03")).any()
