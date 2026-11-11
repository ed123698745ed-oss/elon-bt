"""財報修正版（fin-20261107 退回後）建置檢查。FIN_OUT 指向 fin_fix.py 輸出資料夾；沒有就略過。"""
import os

import numpy as np
import pandas as pd
import pytest

OUT = os.environ.get("FIN_OUT", "")
pytestmark = pytest.mark.skipif(not (OUT and os.path.exists(os.path.join(OUT, "financials.parquet"))), reason="需 FIN_OUT")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS = "TaiwanStockFinancialStatements"
NI, NCI = "EquityAttributableToOwnersOfParent", "NoncontrollingInterests"


@pytest.fixture(scope="module")
def df():
    return pd.read_parquet(os.path.join(OUT, "financials.parquet"))


def test_primary_key_unique(df):
    assert not df.duplicated(["stock_id", "date", "dataset", "type"]).any()


def test_no_comprehensive_in_net_income_fields(df):
    s = df[df["dataset"] == IS]
    for t in (NI, NCI):
        x = s[(s["type"] == t) & s["origin_name"].str.contains("綜合損益")]
        assert x.empty, f"{t} 仍混入綜合損益 {len(x)} 列"
    assert s[(s["type"] == "OperatingIncome") & s["origin_name"].str.contains("收入")].empty
    oci = s[s["type"].isin(["OtherComprehensiveIncomeAfterTax", "OtherComprehensiveIncomeAfterTaxThePeriod"])]
    assert not oci["origin_name"].str.contains("綜合損益總額").any()
    assert s[(s["type"] == "TotalConsolidatedProfitForThePeriod") & (s["origin_name"] == "本期損益")].empty
    assert (s["type"] == "-").sum() == 0


def test_origin_whitelist(df):
    wl = pd.read_csv(os.path.join(ROOT, "data_catalog", "fin_origin_whitelist.csv"))
    k = set(map(tuple, wl.itertuples(index=False)))
    o = df[df["src"] == "FinMind"][["dataset", "type", "origin_name"]].drop_duplicates()
    new = [tuple(x) for x in o.itertuples(index=False) if tuple(x) not in k]
    assert not new, new


def test_backfill_src_and_values(df):
    b = df[df["src"] != "FinMind"]
    ok = {"推導：本期淨利−非控制權益淨利", "推導：無非控制權益（本期淨利）", "推導：綜合損益歸屬非控制權益為0",
          "推導：本期淨利−歸母淨利", "財報電子書", "資料不足"}
    assert set(b["src"]) <= ok
    assert b.loc[b["src"] == "資料不足", "value"].isna().all()
    assert b.loc[b["src"] != "資料不足", "value"].notna().all()
    assert set(b["type"]) <= {NI, NCI}


def test_identity_rows(df):
    s = df[df["dataset"] == IS]
    p = s.pivot_table(index=["stock_id", "date"], columns="type", values="value", aggfunc="first")
    iat = p["IncomeAfterTaxes"].where(p["IncomeAfterTaxes"].notna(), p.get("IncomeAfterTax"))
    form = p.get("NetIncomeAttributableToFormerOwnerUnderCommonControl", pd.Series(0.0, index=p.index)).fillna(0)
    d = s[s["src"].isin(["推導：本期淨利−非控制權益淨利", "推導：本期淨利−歸母淨利"])]
    k = list(zip(d["stock_id"], d["date"]))
    gap = (iat.loc[k] - p[NI].loc[k] - p[NCI].loc[k] - form.loc[k]).abs()
    assert (gap <= 1).all()


def test_ebook_matches_eve_spot_check(df):
    """Eve 2026-11-11：1701 中化 2024Q2 歸母淨利 8,025.3 萬元。"""
    r = df[(df["stock_id"] == "1701") & (df["date"] == "2024-06-30") & (df["dataset"] == IS) & (df["type"] == NI)]
    assert len(r) == 1
    if r["src"].iloc[0] != "資料不足":
        assert abs(r["value"].iloc[0] - 80_253_000) <= 1_000


def test_backfill_scope(df):
    """補值只發生在原本被綜合損益佔用的股季。"""
    s = df[df["dataset"] == IS]
    ci = s[s["type"] == "ComprehensiveIncomeAttributableToOwnersOfParent"]
    ci_k = set(zip(ci["stock_id"], ci["date"]))
    b = s[(s["src"] != "FinMind") & (s["type"] == NI)]
    assert set(zip(b["stock_id"], b["date"])) <= ci_k
