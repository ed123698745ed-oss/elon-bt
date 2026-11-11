"""068 合併組挑選協定（策略卡 4.3「最多再做一次合併組」；2026-11-11 於看任何變體報酬前寫定）。

家族（一次改一個參數族）：回看天數｛V-L20、V-L120｝、選股檔數｛V-TOP10｝、選股順序｛V-FILT1ST｝、
獲利濾網｛V-ROE8、V-REV｝、流動性｛V-LIQ0.5億、V-LIQ2億｝、換股頻率｛V-2W｝、大盤濾網｛V-MKT｝。
合格條件：樣本內平均報酬 > M1 樣本內平均報酬，且樣本內聚合 p < 0.05。
排序指標：樣本內平均報酬（逐筆）由大到小；平手取聚合 p 較小者，再平手取家族內列序在前者。
每族取合格者中第一名；沒有合格者的族沿用原版設定。合格族數 < 2 時不做合併組（合併組等同單一變體）。
V-ROE8 被選入時，合併組自 2014-04 起（同 V-ROE8）。
"""
import pandas as pd

FAMILIES = {
    "L": {"V-L20": dict(L=20), "V-L120": dict(L=120)},
    "top": {"V-TOP10": dict(top=10)},
    "order": {"V-FILT1ST": dict(filt_first=True)},
    "filt": {"V-ROE8": dict(filt="roe4"), "V-REV": dict(filt="rev")},
    "liq": {"V-LIQ0.5億": dict(liq=5e7), "V-LIQ2億": dict(liq=2e8)},
    "freq": {"V-2W": dict(biweekly=True)},
    "mkt": {"V-MKT": dict(mkt=True)},
}


def pick(tt):
    """tt：card_ten.pkl（樣本內）。回傳 (合併組參數 dict 或 None, 選入清單, 說明)。"""
    t = tt.set_index("combo")
    base = t.loc["M1", "平均報酬"]
    params, chosen = dict(L=60, top=30, filt="roe"), []
    for fam, opts in FAMILIES.items():
        q = []
        for k, (c, p) in enumerate(opts.items()):
            if c in t.index and t.loc[c, "平均報酬"] > base and t.loc[c, "聚合p"] < 0.05:
                q.append((-t.loc[c, "平均報酬"], t.loc[c, "聚合p"], k, c, p))
        if q:
            q.sort()
            _, _, _, c, p = q[0]
            chosen.append(c); params.update(p)
    if len(chosen) < 2:
        return None, chosen, f"合格族數 {len(chosen)} < 2，不做合併組"
    if params.get("filt") == "roe4":
        from sim068 import ROE4_START
        params["start"] = ROE4_START
    return params, chosen, "合併：" + "＋".join(chosen)
