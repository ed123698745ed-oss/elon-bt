"""財報修正版建置（Eve 2026-11-11 退回 fin-20261107：損益表歸母淨利欄混入歸母綜合損益）。

做法（Ed 2026-11-11 選「恆等式＋電子書」）：
1. 依原始中文科目名稱（origin_name）重新對應：錯標的列改成獨立科目，不再混進淨利欄（REMAP）。
2. 歸母淨利（EquityAttributableToOwnersOfParent）只補「原本被綜合損益佔用」的股季：
   ① 同表有非控制權益淨利：本期淨利 − 非控制權益淨利 − 共同控制下前手淨利；
   ② 同表沒有非控制權益列、或綜合損益歸屬非控制權益為 0，且無共同控制下前手：本期淨利；
   ③ 證交所財報電子書讀到的官方數值（data_seed/fin_ebook.csv）；
   都沒有 → 加一列 value 空值、src＝資料不足（不推估）。
   非控制權益淨利（NoncontrollingInterests）同理：本期淨利 − 歸母淨利 − 前手淨利；綜合損益歸屬非控制權益為 0 時記 0；
   或電子書；都沒有標資料不足。
3. 白名單：輸出的每個 (dataset, type, origin_name) 都要在 data_catalog/fin_origin_whitelist.csv，
   出現新名稱就中止（WHITELIST=build 時改為產生白名單，只供第一次建立與人工審視）。
新增欄 src：FinMind／推導：…／財報電子書／資料不足。
用法：SRC=financials.parquet OUT=out python data_layer/fin_fix.py
"""
import json, os, sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS, BS = "TaiwanStockFinancialStatements", "TaiwanStockBalanceSheet"
NI, NCI = "EquityAttributableToOwnersOfParent", "NoncontrollingInterests"
CI_P, CI_N = "ComprehensiveIncomeAttributableToOwnersOfParent", "ComprehensiveIncomeAttributableToNoncontrollingInterests"
FORM, CI_F = "NetIncomeAttributableToFormerOwnerUnderCommonControl", "ComprehensiveIncomeAttributableToFormerOwnerUnderCommonControl"

# (dataset, 原 type, origin_name) → 新 type。只列語意不同的錯標；同義措辭不改。
REMAP = {
    (IS, NI, "綜合損益總額歸屬於母公司業主"): CI_P,
    (IS, NCI, "綜合損益總額歸屬於非控制權益"): CI_N,
    (IS, "OtherComprehensiveIncomeAfterTax", "本期綜合損益總額（稅後）"): "TotalConsolidatedProfitForThePeriod",
    (IS, "OtherComprehensiveIncomeAfterTaxThePeriod", "本期綜合損益總額（稅後）"): "TotalConsolidatedProfitForThePeriod",
    (IS, "OperatingIncome", "營業收入淨額"): "Revenue",
    (IS, "TotalConsolidatedProfitForThePeriod", "本期損益"): "IncomeAfterTaxes",
    (IS, "-", "合併前非屬共同控制股權損益"): "NetIncomePreMergerNonCommonControl",
    (IS, "-", "合併前非屬共同控制股權綜合損益淨額"): "ComprehensiveIncomePreMergerNonCommonControl",
    (IS, "-", "收回(提存)各項保險責任準備淨額"): "InsuranceReservesNet",
    (IS, "-", "淨利（損）歸屬於共同控制下前手權益"): FORM,
    (IS, "-", "淨利（淨損）歸屬於共同控制下前手權益"): FORM,
    (IS, "-", "綜合損益總額歸屬於共同控制下前手權益"): CI_F,
    (IS, "-", "費損"): "Expenses",
}
WL = os.path.join(ROOT, "data_catalog", "fin_origin_whitelist.csv")
EBOOK = os.environ.get("EBOOK") or os.path.join(ROOT, "data_seed", "fin_ebook.csv")
TOL = 0.5   # 元；重新對應後與既有列比對的容差


def remap(df, log):
    df = df.copy()
    df["src"] = "FinMind"
    key = ["dataset", "type", "origin_name"]
    m = pd.Series([tuple(x) in REMAP for x in df[key].itertuples(index=False)], index=df.index)
    moved = df[m].copy()
    moved["type"] = [REMAP[tuple(x)] for x in moved[key].itertuples(index=False)]
    rest = df[~m]
    pk = ["stock_id", "date", "dataset", "type"]
    # 兩個錯標欄對應到同一科目：數值相同只留一列，不同則後者改名為衝突
    d = moved.duplicated(pk, keep="first")
    if d.any():
        first = moved[~d].set_index(pk)["value"]
        dv = moved[d]
        eq = [abs(v - first.get(tuple(k), np.nan)) <= TOL for k, v in zip(dv[pk].itertuples(index=False), dv["value"])]
        eq = pd.Series(eq, index=dv.index)
        log["remap_internal_dup_dropped"] = int(eq.sum())
        moved.loc[eq[~eq].index, "type"] = moved.loc[eq[~eq].index, "type"] + "_衝突"
        moved = moved.drop(index=eq[eq].index)
    j = moved.merge(rest[pk + ["value"]], on=pk, how="left", suffixes=("", "_old"))
    same = j["value_old"].notna() & ((j["value"] - j["value_old"]).abs() <= TOL)
    clash = j["value_old"].notna() & ~same
    log["remap_rows"] = int(len(moved))
    log["remap_by_rule"] = {f"{a}|{b}→{REMAP[(d, a, b)]}": int(n) for (d, a, b), n in
                            df[m].groupby(key).size().items()}
    log["remap_duplicate_dropped"] = int(same.sum())
    log["remap_clash"] = int(clash.sum())
    if clash.any():   # 目標科目已有不同數值：不覆蓋，兩者都留，重新對應的列改名並記錄
        j.loc[clash, "type"] = j.loc[clash, "type"] + "_衝突"
        j.loc[clash, ["stock_id", "date", "type", "value", "value_old", "origin_name"]].to_csv(
            os.path.join(os.environ.get("OUT", "out"), "remap_clash.csv"), index=False)
    keep = j[~same].drop(columns="value_old")
    out = pd.concat([rest, keep], ignore_index=True)
    assert not out.duplicated(pk).any(), "重新對應後主鍵重複"
    return out


def backfill(df, log):
    s = df[df["dataset"] == IS]
    p = s.pivot_table(index=["stock_id", "date"], columns="type", values="value", aggfunc="first")
    g = lambda c: p[c] if c in p else pd.Series(np.nan, index=p.index)
    iat = g("IncomeAfterTaxes").where(g("IncomeAfterTaxes").notna(), g("IncomeAfterTax"))
    ni, nci, form = g(NI), g(NCI), g(FORM)
    ci_p, ci_n, ci_f = g(CI_P), g(CI_N), g(CI_F)
    no_form = form.isna() & (ci_f.isna() | (ci_f == 0))
    form0 = form.fillna(0)
    eb = pd.read_csv(EBOOK, dtype={"stock_id": str, "date": str}) if os.path.exists(EBOOK) else \
        pd.DataFrame(columns=["stock_id", "date", "type", "value", "file", "page"])
    ebv = {(r.stock_id, r.date, r.type): r for r in eb.itertuples(index=False)}
    rows, stat = [], {}

    def add(k, typ, val, src, origin):
        rows.append({"stock_id": k[0], "date": k[1], "dataset": IS, "type": typ, "value": val,
                     "origin_name": origin, "src": src})
        stat[f"{typ}|{src}"] = stat.get(f"{typ}|{src}", 0) + 1

    # 歸母淨利：只補被綜合損益佔用、且沒有淨利列的股季
    need_ni = p.index[ci_p.notna() & ni.isna()]
    for k in need_ni:
        if pd.notna(iat[k]) and pd.notna(nci[k]) and (pd.notna(form[k]) or no_form[k]):
            add(k, NI, iat[k] - nci[k] - form0[k], "推導：本期淨利−非控制權益淨利", "（補）本期淨利−淨利歸屬於非控制權益")
        elif pd.notna(iat[k]) and nci.isna()[k] and (ci_n.isna()[k] or ci_n[k] == 0) and no_form[k]:
            add(k, NI, iat[k], "推導：無非控制權益（本期淨利）", "（補）本期淨利（無非控制權益）")
        elif (k[0], k[1], NI) in ebv:
            r = ebv[(k[0], k[1], NI)]
            add(k, NI, float(r.value), "財報電子書", f"（補）財報電子書 {r.file} 第{r.page}頁")
        else:
            add(k, NI, np.nan, "資料不足", "（補）資料不足")
    # 非控制權益淨利：被綜合損益佔用、且沒有淨利列的股季
    ni_new = {(r["stock_id"], r["date"]): r["value"] for r in rows if r["type"] == NI}
    need_nci = p.index[ci_n.notna() & nci.isna()]
    for k in need_nci:
        n_ = ni[k] if pd.notna(ni[k]) else ni_new.get(k, np.nan)
        src_ni_derived = k in ni_new
        if ci_n[k] == 0 and no_form[k]:
            add(k, NCI, 0.0, "推導：綜合損益歸屬非控制權益為0", "（補）非控制權益淨利為0")
        elif pd.notna(iat[k]) and pd.notna(n_) and not src_ni_derived and (pd.notna(form[k]) or no_form[k]):
            add(k, NCI, iat[k] - n_ - form0[k], "推導：本期淨利−歸母淨利", "（補）本期淨利−淨利歸屬於母公司業主")
        elif (k[0], k[1], NCI) in ebv:
            r = ebv[(k[0], k[1], NCI)]
            add(k, NCI, float(r.value), "財報電子書", f"（補）財報電子書 {r.file} 第{r.page}頁")
        else:
            add(k, NCI, np.nan, "資料不足", "（補）資料不足")
    log["backfill"] = stat
    log["need_ni"], log["need_nci"] = int(len(need_ni)), int(len(need_nci))
    pd.DataFrame(rows).to_csv(os.path.join(os.environ.get("OUT", "out"), "backfill_rows.csv"), index=False)
    return pd.concat([df, pd.DataFrame(rows)], ignore_index=True)


def ebook_targets(df):
    """電子書要抓的股季：歸母淨利或非控制權益淨利最後落在「資料不足」者。"""
    b = df[(df["src"] == "資料不足")]
    return b[["stock_id", "date", "type"]].sort_values(["stock_id", "date"])


def check_whitelist(df):
    o = df[df["src"] == "FinMind"][["dataset", "type", "origin_name"]].drop_duplicates()
    if os.environ.get("WHITELIST") == "build":
        o.sort_values(list(o.columns)).to_csv(WL, index=False)
        return []
    wl = pd.read_csv(WL)
    k = set(map(tuple, wl.itertuples(index=False)))
    return [tuple(x) for x in o.itertuples(index=False) if tuple(x) not in k]


def main():
    out = os.environ.get("OUT", "out"); os.makedirs(out, exist_ok=True)
    df = pd.read_parquet(os.environ["SRC"])
    log = {"src_rows": int(len(df))}
    df = remap(df, log)
    df = backfill(df, log)
    bad = check_whitelist(df)
    if bad:
        log["whitelist_new"] = [list(x) for x in bad]
        json.dump(log, open(os.path.join(out, "fin_fix_log.json"), "w"), ensure_ascii=False, indent=1)
        print("白名單外的科目名稱：", bad); sys.exit(3)
    df = df.sort_values(["stock_id", "date", "dataset", "type"]).reset_index(drop=True)
    df.to_parquet(os.path.join(out, "financials.parquet"), index=False)
    ebook_targets(df).to_csv(os.path.join(out, "ebook_targets.csv"), index=False)
    log["out_rows"] = int(len(df))
    json.dump(log, open(os.path.join(out, "fin_fix_log.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(log, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
