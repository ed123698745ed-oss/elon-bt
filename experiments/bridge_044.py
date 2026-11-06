"""044 新舊版橋接（退回-67，Eve 第一期審查「修正後交新舊批次與排除原因橋接」）。

舊：experiments/out_044（data-20261105，commit d1e2492）
新：RES_DIR（修正後資料標籤重跑 rerun_044.py 的輸出）
輸出 experiments/out_044_bridge/：batch_bridge.csv、position_bridge.csv、period_changes.csv、summary.json
推算換股比歸因：新版未完成部位若持有窗內有 ratio_basis＝僅有反推值 的減資／面額變更 → 歸「推算換股比改列資料不足」。
"""
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = os.environ.get("OLD_RES", os.path.join(ROOT, "experiments", "out_044"))
NEW = os.environ.get("RES_DIR", "/home/claude/rerun044_new")
OUT_DATA = os.environ.get("ELON_OUT", "/home/claude/raw_dl/out_new")
DST = os.environ.get("BRIDGE_DST", os.path.join(ROOT, "experiments", "out_044_bridge"))


def main():
    os.makedirs(DST, exist_ok=True)
    bo, bn = pd.read_csv(f"{OLD}/batches.csv"), pd.read_csv(f"{NEW}/batches.csv")
    po, pn = pd.read_csv(f"{OLD}/positions.csv", dtype={"stock_id": str}), pd.read_csv(f"{NEW}/positions.csv", dtype={"stock_id": str})
    b = bo[["S", "status", "ret"]].merge(bn[["S", "status", "ret"]], on="S", how="outer", suffixes=("_old", "_new"))
    b["status_old"] = b["status_old"].fillna("（舊版無此批）")
    b["status_new"] = b["status_new"].fillna("（新版無此批）")
    b["change"] = [("不變" if o == n else f"{o} → {n}") for o, n in zip(b["status_old"], b["status_new"])]
    b.to_csv(f"{DST}/batch_bridge.csv", index=False, encoding="utf-8-sig")

    k = ["S", "side", "stock_id"]
    p = po[k + ["status", "ret"]].merge(pn[k + ["status", "ret"]], on=k, how="outer", suffixes=("_old", "_new"), indicator=True)
    p["kind"] = p["_merge"].map({"left_only": "只在舊版（新版未入選）", "right_only": "只在新版（新入選）", "both": "兩版都有"})
    ca = pd.read_parquet(f"{OUT_DATA}/corp_actions.parquet") if os.path.exists(f"{OUT_DATA}/corp_actions.parquet") else None
    inferred = {}
    if ca is not None and "ratio_basis" in ca:
        x = ca[ca["ratio_basis"].isin(["僅有反推值", "取不到"]) | ca["source"].astype(str).str.contains("除權除息歷史表")]
        for s, g in x.groupby("stock_id"):
            inferred[s] = list(pd.to_datetime(g["ex_date"]).dt.date)
    reason = []
    for r in p.itertuples():
        if r.kind != "兩版都有":
            reason.append("母體或排序改變（市場別／漲跌幅／跳動修正影響候選）")
        elif r.status_old == r.status_new:
            reason.append("狀態不變" + ("" if pd.isna(r.ret_old) or pd.isna(r.ret_new) or abs(r.ret_old - r.ret_new) < 1e-12 else "；報酬改變"))
        else:
            s0 = pd.Timestamp(r.S).date()
            hit = any(s0 <= d <= (pd.Timestamp(r.S) + pd.Timedelta(days=60)).date() for d in inferred.get(r.stock_id, []))
            if "限幅待查" in str(r.status_new):
                reason.append("限幅待查改列資料不足")
            elif hit and "資料不足" in str(r.status_new):
                reason.append("公司行動資料不足（推算比率或早期櫃買除權息無分項）")
            else:
                reason.append("跳動／漲跌幅判定修正")
    p["reason"] = reason
    p.drop(columns=["_merge"]).to_csv(f"{DST}/position_bridge.csv", index=False, encoding="utf-8-sig")

    to, tn = pd.read_csv(f"{OLD}/ten_stats.csv"), pd.read_csv(f"{NEW}/ten_stats.csv")
    t = to.merge(tn, on="組", suffixes=("_old", "_new"))
    t["顯著判斷改變（p<0.05）"] = (t["雙尾p_old"] < 0.05) != (t["雙尾p_new"] < 0.05)
    t["平均報酬正負改變"] = (t["平均報酬_old"] > 0) != (t["平均報酬_new"] > 0)
    t.to_csv(f"{DST}/period_changes.csv", index=False, encoding="utf-8-sig")

    summ = {
        "batches_old": bo["status"].value_counts().to_dict(), "batches_new": bn["status"].value_counts().to_dict(),
        "batch_changes": b["change"].value_counts().to_dict(),
        "positions_kind": p["kind"].value_counts().to_dict(),
        "position_reason": p["reason"].value_counts().to_dict(),
        "batches_touching_insufficient_actions": int(p.loc[p["reason"].str.startswith("公司行動資料不足"), "S"].nunique()),
        "batches_touching_pending_limit": int(p.loc[p["reason"] == "限幅待查改列資料不足", "S"].nunique()),
        "period_judgement_changed": t.loc[t["顯著判斷改變（p<0.05）"] | t["平均報酬正負改變"], "組"].tolist(),
    }
    json.dump(summ, open(f"{DST}/summary.json", "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps(summ, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
