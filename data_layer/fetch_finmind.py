"""FinMind 原始資料下載（可續傳）。

只存原樣回傳，不清理；清理在 build 階段做。
- token 由環境變數 FINMIND_TOKENS（空白分隔）或 FINMIND_TOKEN_1..4 提供，不寫進程式。
- 402（額度用完）時該 token 冷卻，全部冷卻就等待；超過時間預算即停止，下次接續。
- 每次請求寫入 raw/_attempts_finmind.csv（時間、資料集、代號、token尾碼、HTTP狀態、筆數）。
"""
import csv, gzip, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

RAW = os.environ.get("RAW_DIR", "raw")
API = "https://api.finmindtrade.com/api/v4/data"
BUDGET_MIN = float(os.environ.get("BUDGET_MIN", "330"))
COOLDOWN = 15 * 60
START = "1990-01-01"

GLOBAL = ["TaiwanStockInfo", "TaiwanStockDelisting", "TaiwanStockSplitPrice", "TaiwanStockTradingDate"]
PER_ID = ["TaiwanStockPrice", "TaiwanStockDividendResult", "TaiwanStockDividend",
          "TaiwanStockCapitalReductionReferencePrice"]


def tokens():
    t = os.environ.get("FINMIND_TOKENS", "").split()
    t += [os.environ[k] for k in sorted(os.environ) if re.fullmatch(r"FINMIND_TOKEN_\d+", k) and os.environ[k]]
    if not t and os.path.exists(os.path.expanduser("~/.finmind_tokens")):
        t = open(os.path.expanduser("~/.finmind_tokens")).read().split()
    if not t:
        sys.exit("no FinMind token")
    return list(dict.fromkeys(t))


class Client:
    def __init__(self, toks):
        self.toks = toks
        self.cool = {t: 0.0 for t in toks}
        self.i = 0
        os.makedirs(RAW, exist_ok=True)
        self.log = open(os.path.join(RAW, "_attempts_finmind.csv"), "a", newline="")
        self.w = csv.writer(self.log)

    def get(self, dataset, data_id=None, deadline=None):
        p = {"dataset": dataset}
        if data_id:
            p.update(data_id=data_id, start_date=START)
        url = API + "?" + urllib.parse.urlencode(p)
        while True:
            if deadline and time.time() > deadline:
                return None
            now = time.time()
            ready = [t for t in self.toks if self.cool[t] <= now]
            if not ready:
                wait = min(self.cool.values()) - now + 5
                if deadline and now + wait > deadline:
                    return None
                print(f"all tokens cooling, sleep {wait:.0f}s", flush=True)
                time.sleep(max(wait, 5))
                continue
            t = ready[self.i % len(ready)]
            self.i += 1
            code, data = 0, None
            try:
                req = urllib.request.Request(url, headers={"Authorization": "Bearer " + t})
                d = json.load(urllib.request.urlopen(req, timeout=120))
                code, data = 200, d
            except urllib.error.HTTPError as e:
                code = e.code
            except Exception as e:  # network
                code = -1
            n = len(data.get("data", [])) if data else ""
            self.w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), dataset,
                             data_id or "", t[-6:], code, n])
            self.log.flush()
            if code == 200:
                return data
            if code == 402:
                self.cool[t] = time.time() + COOLDOWN
                continue
            if code in (-1, 429, 500, 502, 503, 504):
                time.sleep(10)
                continue
            return {"status": code, "data": [], "error": True}


def path(dataset, data_id=None):
    d = os.path.join(RAW, "finmind", dataset)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, (data_id or "_all") + ".json.gz")


def save(p, obj):
    tmp = p + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, p)


def load(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def universe():
    """上市、上櫃現行代號 ∪ 已下市代號；第一期只收 4 碼代號（普通股與 4 碼 ETF）。"""
    ids = set()
    for x in load(path("TaiwanStockInfo"))["data"]:
        if x["type"] in ("twse", "tpex"):
            ids.add(x["stock_id"])
    for x in load(path("TaiwanStockDelisting"))["data"]:
        ids.add(x["stock_id"])
    return sorted(i for i in ids if re.fullmatch(r"\d{4}", i))


def main():
    deadline = time.time() + BUDGET_MIN * 60
    c = Client(tokens())
    for ds in GLOBAL:
        p = path(ds)
        if not os.path.exists(p):
            d = c.get(ds, deadline=deadline)
            if d is None:
                break
            save(p, d)
    ids = universe()
    todo = [(ds, i) for ds in PER_ID for i in ids if not os.path.exists(path(ds, i))]
    print(f"universe {len(ids)} ids, todo {len(todo)} requests", flush=True)
    done = 0
    for ds, i in todo:
        d = c.get(ds, i, deadline=deadline)
        if d is None:
            break
        save(path(ds, i), d)
        done += 1
        if done % 200 == 0:
            print(f"{done}/{len(todo)}", flush=True)
    left = sum(1 for ds in PER_ID for i in ids if not os.path.exists(path(ds, i)))
    status = {"universe": len(ids), "remaining": left,
              "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    json.dump(status, open(os.path.join(RAW, "_status_finmind.json"), "w"))
    print(status)


if __name__ == "__main__":
    main()
