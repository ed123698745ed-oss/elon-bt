"""官方來源原始資料下載（可續傳，原樣保存）。

- TWSE 休市日（每年一檔）、TWSE 終止上市清單、TWSE 上市公司基本資料（含上市日期）
- TPEx 上櫃公司基本資料、TPEx 除權除息計算結果（每月一檔）
- TWSE TWT49U 除權除息計算結果（每月一檔；部分網路環境會被 TWSE 安全機制擋下，失敗照記不推估）
每次請求寫入 raw/_attempts_official.csv。請求間隔 3 秒。
"""
import csv, os, time, urllib.error, urllib.request
from datetime import date, datetime, timezone

RAW = os.environ.get("RAW_DIR", "raw")
UA = {"User-Agent": "Mozilla/5.0 (elon-bt research)"}
GAP = 3.0
OUT = os.path.join(RAW, "official")


def months(y0, m0):
    t = date.today()
    y, m = y0, m0
    while (y, m) <= (t.year, t.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def last_day(y, m):
    return (date(y + (m == 12), m % 12 + 1, 1) - date.resolution).day


def jobs():
    t = date.today()
    yield "twse_suspend_listing.json", "https://www.twse.com.tw/rwd/zh/company/suspendListing?response=json"
    yield "twse_t187ap03_L.json", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    yield "tpex_t187ap03_O.json", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
    for y in range(1990, t.year + 2):
        yield f"twse_holiday/{y}.json", f"https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?date={y}&response=json"
    for y, m in months(2003, 1):
        d1, d2 = f"{y}{m:02d}01", f"{y}{m:02d}{last_day(y, m):02d}"
        yield f"twse_twt49u/{y}{m:02d}.json", f"https://www.twse.com.tw/rwd/zh/exRight/TWT49U?response=json&startDate={d1}&endDate={d2}"
    for y, m in months(2003, 1):
        r = y - 1911
        yield (f"tpex_exright/{y}{m:02d}.json",
               f"https://www.tpex.org.tw/web/stock/exright/dailyquo/exDailyQ_result.php?l=zh-tw&d={r}/{m:02d}/01&ed={r}/{m:02d}/{last_day(y, m):02d}&o=json")


def main():
    os.makedirs(OUT, exist_ok=True)
    log = csv.writer(open(os.path.join(RAW, "_attempts_official.csv"), "a", newline=""))
    cur_month = date.today().strftime("%Y%m")
    for name, url in jobs():
        p = os.path.join(OUT, name)
        if os.path.exists(p) and cur_month not in name:
            continue
        os.makedirs(os.path.dirname(p), exist_ok=True)
        code, body = 0, b""
        try:
            body = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
            code = 200
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception:
            code = -1
        ok = code == 200 and body[:1] in (b"{", b"[")
        log.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), name, url, code,
                      len(body), "ok" if ok else "blocked_or_error"])
        if ok:
            open(p, "wb").write(body)
        time.sleep(GAP)


if __name__ == "__main__":
    main()
