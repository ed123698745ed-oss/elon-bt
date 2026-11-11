"""可轉債（含交換債）發行基本資料：公開資訊觀測站 t120sg01（債券基本資料，某申報年月的快照）。
目標清單 jobs/cb_targets.csv（bond_id, issuer, yrn, months）；依序試 months，取到「債券代碼：<bond_id>」即成功；
都沒有時（或 months 空白）改試 2006～2026 年各年 6 月。回應存 RAW/cb/<bond_id>.html；嘗試紀錄 RAW/_attempts_cb.csv。
不推估：取不到就記 notfound。可續傳：已成功者略過。環境：RAW、GAP（秒）、BUDGET_MIN。"""
import csv, datetime as dt, os, sys, time, urllib.request

RAW = os.environ.get("RAW", "raw")
GAP = float(os.environ.get("GAP", "3"))
BUDGET = float(os.environ.get("BUDGET_MIN", "320")) * 60
UA = "Mozilla/5.0 (elon-bt cb)"
BASE = ("https://mopsov.twse.com.tw/mops/web/t120sg01?TYPEK=&bond_kind=5&bond_subn=%24M00000001&come=2"
        "&encodeURIComponent=1&firstin=ture&pg=&step=0&tg=&bond_id={b}&bond_yrn={y}&issuer_stock_code={i}&monyr_reg={m}")
FALLBACK = [f"{y}06" for y in range(2006, 2027)]


def get(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://mopsov.twse.com.tw/mops/web/t120sb02_q10"}), timeout=30)
    return r.read().decode("utf-8", "ignore")


def main():
    t0 = time.time()
    out = os.path.join(RAW, "cb"); os.makedirs(out, exist_ok=True)
    logp = os.path.join(RAW, "_attempts_cb.csv")
    done = {}
    if os.path.exists(logp):
        for r in csv.DictReader(open(logp, encoding="utf-8")):
            if r["result"] in ("ok", "notfound"):
                done[r["bond_id"]] = r["result"]
    new = not os.path.exists(logp)
    lf = open(logp, "a", newline="", encoding="utf-8"); w = csv.writer(lf)
    if new:
        w.writerow(["ts", "bond_id", "monyr", "result", "note"])
    targets = list(csv.DictReader(open("jobs/cb_targets.csv", encoding="utf-8")))
    left = 0
    for tg in targets:
        b = tg["bond_id"]
        if b in done:
            continue
        if time.time() - t0 > BUDGET:
            left += 1
            continue
        months = [m for m in tg["months"].split(";") if m]
        if months:   # 有線索者只補試線索年份前後一年的 6 月，避免每檔試滿 21 年
            ys = sorted(int(m[:4]) for m in months)
            fb = [f"{y}06" for y in range(max(2006, ys[0] - 1), min(2026, ys[-1] + 1) + 1)]
        else:
            fb = FALLBACK
        tried, hit = [], None
        for m in months + [x for x in fb if x not in months]:
            try:
                h = get(BASE.format(b=b, y=tg["yrn"], i=tg["issuer"], m=m))
            except Exception as e:
                w.writerow([dt.datetime.utcnow().isoformat(), b, m, "error", str(e)[:80]]); lf.flush()
                time.sleep(GAP * 3); hit = "error"; break
            tried.append(m)
            time.sleep(GAP)
            if f"債券代碼：{b}" in h.replace("&nbsp;", "").replace(" ", ""):
                open(os.path.join(out, f"{b}.html"), "w", encoding="utf-8").write(h)
                w.writerow([dt.datetime.utcnow().isoformat(), b, m, "ok", f"tries={len(tried)}"]); lf.flush()
                hit = "ok"; break
            if "安全性考量" in h:
                w.writerow([dt.datetime.utcnow().isoformat(), b, m, "error", "blocked"]); lf.flush()
                time.sleep(60); hit = "error"; break
        if len(done) + targets.index(tg) % 25 == 0:
            print("progress", targets.index(tg), b, hit, flush=True)
        if hit is None:
            w.writerow([dt.datetime.utcnow().isoformat(), b, ";".join(tried[:3]) + f"..({len(tried)})", "notfound", ""]); lf.flush()
        elif hit == "error":
            left += 1
    lf.close()
    if left == 0:
        open(os.path.join(RAW, "_cb_complete"), "w").write(dt.date.today().isoformat())
    print("left", left)


if __name__ == "__main__":
    main()
