"""可轉債轉換價查詢（cb 組）。

conv_price_asof(conv, issues, bond_id, date)：回傳「在 date 當天可用」的轉換價。
一筆調整要同時滿足兩個條件才算可用（Eve 2026-11-12）：
  1. 生效日 effective ≤ date；
  2. 可得日 available_date（申報日）早於 date 的「日曆日」—— 申報當天（不論幾點）都不可用，最早次一日。
都不符時回傳發行時轉換價 conv_price_issue（官方欄）。
發行日 issue_date 未知、或 date 早於發行日、或晚於到期／下櫃日時，一律回傳 None（還沒發行或已不存在，不得借用其他世代的價格）。
只讀 cb_conv_price（已歸屬的調整）；隔離表 cb_conv_price_quarantine 不參與。
"""
import pandas as pd


def conv_price_asof(conv, issues, bond_id, date, fallback=True):
    ts = pd.Timestamp(date)
    day = ts.normalize()
    row = issues.loc[issues["bond_id"] == bond_id]
    if row.empty:
        return None
    iss = pd.to_datetime(row["issue_date"].iloc[0])
    end = pd.to_datetime(row["delist_date"].iloc[0]) if pd.notna(row["delist_date"].iloc[0]) else pd.to_datetime(row["maturity_date"].iloc[0])
    if pd.isna(iss) or day < iss.normalize() or (pd.notna(end) and day > end.normalize()):
        return None
    c = conv[(conv["bond_id"] == bond_id) & (conv["effective"].dt.normalize() <= day)
             & (conv["available_date"].dt.normalize() < day)]
    if len(c):
        return float(c.sort_values(["effective", "available_date"]).iloc[-1]["price_after"])
    if not fallback:
        return None
    v = pd.to_numeric(row["conv_price_issue"], errors="coerce").dropna()
    return float(v.iloc[0]) if len(v) else None
