"""第二期共用資料層：官方原始檔下載（報酬指數、處置／注意、融資融券、平盤下放空名單）。

用法：python data_layer/fetch_phase2.py <src>
src：twse_fulldelivery twse_tri twse_ix tpex_ix twse_punish twse_notice tpex_disposal tpex_attention
     twse_margin tpex_margin twse_mark tpex_mark tpex_chtm
原則（防錯清單 A11／退回-60、67）：每筆回應都核對回傳的日期／區間與查詢一致，不符者不存、記入 attempts；
查無資料（官方明示）存原檔並標 empty，不推估。可續傳：已存在的檔案略過。
"""
import csv, datetime as dt, json, os, sys, time, urllib.parse, urllib.request

RAW = os.environ.get("RAW", "raw")
TW = "https://www.twse.com.tw/rwd/zh"
TP = "https://www.tpex.org.tw/www/zh-tw"
UA = "Mozilla/5.0 (elon-bt research)"
TODAY = dt.date.today()


def roc(d, sep="/"):
    return f"{d.year - 1911}{sep}{d.month:02d}{sep}{d.day:02d}"


def months(y0, m0):
    y, m = y0, m0
    while (y, m) <= (TODAY.year, TODAY.month):
        yield dt.date(y, m, 1)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def month_end(d):
    n = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return min(n - dt.timedelta(days=1), TODAY)


def period_end(src, d):
    """該筆資料所涵蓋期間的最後一個日曆日：月檔＝月底、年檔＝12/31、日檔＝當日。"""
    if src in ("twse_tri", "twse_ix", "tpex_ix", "twse_notice", "tpex_attention"):
        n = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        return n - dt.timedelta(days=1)
    if src in ("twse_punish", "tpex_disposal"):
        return dt.date(d.year, 12, 31)
    return d


def last_fetch_dates(logpath):
    """各 key 最近一次成功（ok／empty）下載的日期，取自 attempts 紀錄。"""
    out = {}
    if os.path.exists(logpath):
        with open(logpath, newline="") as f:
            for row in csv.DictReader(f):
                if row["result"] in ("ok", "empty"):
                    out[row["key"]] = dt.date.fromisoformat(row["ts"][:10])
    return out


def is_final(src, d, fetched):
    """期間結束『之後』才抓到的檔案才算定稿；期間內（含結束當日）抓的，資料可能不完整，之後要補抓。"""
    return fetched is not None and fetched > period_end(src, d)


def trading_days(start):
    with open("jobs/trading_days.txt") as f:
        ds = [dt.date.fromisoformat(x.strip()) for x in f if x.strip()]
    return [d for d in ds if start <= d <= TODAY]


# 每個來源：產生 (key, url) 與核對函式 check(json, key_date) -> "ok" / "empty" / 錯誤字串
def jobs(src):
    if src == "twse_tri":       # 發行量加權股價報酬指數，官方自 92/01 起
        for d in months(2003, 1):
            yield d.strftime("%Y%m"), f"{TW}/TAIEX/MFI94U?date={d:%Y%m%d}&response=json", d
    elif src == "twse_ix":      # 加權指數開高低收
        for d in months(1999, 1):
            yield d.strftime("%Y%m"), f"{TW}/TAIEX/MI_5MINS_HIST?date={d:%Y%m%d}&response=json", d
    elif src == "tpex_ix":      # 櫃買指數開高低收（月查詢）
        for d in months(2000, 1):
            yield d.strftime("%Y%m"), f"{TP}/indexInfo/inx?date={d:%Y/%m/%d}&response=json", d
    elif src == "twse_punish":
        for y in range(2001, TODAY.year + 1):
            yield str(y), f"{TW}/announcement/punish?startDate={y}0101&endDate={y}1231&response=json", dt.date(y, 1, 1)
    elif src == "twse_notice":
        for d in months(2001, 1):
            e = month_end(d)
            yield d.strftime("%Y%m"), f"{TW}/announcement/notice?startDate={d:%Y%m%d}&endDate={e:%Y%m%d}&response=json", d
    elif src == "tpex_disposal":
        for y in range(2001, TODAY.year + 1):
            yield str(y), f"{TP}/bulletin/disposal?startDate={y}/01/01&endDate={y}/12/31&response=json", dt.date(y, 1, 1)
    elif src == "tpex_attention":
        for d in months(2001, 1):
            e = month_end(d)
            yield d.strftime("%Y%m"), f"{TP}/bulletin/attention?startDate={d:%Y/%m/%d}&endDate={e:%Y/%m/%d}&response=json", d
    elif src == "twse_margin":
        for d in trading_days(dt.date(2001, 1, 2)):
            yield d.strftime("%Y%m%d"), f"{TW}/marginTrading/MI_MARGN?date={d:%Y%m%d}&selectType=ALL&response=json", d
    elif src == "tpex_margin":
        for d in trading_days(dt.date(2007, 1, 2)):
            yield d.strftime("%Y%m%d"), f"{TP}/margin/balance?date={d:%Y/%m/%d}&response=json", d
    elif src == "twse_mark":
        for d in trading_days(dt.date(2013, 1, 2)):
            yield d.strftime("%Y%m%d"), f"{TW}/marginTrading/TWT92U?date={d:%Y%m%d}&response=json", d
    elif src == "tpex_mark":
        for d in trading_days(dt.date(2013, 1, 2)):
            yield d.strftime("%Y%m%d"), f"{TP}/margin/mark?date={d:%Y/%m/%d}&response=json", d
    elif src == "twse_fulldelivery":   # 變更交易（全額交割）每日名單，官方自 93/12/24 起
        for d in trading_days(dt.date(2004, 12, 24)):
            yield d.strftime("%Y%m%d"), f"{TW}/fullDelivery/TWT85U?date={d:%Y%m%d}&response=json", d
    elif src == "tpex_chtm":   # 櫃買變更交易／分盤／管理股票每日名單；API 自 97/04/09 起有資料（04/08 以前回空表）
        for d in trading_days(dt.date(2008, 4, 9)):
            yield d.strftime("%Y%m%d"), f"{TP}/afterTrading/chtm?date={d:%Y/%m/%d}&response=json", d
    else:
        raise SystemExit(f"unknown src {src}")


def check(src, j, d):
    s = str(j.get("stat", "OK"))
    if src.startswith("twse_") and s.upper() != "OK":
        return "empty" if ("查詢日期小於" in s or "沒有符合" in s or "查無" in s) else f"stat={s[:40]}"
    if src in ("twse_tri", "twse_ix"):
        want = f"{d.year - 1911}年{d.month:02d}月"
        if want not in (j.get("title") or ""):
            return f"title不符:{j.get('title')}"
        bad = [r[0] for r in j.get("data", []) if not r[0].strip().startswith(f"{d.year - 1911}/{d.month:02d}/")]
        return f"日期越界{bad[:2]}" if bad else ("ok" if j.get("data") else "empty")
    if src == "tpex_ix":
        t = j["tables"][0]
        if t.get("date") != f"{d.year - 1911}/{d.month:02d}":
            return f"date不符:{t.get('date')}"
        bad = [r[0] for r in t.get("data", []) if not r[0].startswith(f"{d.year}/{d.month:02d}/")]
        return f"日期越界{bad[:2]}" if bad else ("ok" if t.get("data") else "empty")
    if src == "twse_punish":
        want = f"({d.year - 1911}/01/01 至 {d.year - 1911}/12/31)"
        if want not in (j.get("title") or ""):
            return f"title不符:{j.get('title')}"
        return "ok" if j.get("data") else "empty"
    if src == "twse_notice":
        want = f"{d.year - 1911:03d}年{d.month:02d}月01日"
        if want not in (j.get("title") or ""):
            return f"title不符:{j.get('title')}"
        return "ok" if j.get("data") else "empty"
    if src in ("tpex_disposal", "tpex_attention"):
        t = j["tables"][0]
        y = d.year - 1911
        want = f"{y}/01/01 ~ {y}/12/31" if src == "tpex_disposal" else f"{y}/{d.month:02d}/01 至"
        if want not in (t.get("title2") or ""):
            return f"title2不符:{t.get('title2')}"
        return "ok" if t.get("data") else "empty"
    if src == "twse_margin":
        want = f"{d.year - 1911:03d}年{d.month:02d}月{d.day:02d}日"
        ts = j.get("tables", [])
        if not ts or not all((t.get("title") or "").startswith(want) for t in ts if t.get("title")):
            return "title日期不符"
        rows = [r for t in ts if "融資融券彙總" in (t.get("title") or "") for r in (t.get("data") or [])]
        return "ok" if rows else "empty"
    if src == "twse_fulldelivery":
        want = f"{d.year - 1911:03d}年{d.month:02d}月{d.day:02d}日"
        if not (j.get("title") or "").startswith(want):
            return f"title不符:{j.get('title')}"
        return "ok" if j.get("data") else "empty"
    if src == "twse_mark":
        if j.get("date") != d.strftime("%Y%m%d"):
            return f"date不符:{j.get('date')}"
        return "ok" if j.get("data") else "empty"
    if src in ("tpex_margin", "tpex_mark"):
        t = j["tables"][0]
        if j.get("date") != d.strftime("%Y%m%d") or t.get("date") != roc(d):
            return f"date不符:{j.get('date')}/{t.get('date')}"
        rows = [r for r in t.get("data", []) if len(r) > 1]   # 早年平盤下名單只回一列日期，不算資料
        return "ok" if rows else "empty"
    if src == "tpex_chtm":
        t = j["tables"][0]
        if j.get("date") != d.strftime("%Y%m%d") or t.get("date") != roc(d):
            return f"date不符:{j.get('date')}/{t.get('date')}"
        return "ok" if t.get("data") else "empty"
    return "未定義核對"


def main(src):
    out = os.path.join(RAW, "phase2", src)
    os.makedirs(out, exist_ok=True)
    logp = os.path.join(RAW, f"_attempts_phase2_{src}.csv")
    new = not os.path.exists(logp)
    log = open(logp, "a", newline="")
    w = csv.writer(log)
    if new:
        w.writerow(["ts", "key", "result", "url"])
    gap = float(os.environ.get("GAP", "3"))
    budget = time.time() + 60 * float(os.environ.get("BUDGET_MIN", "320"))
    missing = 0
    fetched = last_fetch_dates(logp)
    open_keys = []
    for key, url, d in jobs(src):
        fp = os.path.join(out, f"{key}.json")
        if os.path.exists(fp):
            if is_final(src, d, fetched.get(key)) or period_end(src, d) < TODAY and fetched.get(key) is None:
                continue
            open_keys.append(key)          # 期間未結束就抓過：重抓（失敗時保留舊檔）
        if time.time() > budget:
            missing += 1
            continue
        res = "?"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=180) as r:
                    body = r.read()
                j = json.loads(body)
                res = check(src, j, d)
                if res in ("ok", "empty"):
                    with open(fp, "wb") as f:
                        f.write(body)
                    break
            except Exception as e:
                res = f"err:{type(e).__name__}:{str(e)[:60]}"
            time.sleep(gap * (attempt + 2))
        w.writerow([dt.datetime.now().isoformat(timespec="seconds"), key, res, url])
        log.flush()
        if res not in ("ok", "empty"):
            missing += 1
        time.sleep(gap)
    if missing == 0:
        # 第一行＝本次完整檢查日；open_periods＝期間尚未結束、之後仍會更新的 key（資料只到抓取當日）
        still = [k for k in open_keys]
        open(os.path.join(RAW, f"_phase2_{src}_complete"), "w").write(f"{TODAY.isoformat()}\nopen_periods={','.join(still)}\n")
    print(src, "missing", missing, "open", open_keys)


if __name__ == "__main__":
    main(sys.argv[1])
