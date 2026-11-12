"""可轉債組（cb）：鍵值、來源欄、推算值不進主欄、日期順序、轉換價軌跡去重。環境 CB_OUT。"""
import os

import pandas as pd
import pytest

OUT = os.environ.get("CB_OUT", "out_cb")
need = pytest.mark.skipif(not os.path.exists(os.path.join(OUT, "cb_issues.parquet")), reason="需要 CB_OUT")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@need
def test_keys_and_coverage():
    d = pd.read_parquet(os.path.join(OUT, "cb_issues.parquet"))
    seed = pd.read_csv(os.path.join(ROOT, "data_seed", "cb_seed_20260830_main.csv"), dtype={"代號": str})
    assert d["bond_id"].is_unique
    assert set(d["bond_id"]) == set(seed["代號"].str.strip())
    assert set(d["official_status"]) <= {"官方取得", "已查月份未命中", "下載失敗"}
    miss = d[d["official_status"] == "已查月份未命中"]
    assert (miss["months_tried_n"] > 0).all() and miss["months_tried"].notna().all()


@need
def test_sources_and_no_estimates_in_main():
    d = pd.read_parquet(os.path.join(OUT, "cb_issues.parquet"))
    for k in ("issue_date", "maturity_date", "conv_start", "conv_end", "amount_issued", "guarantee", "coupon_rate", "delist_date"):
        has = d[k].notna()
        assert d.loc[has, k + "_src"].notna().all(), k
        assert not d.loc[has, k + "_src"].str.contains("推算|反推").any(), k
        assert d.loc[~has, k + "_src"].isna().all(), k
    for k in ("conv_start", "issue_date"):
        if k + "_est" in d.columns:
            e = d[k + "_est"].notna()
            assert d.loc[e, k + "_est_src"].str.contains("推算|反推").all()


@need
def test_official_rows_use_official_values():
    d = pd.read_parquet(os.path.join(OUT, "cb_issues.parquet"))
    o = d[d["official_status"] == "官方取得"]
    assert (o["issue_date_src"] == "MOPS t120sg01").all()
    assert (o["maturity_date_src"] == "MOPS t120sg01").all()
    assert o["snapshot_month"].str.fullmatch(r"\d{6}").all()


@need
def test_date_order():
    d = pd.read_parquet(os.path.join(OUT, "cb_issues.parquet"))
    for a, b in (("issue_date", "maturity_date"), ("conv_start", "conv_end"), ("issue_date", "conv_start")):
        x = d[d[a].notna() & d[b].notna()]
        bad = x[x[a] > x[b]]
        assert len(bad) <= 5, bad[["bond_id", a, b]].head()   # 容許少數官方原值異常，逐筆列於驗收說明


@need
def test_conv_price_dedup():
    t = pd.read_parquet(os.path.join(OUT, "cb_conv_price.parquet"))
    assert not t.duplicated(["bond_id", "effective", "price_before", "price_after"]).any()
    assert t["src"].notna().all()


@need
def test_identity_no_seed_values_when_generation_doubtful():
    """世代疑義：清單值不得出現在主欄（Eve 2026-11-12：44161、140201、25472）。"""
    d = pd.read_parquet(os.path.join(OUT, "cb_issues.parquet"))
    g = d[d["identity_status"] == "世代疑義"]
    for c in [c for c in d.columns if c.endswith("_src") and not c.endswith("_est_src")]:
        assert not g[c].fillna("").str.startswith("種子").any(), c
    for b in ("44161", "140201", "25472"):
        assert d.loc[d["bond_id"] == b, "identity_status"].iloc[0] == "世代疑義", b


@need
def test_conv_price_assigned_within_issue_life():
    d = pd.read_parquet(os.path.join(OUT, "cb_issues.parquet"))
    t = pd.read_parquet(os.path.join(OUT, "cb_conv_price.parquet"))
    q = pd.read_parquet(os.path.join(OUT, "cb_conv_price_quarantine.parquet"))
    assert (t["assign_status"] == "已歸屬").all() and (q["assign_status"] != "已歸屬").all()
    j = t.merge(d[["bond_id", "issue_date", "maturity_date", "delist_date"]], on="bond_id")
    assert len(j) == len(t)
    assert (j["effective"] >= j["issue_date"]).all()
    end = j["delist_date"].fillna(j["maturity_date"])
    assert (end.isna() | (j["effective"] <= end)).all()
    assert t["available_date"].notna().all()
    # c1 的 21 筆「調整早於發行日」不得留在已歸屬表
    c1_early = {("140201", y) for y in range(2008, 2013)} | {("25472", y) for y in range(2000, 2018)}
    assert not any((b, e.year) in c1_early and e < pd.Timestamp("2017-11-23") for b, e in zip(t["bond_id"], t["effective"]) if b in ("140201", "25472") and (b == "25472" or e.year <= 2012))


@need
def test_conv_price_asof_respects_available_date():
    """申報日晚於生效日的調整：生效日當天不得讀到調整後價格（181 筆回歸檢查，含隔離前全部）。"""
    import sys
    sys.path.insert(0, ROOT)
    from framework.cb import conv_price_asof
    d = pd.read_parquet(os.path.join(OUT, "cb_issues.parquet"))
    t = pd.read_parquet(os.path.join(OUT, "cb_conv_price.parquet"))
    late = t[t["available_date"] > t["effective"]]
    assert len(late) > 0
    for r in late.itertuples(index=False):
        p = conv_price_asof(t, d, r.bond_id, r.effective, fallback=False)
        prior = t[(t["bond_id"] == r.bond_id) & (t["effective"] <= r.effective) & (t["available_date"] < r.effective)]
        exp = float(prior.sort_values(["effective", "available_date"]).iloc[-1]["price_after"]) if len(prior) else None
        assert p == exp, (r.bond_id, r.effective, p, exp)   # 這一筆本身不得被選到
        assert conv_price_asof(t, d, r.bond_id, r.available_date + pd.Timedelta(days=1)) is not None
