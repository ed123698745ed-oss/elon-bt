"""fetch-market 進度摘要：依 attempts 檔統計結果，寫 _status_market_<src>.json。"""
import collections, csv, json, os, sys

src = sys.argv[1]
rows = list(csv.DictReader(open(f"raw/_attempts_market_{src}.csv")))
c = collections.Counter(r["result"] for r in rows)
files = sum(len(fs) for _, _, fs in os.walk("raw/market"))
json.dump({"src": src, "attempts": len(rows), "by_result": c, "files": files,
           "complete": os.path.exists(f"raw/_market_{src}_complete")},
          open(f"_status_market_{src}.json", "w"), ensure_ascii=False)
print(src, dict(c), "files", files)
