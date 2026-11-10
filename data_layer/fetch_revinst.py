"""月營收與三大法人買賣超原始資料下載與建置（067 濾網 E-Test、073 月營收卡等共用；
Ed 2026-11-11 00:16：「把月營收和三大法人資料加進 elon-bt 共用資料層，用 GitHub Actions 在夜間慢慢抓」，D-067-20261111-0016-1）。

- 資料集：TaiwanStockMonthRevenue（月營收）、TaiwanStockInstitutionalInvestorsBuySell（三大法人買賣超，FinMind 自 2012-05 起）。
- 代號範圍：沿用第一期 universe()（上市、上櫃現行 ∪ 已下市，4 碼），清單取自 raw-progress 的 TaiwanStockInfo／TaiwanStockDelisting。
- 只存原樣回傳；月營收為 FinMind 現行值，不是公告當時版本；可得時點由各案依法定期限（次月 10 日）另定。
- 下載時段：夜間（ALLOW_HOURS，預設 17-8）。全部抓完後建 month_revenue.parquet、institutional.parquet 與 manifest_revinst.json；缺值不推估。

環境變數：RAW_DIR（預設 raw_ri）、OUT_DIR（預設 out_ri）、BUDGET_MIN、ALLOW_HOURS、FINMIND_TOKEN_1..4。
"""
import hashlib, json, os, sys, time
from datetime import datetime, timezone

os.environ.setdefault("RAW_DIR", "raw_ri")
sys.path.insert(0, os.path.dirname(__file__))
import fetch_finmind as fm  # noqa: E402

DS = ["TaiwanStockMonthRevenue", "TaiwanStockInstitutionalInvestorsBuySell"]
OUT = os.environ.get("OUT_DIR", "out_ri")


def remaining(ids):
    return [(ds, i) for ds in DS for i in ids if not os.path.exists(fm.path(ds, i))]


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
        if d.get("error"):  # 非 200 且非可重試：不存檔，下次再試
            errors += 1
            continue
        fm.save(fm.path(ds, i), d)
        done += 1
        if done % 200 == 0:
            print(f"{done}/{len(todo)}", flush=True)
    st = {"universe": len(ids), "remaining": len(remaining(ids)), "done_this_run": done,
          "errors_this_run": errors, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    json.dump(st, open(os.path.join(fm.RAW, "_status_revinst.json"), "w"))
    print(st, flush=True)
    return st


def _rows(ds, ids):
    out, empty = [], 0
    for i in ids:
        data = fm.load(fm.path(ds, i)).get("data", [])
        if not data:
            empty += 1
        for x in data:
            x = dict(x); x["stock_id"] = str(x.get("stock_id", i)); out.append(x)
    return out, empty


def build():
    import pandas as pd
    ids = fm.universe()
    left = remaining(ids)
    if left:
        sys.exit(f"尚有 {len(left)} 筆未下載，不建置")
    os.makedirs(OUT, exist_ok=True)
    files, per = {}, {}
    # 月營收：一檔一月一列；date 為 FinMind 標記日（營收月份的次月 1 日），不是公告日
    r, e = _rows(DS[0], ids)
    rev = pd.DataFrame(r)
    keep = [c for c in ["stock_id", "date", "revenue_year", "revenue_month", "revenue", "country"] if c in rev.columns]
    rev = rev[keep].drop_duplicates(["stock_id", "revenue_year", "revenue_month"], keep="last")
    rev = rev.sort_values(["stock_id", "revenue_year", "revenue_month"]).reset_index(drop=True)
    per[DS[0]] = {"ids": len(ids), "ids_without_data": e}
    # 三大法人：一檔一日一身分一列（股數）
    r, e = _rows(DS[1], ids)
    ins = pd.DataFrame(r)[["date", "stock_id", "name", "buy", "sell"]]
    ins = ins.drop_duplicates(["date", "stock_id", "name"], keep="last").sort_values(["stock_id", "date", "name"]).reset_index(drop=True)
    per[DS[1]] = {"ids": len(ids), "ids_without_data": e}
    for name, df in (("month_revenue", rev), ("institutional", ins)):
        p = os.path.join(OUT, f"{name}.parquet")
        df.to_parquet(p, index=False)
        files[f"{name}.parquet"] = {"rows": len(df), "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(),
                                    "date_range": [str(df["date"].min()), str(df["date"].max())] if len(df) else None}
    m = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "source": "FinMind api/v4 " + ", ".join(DS),
         "version_note": "FinMind 現行值，非公告當時版本；月營收可得時點依次月 10 日法定期限由各案推算；法人資料於當日盤後公布",
         "files": files, "per_dataset": per, "code_commit": os.environ.get("GITHUB_SHA", "")}
    json.dump(m, open(os.path.join(OUT, "manifest_revinst.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(m, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"fetch": fetch, "build": build}[sys.argv[1] if len(sys.argv) > 1 else "fetch"]()
