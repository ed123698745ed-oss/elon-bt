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


def req(url, data=None, timeout=120):
    time.sleep(INTERVAL)
    body = urllib.parse.urlencode(data).encode() if data else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=timeout) as r:
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


def keep(t):
    y = re.sub(r"\s+", "", t)
    return "母公司業主" in y or ("歸屬於" in y and "損益" in y) or bool(re.search(r"86[12]0", y))


def ocr_png(path):
    import subprocess
    env = dict(os.environ, OMP_THREAD_LIMIT="1")   # 4 頁並行時，每個 tesseract 只用 1 執行緒，避免互搶導致逾時
    try:
        r = subprocess.run(["tesseract", path, "-", "-l", "chi_tra+eng", "--psm", "6"],
                           capture_output=True, text=True, timeout=600, env=env)
        return r.stdout
    except subprocess.TimeoutExpired:
        return ""


def pages_with(pdf_path):
    """保留損益表候選頁。有文字層就直接取；全檔沒有文字層（掃描檔）時改用 OCR，並標 ocr。
    掃描檔只辨識前 18 頁（財報的綜合損益表多在第 5～13 頁），4 個行程並行；前 18 頁都沒有才再辨識第 19～40 頁。"""
    import pypdfium2 as pdfium, tempfile
    from concurrent.futures import ThreadPoolExecutor
    doc = pdfium.PdfDocument(pdf_path)
    texts = [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    chars = sum(len(re.sub(r"\s+", "", t)) for t in texts)
    ocr = chars < 200
    out = []
    if not ocr:
        out = [{"page": i + 1, "text": t, "ocr": False} for i, t in enumerate(texts) if keep(t)]
        return out, chars, len(doc), ocr
    tmp = tempfile.mkdtemp()
    for lo, hi in ((0, 18), (18, 40)):
        idx = list(range(lo, min(hi, len(doc))))
        paths = []
        for i in idx:
            pth = os.path.join(tmp, f"p{i}.png")
            doc[i].render(scale=250 / 72).to_pil().convert("L").save(pth); paths.append(pth)
        with ThreadPoolExecutor(4) as ex:
            res = list(ex.map(ocr_png, paths))
        for i, t in zip(idx, res):
            if keep(t) or re.search(r"(^|\n)\s*86[01]0\D", t):
                out.append({"page": i + 1, "text": t, "ocr": True})
        for pth in paths:
            os.remove(pth)
        if any(re.search(r"86[12]0|母\s*公\s*司\s*業\s*主", x["text"]) for x in out):
            break
    return out, chars, len(doc), ocr


def redo(d0):
    """舊版沒存到頁面（含掃描檔未 OCR）、或「有上傳紀錄卻沒對到檔名」的紀錄重抓一次。"""
    if d0.get("status") == "ok" and not d0.get("pages") and (d0.get("v", 1) < 3 or d0.get("extract_error")):
        return d0.get("tries", 1) < 3   # OCR 一再失敗者最多試 3 次，之後列資料不足

    return d0.get("status") in ("no_file", "no_link") and bool(d0.get("upload_times")) and d0.get("v_nf", 1) < 5


def main():
    if prog.get("blocked_runs", 0) >= 3:
        print("已連續被擋 3 次，停止抓取等 Ed 決定"); return
    todo = list(csv.DictReader(open(os.environ.get("REPORTS") or os.path.join(HERE, "data_seed", "fin_ebook_reports.csv"))))
    pj = open(os.path.join(OUT, "pages.jsonl"), "a")
    for r in todo:
        sid, y, s = r["stock_id"], r["roc_year"], r["seamon"]
        key = f"{sid}_{y}_{s}"
        d0 = prog["done"].get(key)
        if d0 and not redo(d0):
            continue   # 舊版沒存到頁面（含掃描檔未 OCR）的紀錄用新規則重抓一次
        if time.time() - T0 > BUDGET:
            print("時間預算用完，下次接續"); break
        b = req(f"{BASE}?step=1&colorchg=1&co_id={sid}&year={y}&seamon={s}&mtype=A")
        if b is None: continue
        if blocked(b): stop("list", key)
        t = b.decode("big5", "ignore")
        allf = re.findall(r'readfile2?\("A","%s","(\d{6}_%s_AI[123]\.(?:pdf|zip))"\)' % (sid, sid), t)
        fn = sorted(set(allf), key=lambda x: x[-5])[:1]
        rec = {"tries": (d0 or {}).get("tries", 1) + 1 if d0 else 1, "key": key, "upload_times": re.findall(r"(\d{3}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})", t), "files": sorted(set(allf)), "v_nf": 5}
        if not fn and rec["upload_times"]:
            # 有上傳紀錄卻沒對到 AI1～3 檔名（2026-11-14 發現 2475、5305 等）：存列表頁原文，改用寬鬆檔名
            os.makedirs(os.path.join(OUT, "listpages"), exist_ok=True)
            open(os.path.join(OUT, "listpages", key + ".html"), "w").write(t)
            loose = sorted(set(re.findall(r'readfile2?\(\s*"[A-Z]*"\s*,\s*"%s"\s*,\s*"([^"]+?\.(?:pdf|zip))"' % sid, t, re.I)))
            rec["files_loose"] = loose
            fn = loose[:1]
        if not fn:
            rec["status"] = "no_file"; prog["done"][key] = rec; save(); continue
        b = req(BASE, {"step": "9", "kind": "A", "co_id": sid, "filename": fn[0]})
        if b is None: continue
        if blocked(b): stop("step9", key)
        if b.startswith(b"PK") or b.startswith(b"%PDF"):
            pdf = b   # zip 檔 step9 直接回傳檔案本身（2475 的 102、106 年）
        else:
            link = re.findall(rb"(?:https://doc\.twse\.com\.tw)?(/pdf/[^'\" >]+\.(?:pdf|zip))", b)
            if not link:
                rec["status"] = "no_link"; prog["done"][key] = rec; save(); continue
            pdf = req("https://doc.twse.com.tw" + link[0].decode(), timeout=900)   # PDF 常數 MB、站方慢，120 秒常逾時
            if pdf is None: continue
            if blocked(pdf): stop("pdf", key)
        if pdf.startswith(b"PK"):   # 102 年前後部分公司上傳 zip（內含 PDF；2475、5305）
            import io, zipfile
            try:
                z = zipfile.ZipFile(io.BytesIO(pdf))
                mem = sorted((m for m in z.infolist() if m.filename.lower().endswith(".pdf")), key=lambda m: -m.file_size)
                if mem:
                    rec["zip_member"] = mem[0].filename
                    pdf = z.read(mem[0])
            except Exception as e:
                rec["zip_error"] = str(e)[:200]
        if not pdf.startswith(b"%PDF"):
            rec["status"] = "not_pdf"; prog["done"][key] = rec; save(); continue
        p = os.path.join(OUT, "tmp.pdf"); open(p, "wb").write(pdf)
        rec.update(status="ok", file=fn[0], bytes=len(pdf), sha256=hashlib.sha256(pdf).hexdigest())
        try:
            rec.pop("extract_error", None)
            pg, chars, npages, ocr = pages_with(p); rec["pages"] = [x["page"] for x in pg]
            rec.update(text_chars=chars, n_pages=npages, ocr=ocr, v=3)
            for x in pg:
                pj.write(json.dumps({"key": key, "file": fn[0], **x}, ensure_ascii=False) + "\n")
            pj.flush()
        except Exception as e:
            rec["extract_error"] = str(e)[:200]
        os.remove(p)
        prog["done"][key] = rec; prog["blocked_runs"] = 0; save()
    def pending(k):
        d0 = prog["done"].get(k)
        return d0 is None or redo(d0)
    left = sum(1 for r in todo if pending(f"{r['stock_id']}_{r['roc_year']}_{r['seamon']}"))
    prog["remaining"] = left; save()
    if left == 0:
        open(os.path.join(OUT, "_complete"), "w").write(time.strftime("%F"))
    elif os.path.exists(os.path.join(OUT, "_complete")):
        os.remove(os.path.join(OUT, "_complete"))   # 規則更新後又有待重抓者
    print(f"完成 {len(prog['done'])}／{len(todo)}，剩 {left}")


main()
