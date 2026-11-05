"""逐日市場別與櫃買歷史除權息的官方原始檔下載（可續傳，原樣保存，回傳日期核對）。

退回-67（Eve 2026-11-05）：櫃買舊端點對不支援的日期不報錯而回傳「當日」資料，
舊程式未核對回傳日期，致 2003～2010 櫃買除權息整段空白。本程式每次下載都核對回傳
日期／代號／月份與查詢一致，不一致記 mismatch、不存檔。

用法：python data_layer/fetch_market.py tpex|twse
  tpex：櫃買除權息歷史（2000-09 起，2007 以前 exDailyQHis、2008 起 exDailyQ）
        ＋櫃買每日收盤行情（2007-07 起逐交易日）
        ＋櫃買個股月成交（jobs/market_need_months.csv 中 2007-07 以前的股票月份）
  twse：證交所每日收盤行情 MI_INDEX（2004-02-11 起逐交易日）
        ＋證交所個股月成交 STOCK_DAY（2004-02 以前的股票月份）
每次請求寫入 raw/_attempts_market_<src>.csv。BUDGET_MIN 分鐘到即停，下次續傳。
"""
import csv, json, os, sys, time, urllib.error, urllib.parse, urllib.request
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
    cal_months = [("1101", f"{y}-{m:02d}") for y in range(1999, 2005) for m in range(1, 13) if f"{y}-{m:02d}" < "2004-03"]
    for sid, ym in cal_months + need_months():  # 1101 台泥 1999-01～2004-02 全月：2004-02-11 前的官方交易日曆核對用
        if ym >= "2004-03":
            continue
        y, m = ym.split("-")
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={y}{m}01&stockNo={sid}&response=json"
        yield f"twse_stock/{sid}/{ym}.json", ("GET", url, None), ("stock_month_twse", (sid, y, m)), False


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
    jobs = tpex_jobs if src == "tpex" else twse_jobs
    os.makedirs(OUT, exist_ok=True)
    logp = os.path.join(RAW, f"_attempts_market_{src}.csv")
    new = not os.path.exists(logp)
    log = csv.writer(open(logp, "a", newline=""))
    if new:
        log.writerow(["utc", "file", "method", "url", "body", "http", "bytes", "result", "returned"])
    done = skipped = 0
    for name, (method, url, body), rule, refresh in jobs():
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
            raw = urllib.request.urlopen(req, timeout=60).read()
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
    open(os.path.join(RAW, f"_market_{src}_complete"), "w").write(datetime.now(timezone.utc).isoformat())


if __name__ == "__main__":
    main(sys.argv[1])
