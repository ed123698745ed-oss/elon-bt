"""逐日市場別與櫃買歷史除權息的官方原始檔下載（可續傳，原樣保存，回傳日期核對）。

退回-67（Eve 2026-11-05）：櫃買舊端點對不支援的日期不報錯而回傳「當日」資料，
舊程式未核對回傳日期，致 2003～2010 櫃買除權息整段空白。本程式每次下載都核對回傳
日期／代號／月份與查詢一致，不一致記 mismatch、不存檔。

用法：python data_layer/fetch_market.py tpex|tpex_stock|twse
  tpex：櫃買除權息歷史（2000-09 起，2007 以前 exDailyQHis、2008 起 exDailyQ）
        ＋櫃買每日收盤行情（2007-07 起逐交易日）
        ＋櫃買個股月成交（jobs/market_need_months.csv 中 2007-07 以前的股票月份）
  twse：證交所每日收盤行情 MI_INDEX（2004-02-11 起逐交易日）
        ＋證交所個股月成交 STOCK_DAY（2004-02 以前的股票月份）
每次請求寫入 raw/_attempts_market_<src>.csv。BUDGET_MIN 分鐘到即停，下次續傳。
"""
import csv, glob, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timezone

RAW = os.environ.get("RAW_DIR", "raw")
OUT = os.path.join(RAW, "market")
UA = {"User-Agent": "Mozilla/5.0 (elon-bt research)"}
GAP = float(os.environ.get("GAP", "2.0"))
DEADLINE = time.time() + 60 * float(os.environ.get("BUDGET_MIN", "330"))
JOBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "jobs")


def trading_days():
    return [l.strip() for l in open(os.path.join(JOBS, "trading_days.txt")) if l.strip()]


def need_months():
    r = csv.DictReader(open(os.path.join(JOBS, "market_need_months.csv")))
    return [(x["stock_id"], x["ym"]) for x in r]


def roc(d):  # '2003-07-31' -> '92/07/31'
    y, m, dd = d.split("-")
    return f"{int(y) - 1911}/{m}/{dd}"


def tpex_jobs():
    t = date.today()
    for y in range(2000, t.year + 1):
        s = "2000/09/01" if y == 2000 else f"{y}/01/01"
        ep = "exDailyQHis" if y <= 2007 else "exDailyQ"
        url = f"https://www.tpex.org.tw/www/zh-tw/bulletin/{ep}?startDate={s}&endDate={y}/12/31&response=json"
        exp = s.replace("/", "")
        yield f"tpex_exright/{y}.json", ("GET", url, None), ("date_prefix", exp), y == t.year
    for y in range(2013, t.year + 1):  # 櫃買減資恢復買賣參考價（含每仟股換發新股、每股退還股款；官方表 2013 起有資料）
        url = f"https://www.tpex.org.tw/www/zh-tw/bulletin/revivt?startDate={y}/01/01&endDate={y}/12/31&response=json"
        yield f"tpex_reduction/{y}.json", ("GET", url, None), ("date_prefix", f"{y}0101"), y == t.year
    for d in trading_days():
        if d < "2007-07-01":
            continue
        body = urllib.parse.urlencode({"date": d.replace("-", "/"), "type": "AL", "response": "json"}).encode()
        yield (f"tpex_daily/{d[:4]}/{d}.json", ("POST", "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc", body),
               ("table_date", roc(d)), False)



def tpex_stock_jobs():
    for sid, ym in need_months():
        if ym >= "2007-07":
            continue
        y, m = ym.split("-")
        body = urllib.parse.urlencode({"code": sid, "date": f"{y}/{m}/01", "response": "json"}).encode()
        yield (f"tpex_stock/{sid}/{ym}.json", ("POST", "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock", body),
               ("stock_month", (sid, y, m)), False)


def twse_jobs():
    t = date.today()
    for y in range(2011, t.year + 1):  # 證交所減資恢復買賣參考價格（官方 2011-01-01 起提供）
        url = f"https://www.twse.com.tw/rwd/zh/reducation/TWTAUU?startDate={y}0101&endDate={y}1231&response=json"
        yield f"twse_reduction/{y}.json", ("GET", url, None), ("twse_range", f"{y}0101"), y == t.year
    for y in range(2011, t.year + 1):  # ETF 分割／反分割、面額變更恢復買賣參考價（端點名稱待首次回應確認，失敗照記）
        for code, sub in (("TWTCAU", "split"), ("TWTB8U", "change")):
            url = f"https://www.twse.com.tw/rwd/zh/{sub}/{code}?startDate={y}0101&endDate={y}1231&response=json"
            yield f"twse_{code.lower()}/{y}.json", ("GET", url, None), ("twse_range", f"{y}0101"), y == t.year
    for d in trading_days():
        if d < "2004-02-11":
            continue
        k = d.replace("-", "")
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={k}&type=ALLBUT0999&response=json"
        yield f"twse_daily/{d[:4]}/{d}.json", ("GET", url, None), ("date_eq", k), False
    # 證交所 STOCK_DAY 只提供 2010-01-04 起、MI_INDEX 只提供 2004-02-11 起（官方回應「查詢日期小於…」），
    # 2004-02-11 前的上市逐日身分無官方逐日來源 → 不抓，相關列在資料層標「官方無逐日來源」隔離。
    # 減資明細（每壹仟股換發新股票、每股退還股款、減資後現增）：TWTAVUDetail，依已下載的 TWTAUU 年表逐列產生。
    for f in sorted(glob.glob(os.path.join(OUT, "twse_reduction", "*.json"))):
        for r in json.load(open(f, encoding="utf-8")).get("data") or []:
            det = str(r[-1]).replace(" ", "").split(",")
            if len(det) < 2:
                continue
            sid, fd = det[0], det[1]
            url = f"https://www.twse.com.tw/rwd/zh/reducation/TWTAVUDetail?STK_NO={sid}&FILE_DATE={fd}&response=json"
            yield f"twse_reduction_detail/{sid}_{fd}.json", ("GET", url, None), ("twse_red_detail", (sid, str(r[0]))), False


def check(j, rule):
    """回傳 (ok, 說明)。ok=True 才存檔；空結果但日期正確也算 ok（代表當日／當月該市場無資料）。"""
    kind, exp = rule
    if kind == "date_prefix":
        got = str(j.get("date", ""))
        return got.startswith(exp), got
    if kind == "table_date":
        t = (j.get("tables") or [{}])[0]
        got = str(t.get("date", ""))
        return got == exp, got
    if kind == "stock_month":
        sid, y, m = exp
        t = (j.get("tables") or [{}])[0]
        got = str(t.get("date", ""))
        sub = str(t.get("subtitle", ""))
        rows = t.get("data") or []
        if not rows:  # 無成交資料：日期須為查詢月份
            return got[:6] == f"{y}{m}", f"empty {got}"
        ok = got[:6] == f"{y}{m}" and sub.startswith(sid) and all(r[0][: len(str(int(y) - 1911)) + 3] == f"{int(y) - 1911}/{m}" for r in rows)
        return ok, f"{got} {sub}"
    if kind == "date_eq":
        got = str(j.get("date", ""))
        st = str(j.get("stat", ""))
        if "沒有符合" in st or "很抱歉" in st:
            return got in ("", exp), f"nodata {st}"
        return got == exp, got
    if kind == "twse_range":
        st = str(j.get("stat", ""))
        return st == "OK" or "沒有符合" in st, f"{st} {j.get('date', '')} {str(j.get('fields', ''))[:200]}"
    if kind == "twse_red_detail":
        sid, resume = exp
        if str(j.get("stat", "")) != "OK" or not j.get("data"):
            return False, f"stat {j.get('stat')}"
        row = j["data"][0]
        stop = str(row[2]).strip()
        try:
            n1 = [int(x) for x in stop.split("/")]; n2 = [int(x) for x in resume.split("/")]
            from datetime import date as _d
            gap = (_d(n2[0] + 1911, n2[1], n2[2]) - _d(n1[0] + 1911, n1[1], n1[2])).days
        except Exception:
            return False, f"bad dates {stop} {resume}"
        return str(row[0]).strip() == sid and 0 < gap <= 45, f"{row[0].strip()} stop {stop} resume {resume} gap {gap}"
    if kind == "stock_month_twse":
        sid, y, m = exp
        got = str(j.get("date", ""))
        st = str(j.get("stat", ""))
        title = str(j.get("title", ""))
        if st != "OK":
            return "沒有符合" in st or "很抱歉" in st, f"nodata {st}"
        return got[:6] == f"{y}{m}" and sid in title, f"{got} {title[:30]}"
    return False, "unknown rule"


def main(src):
    jobs = {"tpex": tpex_jobs, "tpex_stock": tpex_stock_jobs, "twse": twse_jobs}[src]
    os.makedirs(OUT, exist_ok=True)
    logp = os.path.join(RAW, f"_attempts_market_{src}" + (f"_s{os.environ['SHARD_K']}" if os.environ.get("SHARD_N") else "") + ".csv")
    new = not os.path.exists(logp)
    log = csv.writer(open(logp, "a", newline=""))
    if new:
        log.writerow(["utc", "file", "method", "url", "body", "http", "bytes", "result", "returned"])
    done = skipped = 0
    shard_n, shard_k = int(os.environ.get("SHARD_N", "1")), int(os.environ.get("SHARD_K", "0"))
    for i, (name, (method, url, body), rule, refresh) in enumerate(jobs()):
        if i % shard_n != shard_k:
            continue
        p = os.path.join(OUT, name)
        if os.path.exists(p) and not refresh:
            skipped += 1
            continue
        if time.time() > DEADLINE:
            print(f"budget reached; done={done} skipped={skipped}")
            return
        os.makedirs(os.path.dirname(p), exist_ok=True)
        code, raw, res, got = 0, b"", "error", ""
        try:
            req = urllib.request.Request(url, data=body, headers=UA, method=method)
            raw = urllib.request.urlopen(req, timeout=180).read()
            code = 200
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:
            code, got = -1, type(e).__name__
        if code == 200:
            try:
                ok, got = check(json.loads(raw), rule)
                res = "ok" if ok else "mismatch"
            except Exception:
                res = "not_json"
        log.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), name, method, url,
                      (body or b"").decode(), code, len(raw), res, got])
        if res == "ok":
            open(p, "wb").write(raw)
            done += 1
        time.sleep(GAP if res != "error" else GAP * 5)
    print(f"all jobs finished; done={done} skipped={skipped}")
    if os.environ.get("SHARD_N"):
        return
    missing = [n for n, _, _, _ in jobs() if not os.path.exists(os.path.join(OUT, n))]
    if missing:  # 有缺檔（連線錯誤未存）就不標完成，下一輪續抓
        print(f"missing {len(missing)} files, e.g. {missing[:5]}")
        return
    open(os.path.join(RAW, f"_market_{src}_complete"), "w").write(datetime.now(timezone.utc).isoformat())


if __name__ == "__main__":
    main(sys.argv[1])
