"""064 轉投資價值傳遞策略：年報附表三試抓（D-064-20261109-2350-1「先抓一年看看」；
Ed 2026-11-09 23:59「授權 Elon 寫入 elon-bt，用來跑 064 抓取」）。

在 GitHub Actions 依序執行。每家公司：清單頁(step=1) → 下載連結(step=9) → PDF。
禮貌規則：請求一律依序、間隔 ≥ INTERVAL 秒；一般 urllib 請求，不偽裝瀏覽器、不換 IP、不繞過。
回應為站方安全頁（FOR SECURITY REASONS）即停止本次執行（結束碼 2），下次排程接續；
progress.json 記錄連續被擋次數，達 3 次後不再抓取，等 Ed 決定。
輸出（OUT 目錄）：每家 {sid}_list.html（含上傳日期）、PDF、{sid}.json（狀態、檔名、上傳日期、sha256）、
_attempts.csv（每個請求一列）、附表三文字擷取 holdings_text.jsonl（pypdfium2）。
"""
import csv, hashlib, json, os, re, sys, time, urllib.parse, urllib.request

BASE = "https://doc.twse.com.tw/server-java/t57sb01"
YEAR = os.environ.get("ROC_YEAR", "114")
INTERVAL = float(os.environ.get("INTERVAL", "20"))
BUDGET = float(os.environ.get("BUDGET_MIN", "320")) * 60
OUT = os.environ.get("OUT", "out064")
STATE = os.environ.get("STATE", "state064")
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True); os.makedirs(STATE, exist_ok=True)
PROG = os.path.join(STATE, "progress.json")
prog = json.load(open(PROG)) if os.path.exists(PROG) else {"done": {}, "blocked_runs": 0}
LOG = open(os.path.join(OUT, "_attempts.csv"), "a", newline="")
W = csv.writer(LOG)
T0 = time.time()


def save():
    json.dump(prog, open(PROG, "w"), ensure_ascii=False, indent=0)


def req(url, data=None):
    time.sleep(INTERVAL)
    body = urllib.parse.urlencode(data).encode() if data else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=120) as r:
            b = r.read(); st = r.status
    except Exception as e:  # 網路錯誤：記錄後當作本家失敗，下次再試
        W.writerow([time.strftime("%F %T"), url, json.dumps(data or {}, ensure_ascii=False), "ERR", str(e)[:200]]); LOG.flush()
        return None
    W.writerow([time.strftime("%F %T"), url, json.dumps(data or {}, ensure_ascii=False), st, len(b)]); LOG.flush()
    return b


def blocked(b):
    return b is not None and b"FOR SECURITY REASONS" in b


def stop_blocked(where, sid):
    prog["blocked_runs"] = prog.get("blocked_runs", 0) + 1
    prog["last_block"] = {"at": time.strftime("%F %T"), "where": where, "sid": sid}
    save(); print(f"站方安全頁：{where} {sid}，停止本次執行", flush=True); sys.exit(2)


def extract(pdf_path):
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_path); out = []
    for i in range(len(doc)):
        t = doc[i].get_textpage().get_text_range()
        s = re.sub(r"\s+", "", t)
        if "有價證券" in s and re.search(r"附表[一二三四五六七八九十]", s) and re.search(r"(期末|年底)?持有之?(重大)?有價證券", s):
            out.append({"page": i + 1, "text": t})
    return out


def main():
    if prog.get("blocked_runs", 0) >= 3:
        print("已連續被擋 3 次，停止抓取等 Ed 決定"); return
    ids = [r["stock_id"] for r in csv.DictReader(open(os.path.join(HERE, "targets_2025_annual.csv")))]
    hold = open(os.path.join(OUT, "holdings_text.jsonl"), "a")
    for sid in ids:
        if sid in prog["done"]:
            continue
        if time.time() - T0 > BUDGET:
            print("時間預算用完，下次接續"); break
        b = req(f"{BASE}?step=1&colorchg=1&co_id={sid}&year={YEAR}&seamon=4&mtype=A")
        if b is None: continue
        if blocked(b): stop_blocked("list", sid)
        t = b.decode("big5", "ignore")
        open(os.path.join(OUT, f"{sid}_list.html"), "w").write(t)
        fn = re.findall(r'readfile2\("A","%s","(\d{6}_%s_AI1\.pdf)"\)' % (sid, sid), t)
        rec = {"sid": sid, "year": YEAR}
        up = re.findall(r"(\d{3}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})", t)
        rec["upload_times"] = up
        if not fn:
            rec["status"] = "no_AI1"; prog["done"][sid] = rec; save(); continue
        b = req(BASE, {"step": "9", "kind": "A", "co_id": sid, "filename": fn[0]})
        if b is None: continue
        if blocked(b): stop_blocked("step9", sid)
        link = re.findall(rb"(?:https://doc\.twse\.com\.tw)?(/pdf/[^'\" >]+\.pdf)", b)
        if not link:
            rec["status"] = "no_link"; prog["done"][sid] = rec; save(); continue
        pdf = req("https://doc.twse.com.tw" + link[0].decode())
        if pdf is None: continue
        if blocked(pdf): stop_blocked("pdf", sid)
        if not pdf.startswith(b"%PDF"):
            rec["status"] = "not_pdf"; prog["done"][sid] = rec; save(); continue
        p = os.path.join(OUT, fn[0]); open(p, "wb").write(pdf)
        rec.update(status="ok", file=fn[0], bytes=len(pdf), sha256=hashlib.sha256(pdf).hexdigest())
        try:
            pages = extract(p); rec["holding_pages"] = [x["page"] for x in pages]
            for x in pages:
                hold.write(json.dumps({"sid": sid, "file": fn[0], **x}, ensure_ascii=False) + "\n")
            hold.flush()
        except Exception as e:
            rec["extract_error"] = str(e)[:200]
        json.dump(rec, open(os.path.join(OUT, f"{sid}.json"), "w"), ensure_ascii=False)
        prog["done"][sid] = rec; prog["blocked_runs"] = 0; save()
    left = len([i for i in ids if i not in prog["done"]])
    prog["remaining"] = left; save(); print(f"完成 {len(prog['done'])}／{len(ids)}，剩 {left}")


main()
