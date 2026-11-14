"""報告首頁資料層標籤：由 write_report 自動寫入、check_report 能抓出漏標與漏警示。"""
# 註：測試用的未驗收標籤取 data-tdcc-20261111（登記簿狀態「未送驗收」）；若其狀態改變，需改用另一個未驗收標籤。
import os, sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework import data, report  # noqa: E402


def _use(tags):
    data._USED.clear()
    for t, st, tb in tags:
        data._USED[t] = {"status": st, "tables": set(tb)}


def test_refuses_without_shared_data(tmp_path):
    data._USED.clear()
    with pytest.raises(RuntimeError, match="load"):
        report.write_report(str(tmp_path / "r.md"), "t", "c", "V1", "R1", "## 內文\n")


def test_accepted_only_no_warning(tmp_path):
    _use([("data-20261105r68", "已驗收", ["daily_k"])])
    p = report.write_report(str(tmp_path / "r.md"), "t", "c", "V1", "R1", "## 內文\n")
    head = open(p, encoding="utf-8").read().split("\n## ")[0]
    assert "資料層標籤：data-20261105r68（已驗收）" in head and report.WARN_LINE not in head
    assert report.check_report(p) == []


def test_candidate_warning_and_tampering_detected(tmp_path):
    _use([("data-20261105r68", "已驗收", ["daily_k"]), ("data-tdcc-20261111", "未送驗收", ["surveillance"])])
    p = report.write_report(str(tmp_path / "r.md"), "t", "c", "V1", "R1", "## 內文\n")
    head = open(p, encoding="utf-8").read().split("\n## ")[0]
    assert report.WARN_LINE in head and "data-tdcc-20261111（未送驗收）【未驗收" in head
    assert report.check_report(p) == []
    t = open(p, encoding="utf-8").read().replace(report.WARN_LINE, "")       # 有人刪掉警示
    open(p, "w", encoding="utf-8").write(t)
    assert "用了未驗收資料但首頁沒有警示" in report.check_report(p)
    open(p, "w", encoding="utf-8").write(t.replace("data-tdcc-20261111", "X"))
    assert any("缺標籤" in e for e in report.check_report(p))


def _cand_report(tmp_path):
    _use([("data-20261105r68", "已驗收", ["status"]), ("data-tdcc-20261111", "未送驗收", ["surveillance"])])
    return report.write_report(str(tmp_path / "r.md"), "t", "c", "V1", "R1", "## 內文\n")


def test_eve_case_status_and_table_tampered_but_warning_kept(tmp_path):
    """Eve 複審案例：保留警示與原附檔，首頁 c2 改成已驗收、surveillance 改成 calendar，自檢必須抓到。"""
    p = _cand_report(tmp_path)
    t = open(p, encoding="utf-8").read()
    t2 = t.replace("data-tdcc-20261111（未送驗收）【未驗收：未送驗收，結果不得作正式結論】：surveillance",
                   "data-tdcc-20261111（已驗收）：calendar")
    assert t2 != t and report.WARN_LINE in t2
    open(p, "w", encoding="utf-8").write(t2)
    errs = report.check_report(p)
    assert any("驗收狀態不符" in e for e in errs) and any("表名不符" in e for e in errs), errs


@pytest.mark.parametrize("old,new,msg", [
    ("：surveillance", "：calendar", "表名不符"),
    ("：status", "：status、daily_k", "表名不符"),
    ("data-20261105r68（已驗收）", "data-20261105r68（待複審）", "驗收狀態不符"),
    ("；data-tdcc-20261111（未送驗收）【未驗收：未送驗收，結果不得作正式結論】：surveillance", "", "首頁缺標籤"),
])
def test_each_field_compared(tmp_path, old, new, msg):
    p = _cand_report(tmp_path)
    t = open(p, encoding="utf-8").read()
    assert old in t
    open(p, "w", encoding="utf-8").write(t.replace(old, new, 1))
    assert any(msg in e for e in report.check_report(p))


def test_sidecar_status_must_match_registry(tmp_path):
    import json
    p = _cand_report(tmp_path)
    side = json.load(open(p + ".data_tags.json", encoding="utf-8"))
    side["data_tags"]["data-tdcc-20261111"]["status"] = "已驗收"       # 連附檔一起改
    side["has_unaccepted"] = False
    json.dump(side, open(p + ".data_tags.json", "w", encoding="utf-8"), ensure_ascii=False)
    t = open(p, encoding="utf-8").read().replace("data-tdcc-20261111（未送驗收）【未驗收：未送驗收，結果不得作正式結論】", "data-tdcc-20261111（已驗收）")
    open(p, "w", encoding="utf-8").write(t)
    assert any("與登記簿" in e for e in report.check_report(p))
