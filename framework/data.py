"""取資料的唯一入口。

    from framework.data import load, data_tags_used
    k = load("daily_k")                                   # 只給已驗收標籤
    sv = load("surveillance", allow_candidate=True)       # 未驗收版本須明寫，報告會標出
    print(data_tags_used())                               # 報告第一頁的資料標籤

規則：
- 標籤與驗收狀態以 data_catalog/registry.yml 為準（依 Eve 結果填寫）；預設取該組最後一個「已驗收」標籤。
- 該組沒有已驗收標籤時 load() 拒絕，除非 allow_candidate=True；指定 tag= 時，已被取代的標籤一律拒絕。
- 下載後核對 sha256（清冊值），清冊缺雜湊、格式錯誤或不符一律拒絕；本機快取在 $ELON_DATA（預設 ~/.elon_data/<tag>/）。
- 已下載的本機資料夾可用 $ELON_DATA_LOCAL_<組>（例：ELON_DATA_LOCAL_PHASE1=/path/out_r68）指定，仍核對 sha256。
"""
import hashlib, json, os, re, sys

import pandas as pd
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from data_catalog import remote  # noqa: E402

CAT = os.path.join(ROOT, "data_catalog")
_USED = {}          # tag -> {"status":..., "tables": set()}


class DataNotAccepted(RuntimeError):
    pass


def _reg():
    return yaml.safe_load(open(os.path.join(CAT, "registry.yml"), encoding="utf-8"))


def _tables():
    return yaml.safe_load(open(os.path.join(CAT, "tables.yml"), encoding="utf-8"))


def resolve(table, allow_candidate=False, tag=None):
    """回傳 (tag, status)。"""
    t = _tables().get(table)
    if t is None:
        raise KeyError(f"清單沒有表「{table}」；可用：{', '.join(_tables())}（見 CATALOG.md）")
    tags = _reg()["groups"][t["group"]]["tags"]
    if tag:
        hit = [x for x in tags if x["tag"] == tag]
        if not hit:
            raise KeyError(f"{tag} 不在 {t['group']} 組")
        if hit[0]["status"] == "已被取代":
            raise DataNotAccepted(f"{tag} 已被取代，不得使用")
        if hit[0]["status"] != "已驗收" and not allow_candidate:
            raise DataNotAccepted(f"{tag} 狀態為「{hit[0]['status']}」，要用須 allow_candidate=True")
        return tag, hit[0]["status"]
    acc = [x for x in tags if x["status"] == "已驗收"]
    if acc and not allow_candidate:
        return acc[-1]["tag"], "已驗收"
    cand = [x for x in tags if x["status"] not in ("已被取代",)]
    if allow_candidate and cand:
        return cand[-1]["tag"], cand[-1]["status"]
    raise DataNotAccepted(f"{table}（{t['group']} 組）目前沒有已驗收標籤；最新為 "
                          f"{cand[-1]['tag'] + '（' + cand[-1]['status'] + '）' if cand else '無'}，要用須 allow_candidate=True")


def _snapshot(tag):
    p = os.path.join(CAT, "schemas", f"{tag}.json")
    if not os.path.exists(p):
        raise FileNotFoundError(f"缺 {p}；先執行 python tools/gen_catalog.py")
    return json.load(open(p, encoding="utf-8"))


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def path(table, allow_candidate=False, tag=None):
    tag, status = resolve(table, allow_candidate, tag)
    want = _snapshot(tag)["tables"][table].get("sha256")
    if not isinstance(want, str) or not re.fullmatch(r"[0-9a-f]{64}", want):
        raise RuntimeError(f"{tag} 清冊中 {table} 的 sha256 缺失或格式錯誤（{want!r}），不載入")
    group = _tables()[table]["group"].upper()
    local = os.environ.get(f"ELON_DATA_LOCAL_{group}")
    p = os.path.join(local, f"{table}.parquet") if local else \
        os.path.join(os.environ.get("ELON_DATA", os.path.expanduser("~/.elon_data")), tag, f"{table}.parquet")
    if not os.path.exists(p):
        if local:
            raise FileNotFoundError(p)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        remote.download(tag, f"{table}.parquet", p + ".part")
        os.replace(p + ".part", p)
    if _sha(p) != want:
        raise RuntimeError(f"{p} 的 sha256 與 {tag} 清冊不符，不使用")
    u = _USED.setdefault(tag, {"status": status, "tables": set()})
    u["tables"].add(table)
    return p


def load(table, allow_candidate=False, tag=None, columns=None, **kw) -> pd.DataFrame:
    return pd.read_parquet(path(table, allow_candidate, tag), columns=columns, **kw)


def used() -> dict:
    """本次載入紀錄（tag -> {status, tables}），供報告首頁與附檔使用。"""
    return {t: {"status": u["status"], "tables": sorted(u["tables"])} for t, u in _USED.items()}


def has_unaccepted() -> bool:
    return any(u["status"] != "已驗收" for u in _USED.values())


def data_tags_used() -> str:
    """報告第一頁用：列出本次用到的標籤、驗收狀態與表；有未驗收者明確標示。"""
    if not _USED:
        return "（尚未載入任何共用資料）"
    out = []
    for tag, u in _USED.items():
        mark = "" if u["status"] == "已驗收" else f"【未驗收：{u['status']}，結果不得作正式結論】"
        out.append(f"{tag}（{u['status']}）{mark}：{'、'.join(sorted(u['tables']))}")
    return "；".join(out)


def catalog() -> pd.DataFrame:
    """各表目前預設標籤一覽（與 CATALOG.md 同源）。"""
    rows = []
    for name, d in _tables().items():
        try:
            tag, st = resolve(name)
        except DataNotAccepted:
            tag, st = resolve(name, allow_candidate=True)
        rows.append({"table": name, "title": d["title"], "group": d["group"], "tag": tag, "status": st,
                     "timing": d["timing"], "caveats": d["caveats"]})
    return pd.DataFrame(rows)
