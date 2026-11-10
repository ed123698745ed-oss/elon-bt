"""報告首頁資料層標籤：由 write_report 自動寫入、check_report 能抓出漏標與漏警示。"""
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
    _use([("data-20261105r68", "已驗收", ["daily_k"]), ("data-phase2-20261107c2", "待驗收", ["surveillance"])])
    p = report.write_report(str(tmp_path / "r.md"), "t", "c", "V1", "R1", "## 內文\n")
    head = open(p, encoding="utf-8").read().split("\n## ")[0]
    assert report.WARN_LINE in head and "data-phase2-20261107c2（待驗收）【未驗收" in head
    assert report.check_report(p) == []
    t = open(p, encoding="utf-8").read().replace(report.WARN_LINE, "")       # 有人刪掉警示
    open(p, "w", encoding="utf-8").write(t)
    assert "用了未驗收資料但首頁沒有警示" in report.check_report(p)
    open(p, "w", encoding="utf-8").write(t.replace("data-phase2-20261107c2", "X"))
    assert any("缺標籤" in e for e in report.check_report(p))
