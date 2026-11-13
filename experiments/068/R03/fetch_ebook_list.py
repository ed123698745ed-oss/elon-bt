"""068 R03（D-068-20261113-1738-2）：證交所財報電子書清單頁（doc.twse.com.tw t57sb01 step=1）原始 HTML。
只抓清單頁、不下載 PDF；用來取得每份季報／年報的實際上傳時間與是否有更正版本，核對 V-TOP10 訊號當時財報是否已公開。
禮貌規則同 data_layer/fetch_fin_ebook.py：依序、間隔 ≥ INTERVAL 秒、一般 urllib、遇站方安全頁即停止（下次接續）。
環境：KEYS（csv：stock_id, roc_year, seamon）、OUT、INTERVAL、BUDGET_MIN。"""
import csv, gzip, json, os, sys, time, urllib.request

BASE = "https://doc.twse.com.tw/server-java/t57sb01"
INTERVAL = float(os.environ.get("INTERVAL", "30"))
BUDGET = float(os.environ.get("BUDGET_MIN", "320")) * 60
OUT = os.environ.get("OUT", "raw_068list")
os.makedirs(os.path.join(OUT, "html"), exist_ok=True)
PROG = os.path.join(OUT, "progress.json")
prog = json.load(open(PROG)) if os.path.exists(PROG) else {"done": {}, "blocked_runs": 0}
LOG = open(os.path.join(OUT, "_attempts.csv"), "a", newline="")
W = csv.writer(LOG)
T0 = time.time()


def save():
    json.dump(prog, open(PROG, "w"), ensure_ascii=False, indent=0)


def main():
    if prog.get("blocked_runs", 0) >= 3:
        print("已連續被擋 3 次，停止抓取等 Ed 決定"); return
    todo = list(csv.DictReader(open(os.environ["KEYS"])))
    for r in todo:
        key = f"{r['stock_id']}_{r['roc_year']}_{r['seamon']}"
        if key in prog["done"]:
            continue
        if time.time() - T0 > BUDGET:
            print("時間預算用完，下次接續"); break
        url = f"{BASE}?step=1&colorchg=1&co_id={r['stock_id']}&year={r['roc_year']}&seamon={r['seamon']}&mtype=A"
        time.sleep(INTERVAL)
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=120) as resp:
                b = resp.read(); st = resp.status
        except Exception as e:
            W.writerow([time.strftime("%F %T"), url, "ERR", str(e)[:200]]); LOG.flush(); continue
        W.writerow([time.strftime("%F %T"), url, st, len(b)]); LOG.flush()
        if b"FOR SECURITY REASONS" in b:
            prog["blocked_runs"] = prog.get("blocked_runs", 0) + 1
            prog["last_block"] = {"at": time.strftime("%F %T"), "key": key}; save()
            print("站方安全頁，停止本次", key); sys.exit(2)
        with gzip.open(os.path.join(OUT, "html", key + ".html.gz"), "wb") as f:
            f.write(b)
        prog["done"][key] = {"at": time.strftime("%F %T"), "bytes": len(b)}
        prog["blocked_runs"] = 0; save()
    left = sum(1 for r in todo if f"{r['stock_id']}_{r['roc_year']}_{r['seamon']}" not in prog["done"])
    prog["remaining"] = left; save()
    if left == 0:
        open(os.path.join(OUT, "_complete"), "w").write(time.strftime("%F"))
    print(f"完成 {len(prog['done'])}／{len(todo)}，剩 {left}")


main()
