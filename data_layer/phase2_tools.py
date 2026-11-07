"""第二期資料層的使用工具：證券類型、平盤下禁空規則期間、處置區間合併。

證券類型 sec_kind 只依「代號格式」判斷（官方各表沒有證券類型欄），未能歸類者標「其他」，不猜。
"""
import re

import pandas as pd

# 平盤下得融（借）券賣出名單「前一交易日收盤價」門檻改為跌幅達 3.5% 的期間（名單日期，含頭尾）。
# 依據：櫃買官方名單欄位標題在這 134 個交易日改為「跌幅達3.5%以上」（build 時逐日核對）；
# 證交所標題未改字，但星號數量同期暴增（平均每日約 2→27 檔），且金管會措施同時適用上市與上櫃，故兩市場同期採用。
DOWNTICK_35_PERIODS = [(pd.Timestamp("2020-03-20"), pd.Timestamp("2020-06-09")),
                       (pd.Timestamp("2022-10-24"), pd.Timestamp("2023-02-22"))]
RULE_LIMITDOWN = "跌停"
RULE_DROP35 = "跌幅達3.5%"


def ban_rule(date) -> str:
    d = pd.Timestamp(date)
    return RULE_DROP35 if any(a <= d <= b for a, b in DOWNTICK_35_PERIODS) else RULE_LIMITDOWN


def sec_kind(code) -> str:
    """依代號格式分類：普通股／特別股／ETF／可轉債／TDR／權證／受益證券／其他。"""
    c = str(code).strip()
    if re.fullmatch(r"00\d{2,4}[A-Z]?", c):
        return "ETF"
    if re.fullmatch(r"01\d{3}T", c):
        return "受益證券"
    if re.fullmatch(r"[1-9]\d{3}", c):
        return "普通股"
    if re.fullmatch(r"[1-9]\d{3}[A-Z]\d?", c):
        return "特別股／字尾代號"
    if re.fullmatch(r"[1-9]\d{4}", c):
        return "可轉債"
    if re.fullmatch(r"91\d{4}", c):
        return "TDR"
    if re.fullmatch(r"(0[3-8]|7[0-3])\d{3,4}[A-Z]?", c):
        return "權證"
    return "其他"


def disposal_intervals(sv: pd.DataFrame, exclude_flags=("取消／恢復公告", "起訖同日"), max_days=None) -> pd.DataFrame:
    """把處置公告合併成每檔股票互不重疊的處置區間（含頭尾的日曆日，使用時再對交易日曆展開）。
    預設排除「取消／恢復公告」與「起訖同日」列（它們不是新的處置期間）；max_days 給數字則排除期間更長者。
    注意：取消公告對原處置迄日的影響本層不套用（官方公告內文需人工核對）。"""
    p = sv[(sv["kind"] == "處置")].dropna(subset=["start", "end"]).copy()
    for f in exclude_flags:
        p = p[~p["period_flag"].str.contains(f, regex=False)]
    if max_days is not None:
        p = p[p["period_days"] <= max_days]
    out = []
    for (m, c), g in p.sort_values(["market", "code", "start"]).groupby(["market", "code"], sort=False):
        cur_s = cur_e = None
        for s, e in zip(g["start"], g["end"]):
            if cur_s is None:
                cur_s, cur_e = s, e
            elif s <= cur_e:
                cur_e = max(cur_e, e)
            else:
                out.append((m, c, cur_s, cur_e))
                cur_s, cur_e = s, e
        if cur_s is not None:
            out.append((m, c, cur_s, cur_e))
    return pd.DataFrame(out, columns=["market", "code", "start", "end"])


def sec_kind_series(codes: pd.Series) -> pd.Series:
    """整欄分類（只對不重複代號計算，千萬列也很快）。"""
    m = {c: sec_kind(c) for c in codes.unique()}
    return codes.map(m)
