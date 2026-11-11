"""解析財報電子書損益表頁（fetch_fin_ebook.py 的 pages.jsonl），回補歸母淨利、非控制權益淨利（單季，元）。

每份報告找「淨利（損）歸屬於：」到「綜合損益總額歸屬於」之間的列：母公司業主、非控制權益、共同控制下前手權益，
以及沒有科目名稱的合計列（＝本期淨利）。數字依欄序讀取；季報欄位為「本季、去年同季、本年累計、去年累計」，
第一季與年報為「本期、去年同期」。每欄後面可能跟著百分比欄，兩種讀法都試。
只收通過核對的值：
  (a) 母公司業主＋非控制權益＋前手 = 合計（同一欄）；
  (b) 合計（換成元）與 FinMind 同股季單季本期淨利相差 ≤ 1,000 元（四捨五入到仟元）；第四季用年報全年 − 第三季累計。
核對不過、或缺報告者，不輸出（fin_fix 會標資料不足），另列在 ebook_unresolved.csv 供人工檢查。
用法：PAGES=raw_ebook/pages.jsonl SRC=financials.parquet OUT=data_seed python data_layer/parse_fin_ebook.py
"""
import json, os, re

import pandas as pd

IS = "TaiwanStockFinancialStatements"
NUM = re.compile(r"\(\s*\$?\s*([\d,]+(?:\.\d+)?)\s*\)|\$?\s*([\d,]+(?:\.\d+)?)|(-)(?=\s|$)")


def nums(s):
    out = []
    for m in NUM.finditer(s):
        if m.group(3):
            out.append(0.0); continue
        v = m.group(1) or m.group(2)
        if v is None or v == ",":
            continue
        x = float(v.replace(",", ""))
        out.append(-x if m.group(1) else x)
    return out


def strip_code(line):
    return re.sub(r"^\s*\d{4}\s+", "", line)


def block(text):
    """回傳 {'NI': [...], 'NCI': [...], 'FORM': [...], 'TOT': [...]}；找不到回傳 None。"""
    L = [x.strip() for x in text.splitlines()]
    st = next((i for i, x in enumerate(L) if re.search(r"(淨利|損益|純益).{0,6}歸屬於", re.sub(r"\s", "", x))
               and "綜合" not in x), None)
    if st is None:
        return None
    r = {}
    for x in L[st + 1: st + 12]:
        y = re.sub(r"\s", "", x)
        if "綜合損益" in y and "歸屬" in y:
            break
        body = strip_code(x)
        if "母公司業主" in y:
            r["NI"] = nums(body.split("業主", 1)[1])
        elif "非控制權益" in y:
            r["NCI"] = nums(body.split("權益", 1)[1])
        elif "共同控制下前手" in y:
            r["FORM"] = nums(body.split("權益", 1)[1])
        elif re.match(r"^\(?\$", body) and "NI" in r:
            r["TOT"] = nums(body)
            break
    return r if "NI" in r and "TOT" in r else None


def unit(text):
    t = re.sub(r"\s", "", text)
    if re.search(r"單位：?(新臺幣|新台幣)?(仟|千)元", t):
        return 1000.0
    if re.search(r"單位：?(新臺幣|新台幣)?元", t):
        return 1.0
    return None


def columns(v, n_amount_cols, pct):
    """依欄序取金額欄：pct=True 時每個金額後跟一個百分比欄。"""
    step = 2 if pct else 1
    a = v[::step]
    return a[:n_amount_cols] if len(a) >= n_amount_cols else None


def read_report(rec):
    b = block(rec["text"]); u = unit(rec["text"])
    if b is None or u is None:
        return None
    seamon = int(rec["key"].split("_")[2])
    ncol = 4 if seamon in (2, 3) else 2
    outs = []
    for pct in (True, False):
        cols = {k: columns(v, ncol, pct) for k, v in b.items()}
        if any(c is None for c in cols.values()):
            continue
        ok = True
        for j in range(ncol):
            s = cols["NI"][j] + cols.get("NCI", [0] * ncol)[j] + cols.get("FORM", [0] * ncol)[j]
            if abs(s - cols["TOT"][j]) > 1.5:
                ok = False; break
        if ok:
            outs.append({k: [x * u for x in v] for k, v in cols.items()})
    uniq = []
    for o in outs:
        if o not in uniq:
            uniq.append(o)
    return uniq or None   # 多種讀法都通過恆等式時全留，交給 FinMind 本期淨利核對決定


def main():
    pages = [json.loads(l) for l in open(os.environ.get("PAGES", "raw_ebook/pages.jsonl"))]
    rep = {}
    for p in pages:
        if p["key"] in rep:
            continue
        r = read_report(p)
        if r:
            rep[p["key"]] = {"cands": r, "file": p["file"], "page": p["page"]}
    f = pd.read_parquet(os.environ["SRC"], columns=["stock_id", "date", "dataset", "type", "value"])
    s = f[(f["dataset"] == IS) & f["type"].isin(["IncomeAfterTaxes", "IncomeAfterTax"])]
    iat = s.sort_values("type", ascending=False).drop_duplicates(["stock_id", "date"]).set_index(["stock_id", "date"])["value"]
    tg = pd.read_csv(os.environ.get("TARGETS", "ebook_targets.csv"), dtype=str)[["stock_id", "date"]].drop_duplicates()
    rows, bad = [], []
    for sid, d in tg.itertuples(index=False):
        y, m = int(d[:4]) - 1911, int(d[5:7])
        q = {3: 1, 6: 2, 9: 3, 12: 4}[m]
        a = rep.get(f"{sid}_{y}_{q}")
        if a is None:
            bad.append((sid, d, "無報告或無法解析")); continue
        if q < 4:
            cands = [{k: v[0] for k, v in c.items()} for c in a["cands"]]
            src = f"{a['file']}", a["page"]
        else:
            b3 = rep.get(f"{sid}_{y}_3")
            if b3 is None:
                bad.append((sid, d, "缺第三季報告（第四季需年報減第三季累計）")); continue
            cands = [{k: c[k][0] - c3.get(k, [0, 0, 0, 0])[2] for k in ("NI", "NCI", "FORM", "TOT") if k in c}
                     for c in a["cands"] for c3 in b3["cands"]]
            src = f"{a['file']}−{b3['file']}", f"{a['page']}／{b3['page']}"
        ref = iat.get((sid, d))
        okc = [c for c in cands if ref is not None and pd.notna(ref) and abs(c["TOT"] - ref) <= 1000]
        res = {(round(c["NI"]), round(c.get("NCI", 0.0))) for c in okc}
        if len(res) != 1:
            why = "與 FinMind 本期淨利不符" if not okc else "多種讀法結果不一"
            bad.append((sid, d, f"{why}（合計候選 {[round(c['TOT']) for c in cands]}，FinMind {ref}）")); continue
        val = okc[0]
        rows.append((sid, d, "EquityAttributableToOwnersOfParent", val["NI"], src[0], src[1]))
        rows.append((sid, d, "NoncontrollingInterests", val.get("NCI", 0.0), src[0], src[1]))
    out = os.environ.get("OUT", "data_seed"); os.makedirs(out, exist_ok=True)
    pd.DataFrame(rows, columns=["stock_id", "date", "type", "value", "file", "page"]).to_csv(os.path.join(out, "fin_ebook.csv"), index=False)
    pd.DataFrame(bad, columns=["stock_id", "date", "reason"]).to_csv(os.path.join(out, "ebook_unresolved.csv"), index=False)
    print(f"解析報告 {len(rep)}／{len({p['key'] for p in pages})}；回補股季 {len(rows) // 2}；未解決 {len(bad)}")


if __name__ == "__main__":
    main()
