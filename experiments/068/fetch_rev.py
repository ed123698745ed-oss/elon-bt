"""068 快篩：FinMind TaiwanStockMonthRevenue 原始下載（D-068-20261111-0018-1；非共用資料層，列資料層待補清單）。

- 代號清單：experiments/068/ids068.txt（elon-bt data-20261105r68 daily_k 於 2012-01-01～2022-06-30 出現的四碼普通股，非 91xx）。
- 期間：2011-01-01～2022-06-30（只到樣本內切點，樣本外不下載）；年增需前一年同月。
- 只存原樣回傳（raw_rev/finmind/TaiwanStockMonthRevenue/<id>.json.gz）；每次請求記入 raw_rev/_attempts_finmind.csv。
- token 只讀 repo Secrets；台北 17:00～08:00 下載（Ed 2026-11-04 10:05）。重試與冷卻規則同 data_layer/fetch_finmind.Client。
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data_layer"))
os.environ.setdefault("RAW_DIR", "raw_rev")
import fetch_finmind as fm  # noqa: E402

DS = "TaiwanStockMonthRevenue"
START = os.environ.get("REV_START", "2011-01-01")
END = os.environ.get("REV_END", "2022-06-30")
IDS = [l.strip() for l in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ids068.txt")) if l.strip()]


class C(fm.Client):
    def get(self, dataset, data_id=None, deadline=None):
        url = fm.API + "?" + urllib.parse.urlencode(dict(dataset=dataset, data_id=data_id, start_date=START, end_date=END))
        while True:
            if (deadline and time.time() > deadline) or not fm.allowed_now():
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
                data = json.load(urllib.request.urlopen(req, timeout=120))
                code = 200
            except urllib.error.HTTPError as e:
                code = e.code
            except Exception:
                code = -1
            n = len(data.get("data", [])) if data else ""
            self.w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), dataset, data_id, t[-6:], code, n])
            self.log.flush()
            if code == 200:
                if data.get("status") not in (200, None):
                    return {"status": data.get("status"), "data": [], "error": True}
                return data
            if code == 402:
                self.cool[t] = time.time() + fm.COOLDOWN
                continue
            if code in (-1, 429, 500, 502, 503, 504):
                time.sleep(10)
                continue
            return {"status": code, "data": [], "error": True}


def main():
    deadline = time.time() + fm.BUDGET_MIN * 60
    c = C(fm.tokens())
    todo = [i for i in IDS if not os.path.exists(fm.path(DS, i))]
    print(f"ids {len(IDS)} todo {len(todo)}", flush=True)
    done = err = 0
    for sid in todo:
        d = c.get(DS, sid, deadline=deadline)
        if d is None:
            break
        if d.get("error"):
            err += 1
            continue
        d["_query"] = {"dataset": DS, "data_id": sid, "start_date": START, "end_date": END}
        fm.save(fm.path(DS, sid), d)
        done += 1
    left = sum(not os.path.exists(fm.path(DS, i)) for i in IDS)
    st = {"ids": len(IDS), "remaining": left, "done_this_run": done, "errors_this_run": err,
          "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    json.dump(st, open(os.path.join(fm.RAW, "_status_rev.json"), "w"))
    print(st, flush=True)


if __name__ == "__main__":
    main()
