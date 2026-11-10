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
    """自檢：首頁標籤行必須與附檔 data_tags.json 逐字一致（標籤、驗收狀態、表名都比對），
    附檔中的驗收狀態須與登記簿現況一致，用了未驗收資料必須有警示行。"""
    text = open(path, encoding="utf-8").read()
    head = text.split("\n## ")[0]
    side = _json.load(open(path + ".data_tags.json", encoding="utf-8"))
    errs = []
    lines = [l for l in head.splitlines() if l.startswith(TAG_LINE)]
    expect = TAG_LINE + _data.format_tags(side["data_tags"])
    if len(lines) != 1:
        errs.append(f"首頁資料層標籤行應恰有 1 行，實有 {len(lines)} 行")
    elif lines[0] != expect:
        got = _parse_tag_line(lines[0])
        for tag, u in side["data_tags"].items():
            g = got.get(tag)
            if g is None:
                errs.append(f"首頁缺標籤 {tag}")
                continue
            if g["status"] != u["status"]:
                errs.append(f"{tag} 驗收狀態不符：首頁「{g['status']}」、附檔「{u['status']}」")
            if g["tables"] != sorted(u["tables"]):
                errs.append(f"{tag} 表名不符：首頁 {g['tables']}、附檔 {sorted(u['tables'])}")
        for tag in set(got) - set(side["data_tags"]):
            errs.append(f"首頁多出附檔沒有的標籤 {tag}")
        if not errs:
            errs.append("首頁標籤行與附檔格式不一致")
    reg = {t["tag"]: t["status"] for v in _data._reg()["groups"].values() for t in v["tags"]}
    for tag, u in side["data_tags"].items():
        if reg.get(tag) != u["status"]:
            errs.append(f"{tag} 附檔狀態「{u['status']}」與登記簿「{reg.get(tag)}」不符")
    unacc = any(u["status"] != "已驗收" for u in side["data_tags"].values())
    if bool(side.get("has_unaccepted")) != unacc:
        errs.append("附檔 has_unaccepted 與各標籤狀態不一致")
    if unacc and WARN_LINE not in head:
        errs.append("用了未驗收資料但首頁沒有警示")
    if not unacc and WARN_LINE in head:
        errs.append("全為已驗收資料卻有警示")
    return errs


def _parse_tag_line(line):
    import re
    out = {}
    for part in line[len(TAG_LINE):].split("；"):
        m = re.match(r"(?P<tag>[^（]+)（(?P<st>[^）]+)）(?:【[^】]*】)?：(?P<tb>.*)", part)
        if m:
            out[m["tag"]] = {"status": m["st"], "tables": sorted(x for x in m["tb"].split("、") if x)}
    return out
