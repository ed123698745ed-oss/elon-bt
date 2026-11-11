"""可轉債組（cb）建置：官方（公開資訊觀測站 t120sg01）為主、Ed 種子清單（data_seed/cb_seed_20260830_*）補缺。
規則：
- 每個關鍵欄位輸出值與 <欄>_src；官方有值用官方。
- 種子值屬推算（轉換起始日「規則推算*」、發行掛牌日「MOPS賣回權公告反推*」）不進主欄，另存 <欄>_est。
- 官方與種子（非推算）不一致者主欄用官方，conflict 欄列出欄名與差異，不自行判定對錯。
- 種子標示的待核（多世代歧義、疑年報董事會日、董事會決議日衝突、日期衝突待判）寫入 flags。
環境：RAW（含 cb/*.html、_attempts_cb.csv）、SEED（預設 data_seed）、OUT。"""
import csv, glob, os, re, sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cb_parse import parse  # noqa: E402

RAW = os.environ.get("RAW", "raw"); SEED = os.environ.get("SEED", "data_seed"); OUT = os.environ.get("OUT", "out_cb")
OFF = "MOPS t120sg01"

# 官方欄 -> (種子欄, 種子來源欄)
MAP = {
    "issue_date": ("發行掛牌日", "發行掛牌日_來源"),      # 種子此欄＝發行（掛牌）日，與官方發行日期比對
    "maturity_date": ("到期日", "到期日_來源"),
    "delist_date": ("下櫃日", None),
    "conv_start": ("轉換起始日", "轉換起始日來源"),
    "conv_end": ("轉換截止日", None),
    "amount_issued": ("發行總額(億)", None),
    "guarantee": ("擔保", "擔保_來源"),
    "coupon_rate": ("票面利率_新", None),
}
SEED_ONLY = {"board_date": ("董事會決議日", "董事會決議日_來源"), "pricing_date": ("訂價日", "訂價日_來源"),
             "first_put_date": ("賣回權日", "賣回權日_來源"), "effective_date_seed": ("申報生效日", "申報生效日_來源")}
EST = {"conv_start": r"規則推算", "issue_date": r"反推"}


def d(x):
    v = pd.to_datetime(x, errors="coerce")
    return None if pd.isna(v) else v.normalize()


def main():
    os.makedirs(OUT, exist_ok=True)
    seed = pd.read_csv(os.path.join(SEED, "cb_seed_20260830_main.csv"), dtype={"代號": str})
    seed["代號"] = seed["代號"].str.strip()
    att = {}
    if os.path.exists(os.path.join(RAW, "_attempts_cb.csv")):
        for r in csv.DictReader(open(os.path.join(RAW, "_attempts_cb.csv"), encoding="utf-8")):
            if r["result"] in ("ok", "notfound"):
                att[r["bond_id"]] = (r["result"], r["monyr"])
    off = {}
    for f in glob.glob(os.path.join(RAW, "cb", "*.html")):
        b = os.path.basename(f)[:-5]
        p = parse(open(f, encoding="utf-8").read())
        if p and p["bond_id"] == b:
            p["snapshot_month"] = att.get(b, ("", ""))[1]
            off[b] = p
    multigen = set(pd.read_csv(os.path.join(SEED, "cb_seed_20260830_multigen.csv"), dtype={"代號": str})["代號"].str.strip())
    bconf = set(pd.read_csv(os.path.join(SEED, "cb_seed_20260830_board_conflict.csv"), dtype={"代號": str})["代號"].str.strip())
    dconf = pd.read_csv(os.path.join(SEED, "cb_seed_20260830_date_conflict.csv"), dtype={"代號": str})
    dconf = dconf.groupby(dconf["代號"].str.strip())["欄位"].apply(lambda s: "、".join(sorted(set(s)))).to_dict()

    rows = []
    for sd in seed.to_dict("records"):
        sd = {k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in sd.items()}
        b = sd["代號"]; o = off.get(b)
        r = {"bond_id": b, "name_seed": sd.get("名稱"), "issuer": b[:4],
             "official_status": "官方取得" if o else ("官方查無" if att.get(b, ("",))[0] == "notfound" else "未下載"),
             "snapshot_month": o.get("snapshot_month") if o else None}
        conflicts, flags = [], []
        for k, (sc, ssrc) in MAP.items():
            ov = o.get(k) if o else None
            sv = sd.get(sc); src_s = str(sd.get(ssrc) or "原表") if ssrc else "原表"
            if k.endswith("date") or k.startswith("conv_s") or k == "conv_end":
                ov, sv = d(ov), d(sv)
            elif k == "amount_issued":
                sv = None if sv is None else float(sv) * 1e8
            elif k == "coupon_rate" and sv is not None:
                m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(sv))
                sv = float(m.group(1)) if m else None
                src_s = "原表（自票面利率文字取數）"
            elif isinstance(sv, float) and pd.isna(sv):
                sv = None
            if k == "guarantee" and ov:
                r["guarantee_detail"] = ov
                ov = "有擔保" if str(ov).startswith("有") else ("無擔保" if str(ov).startswith("無") else ov)
            est = bool(sv is not None and k in EST and re.search(EST[k], src_s))
            if ov is not None and not (isinstance(ov, float) and pd.isna(ov)):
                r[k], r[k + "_src"] = ov, OFF
                if sv is not None and not est and ov != sv:
                    conflicts.append(f"{k}（官方 {ov.date() if hasattr(ov,'date') else ov}／種子 {sv.date() if hasattr(sv,'date') else sv}）")
            elif sv is not None and not est:
                r[k], r[k + "_src"] = sv, f"種子：{src_s}"
            else:
                r[k], r[k + "_src"] = None, None
            if est:
                r[k + "_est"], r[k + "_est_src"] = sv, f"種子推算：{src_s}"
        for k, (sc, ssrc) in SEED_ONLY.items():
            sv = d(sd.get(sc)); r[k] = sv; r[k + "_src"] = f"種子：{sd.get(ssrc) or '原表'}" if sv is not None else None
        if o:
            for k in ("short_name", "apply_date", "approve_date", "listing_date", "listing_status", "tenor", "amount_applied",
                      "face_value", "units", "issue_price", "conv_price_issue", "conv_premium", "conv_price_latest",
                      "conv_price_latest_eff", "put_terms", "call_terms", "underwriter", "raise_way", "private_board_date"):
                r[k] = d(o[k]) if k.endswith(("_date", "_eff")) else o[k]
        r["delist_reason_seed"] = sd.get("下櫃原因")
        if b in multigen:
            flags.append("代號多世代歧義")
        if str(sd.get("疑年報董事會日")) == "Y":
            flags.append("董事會決議日疑為年報董事會日")
        if b in bconf:
            flags.append("董事會決議日衝突待核")
        if b in dconf:
            flags.append(f"種子日期衝突待判（{dconf[b]}）")
        r["conflict"] = "；".join(conflicts); r["flags"] = "；".join(flags)
        rows.append(r)
    df = pd.DataFrame(rows)
    for c in df.columns:
        if c.endswith(("_date", "_start", "_end", "_eff", "_est")) and not c.endswith("_src"):
            df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in ("amount_issued", "coupon_rate", "amount_applied", "face_value", "units", "issue_price", "conv_price_issue",
              "conv_premium", "conv_price_latest"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace("%", "").str.replace(",", ""), errors="coerce")
    for c in df.columns:
        if df[c].dtype == object and not c.endswith(tuple(MAP)) and c not in ("conflict", "flags"):
            df[c] = df[c].where(df[c].isna(), df[c].astype(str))
    df["guarantee"] = df["guarantee"].where(df["guarantee"].isna(), df["guarantee"].astype(str))
    df.to_parquet(os.path.join(OUT, "cb_issues.parquet"), index=False)

    tr = pd.read_csv(os.path.join(SEED, "cb_seed_20260830_trail.csv"), dtype={"代號": str})
    tr["代號"] = tr["代號"].str.strip()
    tr = tr.rename(columns={"代號": "bond_id", "生效日": "effective", "原價": "price_before", "新價": "price_after", "申報日": "report_date_roc"})
    tr["effective"] = pd.to_datetime(tr["effective"], errors="coerce")
    n0 = len(tr)
    tr = tr.sort_values(["bond_id", "effective", "report_date_roc"]).drop_duplicates(["bond_id", "effective", "price_before", "price_after"], keep="first")
    tr["in_issues"] = tr["bond_id"].isin(df["bond_id"])
    tr["src"] = "種子：MOPS 轉換價格調整公告"
    tr.to_parquet(os.path.join(OUT, "cb_conv_price.parquet"), index=False)
    print("cb_issues", len(df), df["official_status"].value_counts().to_dict())
    for k in list(MAP) + list(SEED_ONLY):
        print(f"  {k}: 缺 {df[k].isna().mean():.1%}  來源 {df[k + '_src'].str[:12].value_counts().to_dict()}")
    print("  conflict 列", int((df["conflict"] != "").sum()), " flags 列", int((df["flags"] != "").sum()))
    print("cb_conv_price", n0, "→", len(tr), "去重", n0 - len(tr), "代號不在清單", int((~tr["in_issues"]).sum()))


if __name__ == "__main__":
    main()
