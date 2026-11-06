"""第二期資料層（候選）：日期一致、處置起迄、註記代碼覆蓋。需 P2_OUT 指向 build_phase2 輸出。"""
import os

import pandas as pd
import pytest

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
def test_downtick_list_keys():
    d = pd.read_parquet(os.path.join(OUT, "downtick_list.parquet"))
    assert not d.duplicated(["date", "market", "code"]).any()
    assert d["date"].isin(_cal()).all()
    assert d["date"].min() >= pd.Timestamp("2013-09-18")


@need
def test_fulldelivery_keys():
    p = os.path.join(OUT, "fulldelivery.parquet")
    d = pd.read_parquet(p)
    if not len(d):
        pytest.skip("尚未下載")
    assert not d.duplicated(["date", "code"]).any()
    assert d["date"].isin(_cal()).all() and d["date"].min() >= pd.Timestamp("2004-12-24")
