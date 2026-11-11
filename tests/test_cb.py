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
    assert set(d["official_status"]) <= {"官方取得", "官方查無", "未下載"}


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
