"""估值組共用資料層：官方每日個股本益比、殖利率、股價淨值比原始檔下載（D-071-20261111-2354-1）。

用法：python data_layer/fetch_pbr.py <src>
src：twse_pbr（證交所 BWIBBU_d，官方 2005-09-02 起）
     tpex_pbr（櫃買 afterTrading/peQryDate，官方 2007-01-02 起）
原則（同 fetch_phase2；防錯 A11／退回-60、67）：每筆回應核對回傳日期與查詢一致，不符者不存、記入 attempts；
官方明示查無資料存原檔並標 empty，不推估。可續傳：已存在且已定稿的檔案略過。
順序：先抓每月最後一個交易日（月／季換股日，071 先用），再抓其餘交易日。
"""
import csv, datetime as dt, json, os, sys, time, urllib.request

RAW = os.environ.get("RAW", "raw")
TW = "https://www.twse.com.tw/rwd/zh"
TP = "https://www.tpex.org.tw/www/zh-tw"
UA = "Mozilla/5.0 (elon-bt research)"
TODAY = dt.date.today()
START = {"twse_pbr": dt.date(2005, 9, 2), "tpex_pbr": dt.date(2007, 1, 2)}


def roc(d, sep="/"):
    return f"{d.year - 1911}{sep}{d.month:02d}{sep}{d.day:02d}"


def trading_days(start):
    with open(os.environ.get("CAL", "jobs/trading_days.txt")) as f:
        ds = [dt.date.fromisoformat(x.strip()) for x in f if x.strip()]
    return [d for d in ds if start <= d <= TODAY]


def ordered_days(src):
    """月底交易日優先，其餘交易日其後；兩段內都依日期遞增。"""
    ds = trading_days(START[src])
    me = [d for i, d in enumerate(ds) if i == len(ds) - 1 or ds[i + 1].month != d.month]
    if os.environ.get("ONLY_MONTHEND") == "1":
        return me
    s = set(me)
    return me + [d for d in ds if d not in s]


def url(src, d):
    if src == "twse_pbr":
        return f"{TW}/afterTrading/BWIBBU_d?date={d:%Y%m%d}&selectType=ALL&response=json"
    if src == "tpex_pbr":
        return f"{TP}/afterTrading/peQryDate?date={d:%Y/%m/%d}&response=json"
    raise SystemExit(f"unknown src {src}")


def check(src, j, d):
    """回傳 ok／empty／錯誤字串。日期不符一律不存。"""
    if src == "twse_pbr":
        s = str(j.get("stat", ""))
        if s.upper() != "OK":
            return "empty" if ("沒有符合" in s or "查無" in s) else f"stat={s[:40]}"
        if j.get("date") != d.strftime("%Y%m%d"):
            return f"date不符:{j.get('date')}"
        want = f"{d.year - 1911:02d}年{d.month:02d}月{d.day:02d}日"
        if not (j.get("title") or "").startswith(want):
            return f"title不符:{j.get('title')}"
        if "股價淨值比" not in (j.get("fields") or []):
            return "缺股價淨值比欄"
        return "ok" if j.get("data") else "empty"
    if src == "tpex_pbr":
        ts = j.get("tables") or []
        if not ts:
            return "無tables"
        t = ts[0]
        if t.get("date") != roc(d):
            return f"date不符:{t.get('date')}"
        if not t.get("data"):
            return "empty"
        if "股價淨值比" not in (t.get("fields") or []):
            return "缺股價淨值比欄"
        return "ok"
    return "未定義核對"


def main(src):
    out = os.path.join(RAW, "pbr", src)
    os.makedirs(out, exist_ok=True)
    logp = os.path.join(RAW, f"_attempts_pbr_{src}.csv")
    new = not os.path.exists(logp)
    log = open(logp, "a", newline="")
    w = csv.writer(log)
    if new:
        w.writerow(["ts", "key", "result", "url"])
    gap = float(os.environ.get("GAP", "3"))
    budget = time.time() + 60 * float(os.environ.get("BUDGET_MIN", "320"))
    missing, done = 0, 0
    for d in ordered_days(src):
        key = d.strftime("%Y%m%d")
        fp = os.path.join(out, f"{key}.json")
        # 日檔：收盤後公布；抓取日晚於資料日才算定稿（當日抓的檔隔日重抓一次）
        if os.path.exists(fp) and (d < TODAY - dt.timedelta(days=1)):
            continue
        if time.time() > budget:
            missing += 1
            continue
        u = url(src, d)
        res = "?"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=180) as r:
                    body = r.read()
                res = check(src, json.loads(body), d)
                if res in ("ok", "empty"):
                    with open(fp, "wb") as f:
                        f.write(body)
                    break
            except Exception as e:
                res = f"err:{type(e).__name__}:{str(e)[:60]}"
            time.sleep(gap * (attempt + 2))
        w.writerow([dt.datetime.now().isoformat(timespec="seconds"), key, res, u])
        log.flush()
        done += 1
        if res not in ("ok", "empty"):
            missing += 1
        time.sleep(gap)
    if missing == 0 and os.environ.get("ONLY_MONTHEND") != "1":
        open(os.path.join(RAW, f"_pbr_{src}_complete"), "w").write(f"{TODAY.isoformat()}\n")
    print(src, "fetched", done, "missing", missing)


if __name__ == "__main__":
    main(sys.argv[1])
