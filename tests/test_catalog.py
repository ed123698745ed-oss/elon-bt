"""資料清單與取資料入口：登記簿、說明、快取三者一致；未驗收／已被取代的標籤擋得住。"""
import os, sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from framework import data  # noqa: E402

CAT = os.path.join(ROOT, "data_catalog")
STATUSES = {"已驗收", "待驗收", "待複審", "未送驗收", "已被取代"}


def _y(n):
    return yaml.safe_load(open(os.path.join(CAT, n), encoding="utf-8"))


def test_registry_statuses_and_tables_documented():
    reg, tbl = _y("registry.yml"), _y("tables.yml")
    seen = set()
    for g, v in reg["groups"].items():
        for t in v["tags"]:
            assert t["status"] in STATUSES, t
            assert t["tag"] not in seen
            seen.add(t["tag"])
            if t["status"] == "已被取代":
                continue
            snap = os.path.join(CAT, "schemas", f"{t['tag']}.json")
            assert os.path.exists(snap), f"缺快取 {snap}（執行 tools/gen_catalog.py）"
            names = set(yaml.safe_load(open(snap, encoding="utf-8"))["tables"])
            documented = {n for n, d in tbl.items() if d["group"] == g}
            assert names <= documented, f"{t['tag']} 有未寫說明的表：{names - documented}"
    for n, d in tbl.items():
        assert d["group"] in reg["groups"]
        for k in ("title", "use", "key", "timing", "caveats"):
            assert d.get(k), (n, k)


def test_catalog_md_is_current():
    import subprocess
    before = open(os.path.join(ROOT, "CATALOG.md"), encoding="utf-8").read()
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gen_catalog.py")], check=True, capture_output=True)
    assert open(os.path.join(ROOT, "CATALOG.md"), encoding="utf-8").read() == before, "CATALOG.md 與登記簿不一致，請重產"


def test_resolve_defaults_to_accepted_and_blocks_others():
    reg = _y("registry.yml")
    for g, v in reg["groups"].items():
        acc = [t["tag"] for t in v["tags"] if t["status"] == "已驗收"]
        table = next(n for n, d in _y("tables.yml").items() if d["group"] == g)
        if acc:
            assert data.resolve(table) == (acc[-1], "已驗收")
        else:
            with pytest.raises(data.DataNotAccepted):
                data.resolve(table)
            tag, st = data.resolve(table, allow_candidate=True)
            assert st != "已驗收"
        for t in v["tags"]:
            if t["status"] == "已被取代":
                with pytest.raises(data.DataNotAccepted):
                    data.resolve(table, allow_candidate=True, tag=t["tag"])
            elif t["status"] != "已驗收":
                with pytest.raises(data.DataNotAccepted):
                    data.resolve(table, tag=t["tag"])
    with pytest.raises(KeyError):
        data.resolve("no_such_table")


def test_load_downloads_checks_sha_and_records_tags(tmp_path, monkeypatch):
    monkeypatch.setenv("ELON_DATA", str(tmp_path))
    monkeypatch.delenv("ELON_DATA_LOCAL_PHASE1", raising=False)
    data._USED.clear()
    try:
        df = data.load("status")
    except OSError as e:
        pytest.skip(f"無法連線 Release：{e}")
    assert len(df) > 0
    used = data.data_tags_used()
    assert used.startswith("data-20261105r68（已驗收）") and "未驗收" not in used


def test_wrong_file_rejected(tmp_path, monkeypatch):
    bad = tmp_path / "status.parquet"
    import pandas as pd
    pd.DataFrame({"stock_id": ["2330"]}).to_parquet(bad)
    monkeypatch.setenv("ELON_DATA_LOCAL_PHASE1", str(tmp_path))
    with pytest.raises(RuntimeError, match="sha256"):
        data.load("status")


def test_candidate_is_marked(monkeypatch):
    data._USED.clear()
    monkeypatch.setattr(data, "_sha", lambda p: None)
    tag, st = data.resolve("surveillance", allow_candidate=True)
    data._USED[tag] = {"status": st, "tables": {"surveillance"}}
    assert "【未驗收" in data.data_tags_used()
