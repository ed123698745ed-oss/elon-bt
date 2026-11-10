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
    after = open(os.path.join(ROOT, "CATALOG.md"), encoding="utf-8").read()
    cut = lambda t: t.split("## 五、未登記標籤")[0]          # 第五節依 GitHub 即時查詢，離線時會不同
    assert cut(after) == cut(before), "CATALOG.md 與登記簿不一致，請重產"


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


@pytest.mark.parametrize("bad", [None, "", "abc", "C65E57653FCDC922EBB4559C936ECF2464620C8E3BF7F38F0CBA191150249F21", "g" * 64])
def test_missing_or_malformed_hash_rejected(bad, tmp_path, monkeypatch):
    """清冊雜湊缺失／空值／格式錯誤時，path() 必須拒絕，即使本機檔存在。"""
    f = tmp_path / "status.parquet"
    f.write_bytes(b"x")
    monkeypatch.setenv("ELON_DATA_LOCAL_PHASE1", str(tmp_path))
    real = data._snapshot

    def fake(tag):
        s = real(tag)
        s["tables"]["status"] = dict(s["tables"]["status"], sha256=bad)
        if bad is None:
            s["tables"]["status"].pop("sha256")
        return s
    monkeypatch.setattr(data, "_snapshot", fake)
    data._USED.clear()
    with pytest.raises(RuntimeError, match="缺失或格式錯誤"):
        data.path("status")
    assert data._USED == {}


def test_all_registered_snapshots_have_valid_hashes():
    import re
    for f in os.listdir(os.path.join(CAT, "schemas")):
        s = yaml.safe_load(open(os.path.join(CAT, "schemas", f), encoding="utf-8"))
        for n, t in s["tables"].items():
            assert re.fullmatch(r"[0-9a-f]{64}", t.get("sha256") or ""), (f, n)


def test_candidate_is_marked(monkeypatch):
    data._USED.clear()
    monkeypatch.setattr(data, "_sha", lambda p: None)
    tag, st = data.resolve("surveillance", allow_candidate=True)
    data._USED[tag] = {"status": st, "tables": {"surveillance"}}
    assert "【未驗收" in data.data_tags_used()
