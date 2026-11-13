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
import json, os, re, unicodedata

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


def after(body, label):
    """回傳科目名稱之後的文字（名稱字間可能有空白）。"""
    pat = r"\s*".join(map(re.escape, label))
    parts = re.split(pat, body, maxsplit=1)
    return parts[1] if len(parts) == 2 else ""


def strip_code(line):
    return re.sub(r"^\s*\d{4}\s+", "", line)


def block(text):
    """回傳 {'NI': [...], 'NCI': [...], 'FORM': [...], 'TOT': [...]}；找不到回傳 None。"""
    text = unicodedata.normalize("NFKC", text)   # PDF 常用相容表意字（如「權」「利」的變體），先正規化
    text = re.sub(r"(\d)\s*,\s+(?=\d{3}(\D|$))", r"\1,", text)   # OCR 常把千分位逗號前後多加空白（10, 819／363 , 847）
    text = re.sub(r"(\d)\s+,(?=\d{3}(\D|$))", r"\1,", text)
    L = [x.strip() for x in text.splitlines()]
    def is_start(x):
        y = re.sub(r"\s", "", x)
        k = y.find("歸屬於")
        if re.match(r"^8600\D", y):   # IFRS 科目代碼：8600 淨利歸屬於（OCR 文字常把中文辨識錯，代碼較穩）
            return True
        return k > 0 and re.search(r"(淨利|淨損|損益|純益)", y[:k]) and "綜合" not in y[:k] and "權益" not in y[:k]
    starts = [i for i, x in enumerate(L) if is_start(x)]
    # OCR 把「8600 淨利歸屬於」辨識成亂碼時，以 8610 列的前一列當起點
    starts += [i - 1 for i, x in enumerate(L) if re.match(r"^8610\D", re.sub(r"\s", "", x)) and i - 1 not in starts and i > 0]
    for st in starts:
        r = {}
        for x in L[st + 1: st + 12]:
            y = re.sub(r"\s", "", x)
            if "綜合損益" in y and "歸屬" in y:
                break
            body = strip_code(x)
            if re.match(r"^87\d\d", y):
                break
            if re.match(r"^8610\D", y):
                r["NI"] = nums(re.sub(r"^[^\d(\$-]*", "", body))
            elif re.match(r"^8620\D", y):
                r["NCI"] = nums(re.sub(r"^[^\d(\$-]*", "", body))
            elif "母公司業主" in y:
                r["NI"] = nums(after(body, "業主"))
            elif "非控制權益" in y:
                r["NCI"] = nums(after(body, "權益"))
            elif "共同控制下前手" in y:
                r["FORM"] = nums(after(body, "權益"))
            elif "NI" in r and (re.match(r"^\(?\$", body) or re.match(r"^(本期淨利|本期淨損|本期損益|合計|淨利)", y)) and nums(body):
                r["TOT"] = nums(body)
                break
        if r.get("NI"):
            return r
    return None


def unit(text):
    t = re.sub(r"\s", "", unicodedata.normalize("NFKC", text))
    if re.search(r"單位[：:]?(新臺幣|新台幣)?(仟|千)元", t):
        return 1000.0
    if re.search(r"單位[：:]?(新臺幣|新台幣)?元", t):
        return 1.0
    return None


def read_report(rec):
    """回傳 {'NI': [...], 'NCI': [...], 'FORM': [...], 'TOT': [...]}（元）。PDF 文字的欄位順序不可靠，
    所以只保留數列，配對交給 match()：用 FinMind 本期淨利找合計，再找「歸母＋非控制＋前手＝合計」的唯一組合。"""
    b = block(rec["text"]); u = unit(rec["text"])
    if b is None:
        return None
    if u is None and not rec.get("ocr"):
        return None
    # OCR 頁常讀不出「單位：千元」：兩種單位都列為候選，由 FinMind 本期淨利核對決定（只有一種會對得上）
    units = [u] if u is not None else [1000.0, 1.0]
    return [{k: [x * uu for x in v] for k, v in b.items()} for uu in units]


def match(r, target, tol_tot=1000.0, tol_sum=1500.0):
    """target：FinMind 本期淨利（元）。回傳唯一的 {'NI','NCI','FORM','TOT'} 或 (None, 原因)。"""
    # 沒有合計列的版式：直接以 FinMind 本期淨利當合計
    tots = [t for t in r["TOT"] if abs(t - target) <= tol_tot] if r.get("TOT") else [target]
    sols = set()
    for t in set(tots):
        for a in r["NI"]:
            for b in (r.get("NCI") or [0.0]):
                for c in (r.get("FORM") or [0.0]):
                    if abs(a + b + c - t) <= (tol_sum if r.get("TOT") else tol_tot + 500):
                        sols.add((a, b, c, t))
    if len(sols) == 1:
        a, b, c, t = sols.pop()
        return {"NI": a, "NCI": b, "FORM": c, "TOT": t}, None
    return None, ("找不到合計等於 FinMind 本期淨利" if not tots else ("恆等式無解" if not sols else f"多組解 {len(sols)}"))


def main():
    pages = [json.loads(l) for l in open(os.environ.get("PAGES", "raw_ebook/pages.jsonl"))]
    rep = {}
    for p in pages:
        r = read_report(p)
        if r:
            for c in r:
                rep.setdefault(p["key"], []).append({**c, "file": p["file"], "page": p["page"]})
    f = pd.read_parquet(os.environ["SRC"], columns=["stock_id", "date", "dataset", "type", "value"])
    s = f[(f["dataset"] == IS) & f["type"].isin(["IncomeAfterTaxes", "IncomeAfterTax"])]
    iat = s.sort_values("type", ascending=False).drop_duplicates(["stock_id", "date"]).set_index(["stock_id", "date"])["value"]
    tg = pd.read_csv(os.environ.get("TARGETS", "ebook_targets.csv"), dtype=str)[["stock_id", "date"]].drop_duplicates()

    def solve(key, target):
        why = "無報告或找不到損益表淨利歸屬區塊"
        for r in rep.get(key, []):
            m, w = match(r, target)
            if m:
                return {**m, "file": r["file"], "page": r["page"]}, None
            why = w
        return None, why

    rows, bad = [], []
    for sid, d in tg.itertuples(index=False):
        y, mo = int(d[:4]), int(d[5:7])
        q = {3: 1, 6: 2, 9: 3, 12: 4}[mo]
        qd = lambda k: f"{y}-{[None, '03-31', '06-30', '09-30', '12-31'][k]}"
        singles = [iat.get((sid, qd(k))) for k in range(1, q + 1)]
        if q < 4:
            ref = singles[-1]
            if ref is None or pd.isna(ref):
                bad.append((sid, d, "FinMind 無本期淨利可核對")); continue
            m, why = solve(f"{sid}_{y - 1911}_{q}", ref)
            if m is None:
                bad.append((sid, d, why)); continue
            val = m; src = m["file"], m["page"]
        else:
            if any(v is None or pd.isna(v) for v in singles):
                bad.append((sid, d, "FinMind 四季本期淨利不全，無法核對年報與第三季累計")); continue
            ma, w1 = solve(f"{sid}_{y - 1911}_4", sum(singles))
            m3, w3 = solve(f"{sid}_{y - 1911}_3", sum(singles[:3]))
            if ma is None or m3 is None:
                bad.append((sid, d, f"年報：{w1 or '可'}；第三季累計：{w3 or '可'}")); continue
            val = {k: ma[k] - m3[k] for k in ("NI", "NCI", "FORM", "TOT")}
            src = f"{ma['file']}−{m3['file']}", f"{ma['page']}／{m3['page']}"
        rows.append((sid, d, "EquityAttributableToOwnersOfParent", val["NI"], src[0], src[1]))
        rows.append((sid, d, "NoncontrollingInterests", val["NCI"], src[0], src[1]))
    out = os.environ.get("OUT", "data_seed"); os.makedirs(out, exist_ok=True)
    pd.DataFrame(rows, columns=["stock_id", "date", "type", "value", "file", "page"]).to_csv(os.path.join(out, "fin_ebook.csv"), index=False)
    pd.DataFrame(bad, columns=["stock_id", "date", "reason"]).to_csv(os.path.join(out, "ebook_unresolved.csv"), index=False)
    print(f"有淨利歸屬區塊的報告 {len(rep)}／{len({p['key'] for p in pages})}；回補股季 {len(rows) // 2}；未解決 {len(bad)}")


if __name__ == "__main__":
    main()
