"""068 R01 敏感度測試：格點完全照 freeze_068_R01.md 第 5 節（看結果前寫定，不得增減）。
每格沿用 simR01 的同一套規則，只改兩個參數；輸出 sensR01_trades.pkl（含 combo＝"<組合>|<參數一>|<參數二>"）。
"""
import pickle, sys
import pandas as pd
import simR01 as S

LN = [("L", 40), ("L", 60), ("L", 90)]
N3 = [("top", 20), ("top", 30), ("top", 45)]
L_ = [40, 60, 90]
GRIDS = {   # 組合 -> (參數一名稱, 值列, 參數二名稱, 值列)
    "M0": ("L", L_, "top", [20, 30, 45]),
    "M1": ("L", L_, "top", [20, 30, 45]),
    "M1-同期": ("L", L_, "top", [20, 30, 45]),
    "V-FILT1ST": ("L", L_, "top", [20, 30, 45]),
    "V-REV": ("L", L_, "top", [20, 30, 45]),
    "V-2W": ("L", L_, "top", [20, 30, 45]),
    "E-M1-ADJ": ("L", L_, "top", [20, 30, 45]),
    "V-L20": ("L", [10, 20, 40], "top", [20, 30, 45]),
    "V-L120": ("L", [80, 120, 180], "top", [20, 30, 45]),
    "V-TOP10": ("L", L_, "top", [5, 10, 20]),
    "V-MERGE": ("L", [80, 120, 180], "top", [5, 10, 20]),
    "V-ROE8": ("roe4_thr", [0.05, 0.08, 0.12], "L", L_),
    "V-LIQ0.5億": ("liq", [3e7, 5e7, 1e8], "L", L_),
    "V-LIQ2億": ("liq", [1e8, 2e8, 4e8], "L", L_),
    "V-MKT": ("mkt_w", [10, 20, 40], "L", L_),
    "E-BUF50": ("buffer", [40, 50, 75], "L", L_),
    "E-SKIP20": ("skip", [10, 20, 40], "L", L_),
    "E-STOP15": ("stop", [0.10, 0.15, 0.20], "L", L_),
}
assert len(GRIDS) == 18 and all(len(a) == 3 and len(b) == 3 for _, a, _, b in GRIDS.values())


def fmt(k, v):
    return {"roe4_thr": f"ROE{int(round(v*100))}%", "liq": f"{v/1e8:g}億", "mkt_w": f"MA{v}", "buffer": f"前{v}",
            "skip": f"跳{v}", "stop": f"停損{int(round(v*100))}%", "L": f"L{v}", "top": f"N{v}"}[k]


if __name__ == "__main__":
    base = {**S.COMBOS, **S.ETESTS}
    rows, meta = [], []
    for name, (k1, v1s, k2, v2s) in GRIDS.items():
        for v1 in v1s:
            for v2 in v2s:
                p = dict(base[name]); p[k1] = v1; p[k2] = v2
                cid = f"{name}|{fmt(k1, v1)}|{fmt(k2, v2)}"
                r, _, _ = S.run(cid, p)
                fr = S.finalize(r, name.startswith("E-"))
                rows += fr
                is_center = (base[name].get(k1, {"L": 60, "top": 30, "roe4_thr": 0.08, "mkt_w": 20}.get(k1)) == v1 and
                             base[name].get(k2, {"L": 60, "top": 30, "roe4_thr": 0.08, "mkt_w": 20}.get(k2)) == v2)
                meta.append(dict(cid=cid, combo=name, p1=k1, v1=v1, p2=k2, v2=v2, center=is_center))
        print(name, "done", flush=True)
    pd.DataFrame(rows).to_pickle("sensR01_trades.pkl")
    pd.DataFrame(meta).to_pickle("sensR01_meta.pkl")
