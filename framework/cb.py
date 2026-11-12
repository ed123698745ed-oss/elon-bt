"""可轉債轉換價查詢（cb 組）。

conv_price_asof(conv, issues, bond_id, date)：回傳「在 date 當天可用」的轉換價。
一筆調整要同時滿足兩個條件才算可用（Eve 2026-11-12）：
  1. 生效日 effective ≤ date；
  2. 可得日 available_date（申報日）< date —— 申報當天盤後才公開，最早次一交易日使用。
都不符時回傳發行時轉換價 conv_price_issue（官方欄）；沒有則 None。
只讀 cb_conv_price（已歸屬的調整）；隔離表 cb_conv_price_quarantine 不參與。
"""
import pandas as pd


def conv_price_asof(conv, issues, bond_id, date, fallback=True):
    date = pd.Timestamp(date)
    c = conv[(conv["bond_id"] == bond_id) & (conv["effective"] <= date) & (conv["available_date"] < date)]
    if len(c):
        return float(c.sort_values(["effective", "available_date"]).iloc[-1]["price_after"])
    if not fallback:
        return None
    r = issues.loc[issues["bond_id"] == bond_id, "conv_price_issue"]
    v = pd.to_numeric(r, errors="coerce").dropna()
    return float(v.iloc[0]) if len(v) else None
