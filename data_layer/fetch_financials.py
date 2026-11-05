"""財報原始資料下載與建置（051 等財報類多空卡共用；Ed 2026-11-05 12:21 同意甲方案）。

- 資料集：TaiwanStockFinancialStatements（綜合損益表）、TaiwanStockBalanceSheet（資產負債表）。
- 代號範圍：沿用第一期 universe()（上市、上櫃現行 ∪ 已下市，4 碼），清單取自 raw-progress 的
  TaiwanStockInfo／TaiwanStockDelisting，與 data-20261105 一致。
- 只存原樣回傳；FinMind 給的是現行（最終修訂）值，不是公告當時版本（D-051-20261104-1052-3）。
- 下載時段沿用 Ed 2026-11-04 10:05 指示：台北 17:00～隔日 08:00（ALLOW_HOURS）。
- 全部抓完後建 financials.parquet 與 manifest_fin.json；缺值不推估。

環境變數：RAW_DIR（預設 raw_fin）、OUT_DIR（預設 out_fin）、BUDGET_MIN、ALLOW_HOURS、FINMIND_TOKEN_1..4。
"""
import hashlib, json, os, sys, time
from datetime import datetime, timezone

os.environ.setdefault("RAW_DIR", "raw_fin")
sys.path.insert(0, os.path.dirname(__file__))
import fetch_finmind as fm  # noqa: E402

FIN = ["TaiwanStockFinancialStatements", "TaiwanStockBalanceSheet"]
OUT = os.environ.get("OUT_DIR", "out_fin")


def remaining(ids):
    return [(ds, i) for ds in FIN for i in ids if not os.path.exists(fm.path(ds, i))]


def fetch():
    deadline = time.time() + fm.BUDGET_MIN * 60
    ids = fm.universe()
    todo = remaining(ids)
    print(f"universe {len(ids)} ids, todo {len(todo)} requests", flush=True)
    c = fm.Client(fm.tokens())
    done = errors = 0
    for ds, i in todo:
        d = c.get(ds, i, deadline=deadline)
        if d is None:  # 超出時段或時間預算，下次接續
            break
        if d.get("error"):  # 非 200 且非可重試：不存檔，下次再試；請求已寫入 _attempts_finmind.csv
            errors += 1
            continue
        fm.save(fm.path(ds, i), d)
        done += 1
        if done % 200 == 0:
            print(f"{done}/{len(todo)}", flush=True)
    st = {"universe": len(ids), "remaining": len(remaining(ids)), "done_this_run": done,
          "errors_this_run": errors, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    json.dump(st, open(os.path.join(fm.RAW, "_status_fin.json"), "w"))
    print(st, flush=True)
    return st


def build():
    import pandas as pd
    ids = fm.universe()
    left = remaining(ids)
    if left:
        sys.exit(f"尚有 {len(left)} 筆未下載，不建置")
    os.makedirs(OUT, exist_ok=True)
    rows, per = [], {}
    for ds in FIN:
        empty = 0
        for i in ids:
            data = fm.load(fm.path(ds, i)).get("data", [])
            if not data:
                empty += 1
            for x in data:
                rows.append({"stock_id": str(x.get("stock_id", i)), "date": x["date"], "dataset": ds,
                             "type": x["type"], "value": x["value"], "origin_name": x.get("origin_name", "")})
        per[ds] = {"ids": len(ids), "ids_without_data": empty}
    df = pd.DataFrame(rows)
    df["stock_id"] = df["stock_id"].astype(str)
    df = df.sort_values(["dataset", "stock_id", "date", "type"]).reset_index(drop=True)
    p = os.path.join(OUT, "financials.parquet")
    df.to_parquet(p, index=False)
    sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
    m = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "source": "FinMind api/v4 " + ", ".join(FIN),
         "version_note": "FinMind 現行（最終修訂）值，非公告當時版本；重編影響於各案注意事項揭露",
         "files": {"financials.parquet": {"rows": len(df), "sha256": sha}},
         "per_dataset": per,
         "date_range": [df["date"].min(), df["date"].max()] if len(df) else None,
         "code_commit": os.environ.get("GITHUB_SHA", "")}
    json.dump(m, open(os.path.join(OUT, "manifest_fin.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(m, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"fetch": fetch, "build": build}[sys.argv[1] if len(sys.argv) > 1 else "fetch"]()
