"""退回-69：漲跌停推算規則對官方值的全面比對。
(a) 官方除權息表的漲跌停（含 2005-03-01 前）；(b) 櫃買每日收盤行情「次日漲停價／次日跌停價」（2007-07 起，適用次一交易日）。
用法：RAW_DIR=... DK=daily_k.parquet python experiments/validate_limits.py
"""
import glob, json, os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework.elon_tools import limit_prices, security_kind
from data_layer.market_history import tpex_official_limits

dk = pd.read_parquet(os.environ["DK"], columns=["date", "stock_id", "market", "ref_price", "prev_close", "limit_src", "no_trade"])
ex = pd.read_parquet(os.environ["EX"])


def rule(df, refcol):
    u, d = [], []
    for r, dt, sid in zip(df[refcol], df["date"], df["stock_id"]):
        a, b = limit_prices(r, dt, security_kind(sid))
        u.append(a); d.append(b)
    return pd.Series(u, index=df.index), pd.Series(d, index=df.index)


def report(name, df, upc, dnc):
    df = df.copy()
    df["ru"], df["rd"] = rule(df, "ref")
    df["ok"] = ((df["ru"] - df[upc]).abs() < 1e-6) & ((df["rd"] - df[dnc]).abs() < 1e-6)
    df["era"] = pd.cut(df["date"], [pd.Timestamp("1990-01-01"), pd.Timestamp("2005-03-01"), pd.Timestamp("2015-06-01"), pd.Timestamp("2100-01-01")],
                       labels=["2005-03前", "2005-03～2015-05", "2015-06後"], right=False)
    df["kind"] = df["stock_id"].map(security_kind)
    g = df.groupby(["era", "kind"], observed=True)["ok"].agg(["size", "sum"])
    g["mismatch"] = g["size"] - g["sum"]
    print(f"== {name}\n{g.to_string()}")
    return df[~df["ok"]]


a = ex.rename(columns={"limit_up": "up", "limit_down": "dn"}).dropna(subset=["ref", "up", "dn"])
a = a[(a["up"] < 9999) & (a["ref"] > 0)]
bad_a = report("(a) 官方除權息表", a, "up", "dn")
off = tpex_official_limits()
b = off.merge(dk[["date", "stock_id", "prev_close", "limit_src"]], on=["date", "stock_id"], how="inner")
b = b[(b["limit_src"] == "規則") & b["prev_close"].notna() & (b["up"] < 9999)].rename(columns={"prev_close": "ref"})
bad_b = report("(b) 櫃買次日漲跌停（規則列）", b, "up", "dn")
out = os.environ.get("OUT", ".")
bad_a.to_csv(f"{out}/limit_mismatch_exright.csv", index=False)
bad_b.to_csv(f"{out}/limit_mismatch_tpex_official.csv", index=False)
print("mismatch samples (b):\n", bad_b.head(15).to_string())
