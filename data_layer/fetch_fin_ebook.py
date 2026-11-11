"""財報補正：證交所財報電子書（doc.twse.com.tw t57sb01）季報／年報 PDF（Ed 2026-11-11 選「恆等式＋電子書」）。
讀 data_seed/fin_ebook_reports.csv（stock_id, roc_year, seamon），每份：清單頁(step=1) → 下載連結(step=9) → PDF。
合併報表 AI1 優先，沒有時依序 AI2、AI3（同 064 做法）。只保存含「母公司業主」的頁面文字（pages.jsonl）與 PDF 的 sha256；
PDF 本身不保存（檔名、頁碼可回 doc.twse.com.tw 重抓核對）。
禮貌規則：請求依序、間隔 ≥ INTERVAL 秒；一般 urllib，不偽裝瀏覽器、不換 IP。遇站方安全頁即停止本次（下次接續）。
環境：OUT（輸出／進度資料夾）、INTERVAL、BUDGET_MIN。"""
import csv, hashlib, json, os, re, sys, time, urllib.parse, urllib.request

BASE = "https://doc.twse.com.tw/server-java/t57sb01"
INTERVAL = float(os.environ.get("INTERVAL", "20"))
BUDGET = float(os.environ.get("BUDGET_MIN", "320")) * 60
OUT = os.environ.get("OUT", "raw_ebook")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(OUT, exist_ok=True)
PROG = os.path.join(OUT, "progress.json")
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
    except Exception as e:
        W.writerow([time.strftime("%F %T"), url, json.dumps(data or {}, ensure_ascii=False), "ERR", str(e)[:200]]); LOG.flush()
        return None
    W.writerow([time.strftime("%F %T"), url, json.dumps(data or {}, ensure_ascii=False), st, len(b)]); LOG.flush()
    return b


def blocked(b):
    return b is not None and b"FOR SECURITY REASONS" in b


def stop(where, key):
    prog["blocked_runs"] = prog.get("blocked_runs", 0) + 1
    prog["last_block"] = {"at": time.strftime("%F %T"), "where": where, "key": key}
    save(); print(f"站方安全頁：{where} {key}，停止本次", flush=True); sys.exit(2)


def pages_with(pdf_path):
    """保留損益表候選頁：含「母公司業主」或「歸屬於」且含「損益」。另回傳全檔字數，判斷是否為掃描檔。"""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_path); out = []; chars = 0
    for i in range(len(doc)):
        t = doc[i].get_textpage().get_text_range()
        y = re.sub(r"\s+", "", t); chars += len(y)
        if "母公司業主" in y or ("歸屬於" in y and "損益" in y):
            out.append({"page": i + 1, "text": t})
    return out, chars, len(doc)


def main():
    if prog.get("blocked_runs", 0) >= 3:
        print("已連續被擋 3 次，停止抓取等 Ed 決定"); return
    todo = list(csv.DictReader(open(os.environ.get("REPORTS") or os.path.join(HERE, "data_seed", "fin_ebook_reports.csv"))))
    pj = open(os.path.join(OUT, "pages.jsonl"), "a")
    for r in todo:
        sid, y, s = r["stock_id"], r["roc_year"], r["seamon"]
        key = f"{sid}_{y}_{s}"
        d0 = prog["done"].get(key)
        if d0 and not (d0.get("status") == "ok" and not d0.get("pages") and d0.get("v") != 2):
            continue   # 第一版只存含「母公司業主」頁；沒存到頁面的舊紀錄用新規則重抓一次
        if time.time() - T0 > BUDGET:
            print("時間預算用完，下次接續"); break
        b = req(f"{BASE}?step=1&colorchg=1&co_id={sid}&year={y}&seamon={s}&mtype=A")
        if b is None: continue
        if blocked(b): stop("list", key)
        t = b.decode("big5", "ignore")
        allf = re.findall(r'readfile2\("A","%s","(\d{6}_%s_AI[123]\.pdf)"\)' % (sid, sid), t)
        fn = sorted(set(allf), key=lambda x: x[-5])[:1]
        rec = {"key": key, "upload_times": re.findall(r"(\d{3}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})", t), "files": sorted(set(allf))}
        if not fn:
            rec["status"] = "no_file"; prog["done"][key] = rec; save(); continue
        b = req(BASE, {"step": "9", "kind": "A", "co_id": sid, "filename": fn[0]})
        if b is None: continue
        if blocked(b): stop("step9", key)
        link = re.findall(rb"(?:https://doc\.twse\.com\.tw)?(/pdf/[^'\" >]+\.pdf)", b)
        if not link:
            rec["status"] = "no_link"; prog["done"][key] = rec; save(); continue
        pdf = req("https://doc.twse.com.tw" + link[0].decode())
        if pdf is None: continue
        if blocked(pdf): stop("pdf", key)
        if not pdf.startswith(b"%PDF"):
            rec["status"] = "not_pdf"; prog["done"][key] = rec; save(); continue
        p = os.path.join(OUT, "tmp.pdf"); open(p, "wb").write(pdf)
        rec.update(status="ok", file=fn[0], bytes=len(pdf), sha256=hashlib.sha256(pdf).hexdigest())
        try:
            pg, chars, npages = pages_with(p); rec["pages"] = [x["page"] for x in pg]
            rec.update(text_chars=chars, n_pages=npages, v=2)
            for x in pg:
                pj.write(json.dumps({"key": key, "file": fn[0], **x}, ensure_ascii=False) + "\n")
            pj.flush()
        except Exception as e:
            rec["extract_error"] = str(e)[:200]
        os.remove(p)
        prog["done"][key] = rec; prog["blocked_runs"] = 0; save()
    def pending(k):
        d0 = prog["done"].get(k)
        return d0 is None or (d0.get("status") == "ok" and not d0.get("pages") and d0.get("v") != 2)
    left = sum(1 for r in todo if pending(f"{r['stock_id']}_{r['roc_year']}_{r['seamon']}"))
    prog["remaining"] = left; save()
    if left == 0:
        open(os.path.join(OUT, "_complete"), "w").write(time.strftime("%F"))
    print(f"完成 {len(prog['done'])}／{len(todo)}，剩 {left}")


main()
