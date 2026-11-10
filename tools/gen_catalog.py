"""產生 CATALOG.md（資料清單）。用法：python tools/gen_catalog.py
- 標籤與驗收狀態：data_catalog/registry.yml（人工，依 Eve 結果）
- 各表說明：data_catalog/tables.yml（人工）
- 欄位、筆數、期間：讀 Release 上 parquet 檔尾（自動）；結果快取在 data_catalog/schemas/<tag>.json（標籤不覆蓋，故快取永久有效）
"""
import json, os, sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from data_catalog import remote  # noqa: E402

CAT = os.path.join(ROOT, "data_catalog")
STATUS_ICON = {"已驗收": "✅", "待驗收": "🟡", "待複審": "🟡", "未送驗收": "⚪", "已被取代": "⛔"}


def load_yaml(n):
    return yaml.safe_load(open(os.path.join(CAT, n), encoding="utf-8"))


def snapshot(tag):
    p = os.path.join(CAT, "schemas", f"{tag}.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    mname, man = remote.manifest(tag)
    files = man.get("files", {})
    tables = {}
    for fn in files:
        if fn.endswith(".parquet"):
            tables[fn[:-8]] = remote.parquet_info(tag, fn)
            tables[fn[:-8]]["sha256"] = files[fn].get("sha256")
    snap = {"tag": tag, "manifest": mname, "code_commit": man.get("code_commit"),
            "tests_exit_code": man.get("tests_exit_code"), "source_asof": man.get("source_asof"), "tables": tables}
    json.dump(snap, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return snap


def current_tags(reg):
    """每組：推薦標籤（最後一個已驗收）與最新候選（最後一個非已被取代且非已驗收者，若比已驗收更新）。"""
    out = {}
    for g, v in reg["groups"].items():
        tags = v["tags"]
        acc = [t for t in tags if t["status"] == "已驗收"]
        cand = [t for t in tags if t["status"] not in ("已驗收", "已被取代")]
        out[g] = (acc[-1] if acc else None, cand[-1] if cand else None)
    return out


def period(info):
    for c in ("date", "data_date", "announce", "ex_date", "start"):
        if c in info["ranges"]:
            a, b = info["ranges"][c]
            return f"{a}～{b}"
    return ""


def main():
    reg, tbl = load_yaml("registry.yml"), load_yaml("tables.yml")
    cur = current_tags(reg)
    snaps = {t["tag"]: snapshot(t["tag"]) for v in reg["groups"].values() for t in v["tags"] if t["status"] != "已被取代"}
    L = ["# 共用資料清單（自動產生，勿手改）", "",
         "由 `tools/gen_catalog.py` 依 `data_catalog/registry.yml`（標籤與驗收狀態）、`data_catalog/tables.yml`（表說明）與 Release 上的 parquet 檔產生。", "",
         "**取資料一律用** `from framework.data import load` → `load(\"表名\")`：預設只給已驗收標籤；要用未驗收版本須寫 `allow_candidate=True`，報告第一頁的資料標籤以 `data_tags_used()` 填寫。", "",
         "圖例：✅ 已驗收　🟡 待驗收／待複審　⚪ 未送驗收　⛔ 已被取代", "",
         "## 一、各組目前可用標籤", "",
         "| 組 | 內容 | 預設（已驗收） | 最新未驗收版本 |", "|---|---|---|---|"]
    for g, v in reg["groups"].items():
        a, c = cur[g]
        L.append(f"| {g} | {v['title']} | {('✅ ' + a['tag']) if a else '無（load 會拒絕，需 allow_candidate）'} | "
                 f"{(STATUS_ICON[c['status']] + ' ' + c['tag'] + '（' + c['status'] + '）') if c else '—'} |")
    L += ["", "## 二、資料表一覽", "",
          "筆數與期間取自 load() 預設會給的標籤；該組沒有已驗收標籤時，取最新未驗收版本（標 🟡／⚪）。", "",
          "| 表 | 內容 | 用途 | 組 | 筆數 | 期間 | 可得時點 |", "|---|---|---|---|---|---|---|"]
    detail = []
    for name, d in tbl.items():
        a, c = cur[d["group"]]
        use_t = a or c
        info = snaps.get(use_t["tag"], {}).get("tables", {}).get(name) if use_t else None
        icon = STATUS_ICON[use_t["status"]] if use_t else ""
        L.append(f"| `{name}` | {d['title']} | {d['use']} | {d['group']} {icon} | "
                 f"{info['rows']:,} | {period(info)} | {d['timing']} |" if info else
                 f"| `{name}` | {d['title']} | {d['use']} | {d['group']} | — | — | {d['timing']} |")
        detail += [f"### `{name}`｜{d['title']}", "",
                   f"- 用途：{d['use']}", f"- 主鍵：{d['key']}", f"- 可得時點：{d['timing']}", f"- 注意：{d['caveats']}"]
        for t in (a, c):
            if t and name in snaps.get(t["tag"], {}).get("tables", {}):
                i = snaps[t["tag"]]["tables"][name]
                detail.append(f"- {STATUS_ICON[t['status']]} {t['tag']}：{i['rows']:,} 列；期間 {period(i) or '—'}")
        if info:
            detail.append("- 欄位：" + "、".join(f"`{x['name']}`" for x in info["columns"]))
        detail.append("")
    L += ["", "## 三、各表說明", ""] + detail
    L += ["## 四、全部標籤", "", "| 組 | 標籤 | 狀態 | 說明 | 程式 commit | 測試 |", "|---|---|---|---|---|---|"]
    for g, v in reg["groups"].items():
        for t in v["tags"]:
            s = snaps.get(t["tag"], {})
            tr = s.get("tests_exit_code")
            L.append(f"| {g} | {t['tag']} | {STATUS_ICON[t['status']]} {t['status']} | {t['note']} | "
                     f"{(s.get('code_commit') or '')[:7]} | {t.get('tests') or ('' if tr is None else ('通過' if tr == 0 else '未過'))} |")
    L += ["", "原始檔倉庫（建置用，不供回測直接讀取）：", ""] + [f"- `{r['tag']}`：{r['note']}" for r in reg["raw"]]
    asof = {t: s.get("source_asof") for t, s in snaps.items() if s.get("source_asof")}
    if asof:
        L += ["", "資料截至日（各來源最後完整檢查日；open_periods 為當時尚未結束、之後會更新的期間）：", ""]
        for t, a in asof.items():
            L.append(f"- {t}：" + "；".join(f"{k} {v[0]}{('（' + v[1] + '）') if len(v) > 1 and v[1] != 'open_periods=' else ''}" for k, v in a.items()))
    known = {t["tag"] for v in reg["groups"].values() for t in v["tags"]} | {r["tag"] for r in reg["raw"]}
    live = remote.release_tags()
    L += ["", "## 五、未登記標籤（load() 不會使用，須先登記並送驗收）", ""]
    if live is None:
        L.append("（本次無法查詢 GitHub Release 清單）")
    else:
        extra = sorted(set(live) - known)
        L += [f"- ⚠ `{t}`" for t in extra] or ["（無）"]
    open(os.path.join(ROOT, "CATALOG.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("CATALOG.md", len(L), "lines")


if __name__ == "__main__":
    main()
