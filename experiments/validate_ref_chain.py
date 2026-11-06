"""退回-69：用櫃買官方次日漲跌停驗證「基準價鏈＋升降單位＋特殊期間」規則；通過後同一規則才用於證交所。
用法：RAW_DIR=raw EX=official_exright.parquet python experiments/validate_ref_chain.py"""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework.elon_tools import limit_prices, security_kind, next_base
from data_layer.market_history import official_quotes, tpex_official_limits

q = official_quotes("上櫃")
ex = pd.read_parquet(os.environ["EX"])[["date", "stock_id", "ref"]].dropna()
q = q.merge(ex, on=["date", "stock_id"], how="left").sort_values(["stock_id", "date"])
off = tpex_official_limits()
off = off[~off["no_limit"] & (off["up"] > 0)]
recs = []
for sid, g in q.groupby("stock_id", sort=False):
    base = None
    for d, c, b, a, r in zip(g["date"], g["close_off"], g["bid"], g["ask"], g["ref"]):
        if r == r and r is not None:
            base = r                      # 官方除權息參考價
        recs.append((sid, d, base))
        base = next_base(base, c, b, a, d + pd.Timedelta(days=1))
ch = pd.DataFrame(recs, columns=["stock_id", "date", "base"])
m = off.merge(ch, on=["stock_id", "date"], how="inner").dropna(subset=["base"])
m = m.merge(ex.rename(columns={"ref": "exref"}), on=["date", "stock_id"], how="left")
m = m[m["exref"].isna()]                  # 除權息日官方另有規則（現增除權等），不在此驗證
lp = [limit_prices(b, d, security_kind(s)) for b, d, s in zip(m["base"], m["date"], m["stock_id"])]
m["ru"], m["rd"] = [x[0] for x in lp], [x[1] for x in lp]
m["ok"] = ((m["ru"] - m["up"]).abs() < 1e-6) & ((m["rd"] - m["dn"]).abs() < 1e-6)
m["yr"] = m["date"].dt.year
print(m.groupby("yr")["ok"].agg(["size", "mean"]).to_string())
print("total", len(m), "mismatch", int((~m["ok"]).sum()))
bad = m[~m["ok"]]
bad.to_parquet(os.environ.get("OUT", "/tmp") + "/chain_bad.parquet")
print(bad[["date", "stock_id", "base", "up", "dn", "ru", "rd"]].sample(min(20, len(bad)), random_state=0).to_string())
