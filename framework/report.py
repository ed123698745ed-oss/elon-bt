"""報告數字表格一律由程式從明細產生（C9、D2、E4），不手打。"""
from framework import elon_tools, stats


def result_table(trades, by=("combo",), cluster_unit=None):
    """回傳 (未四捨五入原表, 報告用 markdown)。原表另存全精度 CSV 交件。"""
    raw = stats.ten_table(trades, by=by, cluster_unit=cluster_unit)
    return raw, elon_tools.to_markdown(raw)


# ── 報告首頁：資料層標籤由程式寫入（執行計畫修訂版55：多空配置類策略報告第一頁寫明資料層標籤） ──
import json as _json
import os as _os

from framework import data as _data

TAG_LINE = "資料層標籤："
WARN_LINE = "⚠ 本報告使用未經 Eve 驗收的共用資料"


def front_page(title, case_id, version, revision, extra_lines=()):
    """報告第一頁。資料層標籤取自本次實際 load() 紀錄；未用任何共用資料時拒絕產生（避免漏標）。"""
    if not _data.used():
        raise RuntimeError("本次沒有經 framework.data.load() 載入任何共用資料，無法寫資料層標籤；請改用 load() 取資料")
    lines = [f"# {title}", "", f"案件：{case_id}｜{version}｜{revision}"]
    if _data.has_unaccepted():
        lines += ["", f"**{WARN_LINE}，結果只供參考，不得作正式結論或送審依據。**"]
    lines += ["", TAG_LINE + _data.data_tags_used()]
    lines += list(extra_lines)
    return "\n".join(lines) + "\n"


def write_report(path, title, case_id, version, revision, body, extra_lines=()):
    """寫出報告：首頁（含資料層標籤）＋內文，另存 <報告>.data_tags.json 供 Eve 核對。
    首頁在寫檔當下才產生，所以內文計算途中追加 load() 的表也會列入。"""
    text = front_page(title, case_id, version, revision, extra_lines) + "\n" + body
    _os.makedirs(_os.path.dirname(_os.path.abspath(path)), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)
    _json.dump({"report": _os.path.basename(path), "data_tags": _data.used(), "has_unaccepted": _data.has_unaccepted()},
               open(path + ".data_tags.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return path


def check_report(path):
    """自檢：首頁第一段必須有資料層標籤行，且與附檔 data_tags.json 一致；用了未驗收資料必須有警示行。"""
    text = open(path, encoding="utf-8").read()
    head = text.split("\n## ")[0]
    side = _json.load(open(path + ".data_tags.json", encoding="utf-8"))
    errs = []
    if TAG_LINE not in head:
        errs.append("首頁缺資料層標籤行")
    for tag in side["data_tags"]:
        if tag not in head:
            errs.append(f"首頁缺標籤 {tag}")
    if side["has_unaccepted"] and WARN_LINE not in head:
        errs.append("用了未驗收資料但首頁沒有警示")
    if not side["has_unaccepted"] and WARN_LINE in head:
        errs.append("全為已驗收資料卻有警示")
    return errs
