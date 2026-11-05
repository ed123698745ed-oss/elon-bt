"""原 7,095 筆跳動重掃（退回-67，Eve：交代多少筆改判、多少股票補回合法交易期間）。

OLD＝data-20261105 輸出資料夾；NEW＝修正版輸出資料夾。
輸出 experiments/out_rescan/：jump_bridge.csv（原跳動逐筆新判定）、new_jumps.csv（新版新增跳動）、summary.json
"""
import json
import os
import sys

import pandas as pd

OLD = os.environ.get("OLD_OUT", "/home/claude/raw_dl/out")
NEW = os.environ.get("ELON_OUT", "/home/claude/raw_dl/out_new")
DST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments", "out_rescan")


def main():
    os.makedirs(DST, exist_ok=True)
    cols = ["date", "stock_id", "close", "prev_close", "ref_price", "limit_up", "limit_down", "limit_src", "jump_flag"]
    o = pd.read_parquet(f"{OLD}/daily_k.parquet", columns=["date", "stock_id", "jump_flag"])
    oj = o[o["jump_flag"]][["date", "stock_id"]]
    n = pd.read_parquet(f"{NEW}/daily_k.parquet", columns=cols + ["market"])
    q = pd.read_parquet(f"{NEW}/daily_k_quarantine.parquet", columns=["date", "stock_id", "quarantine_reason"])
    m = oj.merge(n, on=["date", "stock_id"], how="left").merge(q, on=["date", "stock_id"], how="left")

    def verdict(r):
        if pd.isna(r.market):
            return "移出主日K：" + (r.quarantine_reason if isinstance(r.quarantine_reason, str) else "查無列")
        if bool(r.jump_flag):
            return "仍為跳動"
        if isinstance(r.limit_src, str) and r.limit_src.startswith(("無漲跌幅", "待查")):
            return "改判：" + r.limit_src
        if r.limit_src == "官方除權息表":
            return "改判：官方除權息表界線內（含櫃買 2000～2010 補表）"
        return "改判：其他（公司行動或前收修正）"
    m["new_verdict"] = [verdict(r) for r in m.itertuples()]
    m.to_csv(f"{DST}/jump_bridge.csv", index=False, encoding="utf-8-sig")
    nj = n[n["jump_flag"]].merge(oj.assign(old=True), on=["date", "stock_id"], how="left")
    new_only = nj[nj["old"].isna()].drop(columns=["old"])
    new_only.to_csv(f"{DST}/new_jumps.csv", index=False, encoding="utf-8-sig")

    od = pd.read_parquet(f"{OLD}/daily_k.parquet", columns=["date", "stock_id"])
    key_o = set(zip(od["stock_id"], od["date"]))
    add = n[[(s, d) not in key_o for s, d in zip(n["stock_id"], n["date"])]]
    nd = set(zip(n["stock_id"], n["date"]))
    gone = od[[(s, d) not in nd for s, d in zip(od["stock_id"], od["date"])]]
    summ = {
        "old_jumps": len(oj), "new_jumps": int(n["jump_flag"].sum()),
        "old_jump_verdicts": m["new_verdict"].value_counts().to_dict(),
        "new_jumps_not_in_old": len(new_only),
        "main_rows_old": len(od), "main_rows_new": len(n),
        "rows_added_to_main": len(add), "stocks_with_rows_added": int(add["stock_id"].nunique()),
        "rows_added_by_market": add["market"].value_counts().to_dict(),
        "rows_removed_from_main": len(gone), "stocks_with_rows_removed": int(gone["stock_id"].nunique()),
        "stocks_affected_total": int(len(set(add["stock_id"]) | set(gone["stock_id"]) | set(m.loc[m["new_verdict"] != "仍為跳動", "stock_id"]) | set(new_only["stock_id"]))),
    }
    json.dump(summ, open(f"{DST}/summary.json", "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps(summ, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
