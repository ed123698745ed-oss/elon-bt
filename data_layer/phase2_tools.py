"""第二期資料層的使用工具：證券類型、平盤下禁空規則期間、處置區間合併。

證券類型 sec_kind 只依「代號格式」判斷（官方各表沒有證券類型欄），未能歸類者標「其他」，不猜。
"""
import re

import pandas as pd

# 平盤下得融（借）券賣出名單「前一交易日收盤價」門檻改為跌幅達 3.5% 的期間（名單日期，含頭尾）。
# 依據：櫃買官方名單欄位標題改為「跌幅達3.5%以上」的 134 個交易日（build 時逐日核對），加上 2023-02-23：
#   金管會 2023-02-23 例行記者會宣布「即日起」取消，當日名單仍依前一日跌幅 3.5% 加註（上市 27 檔、上櫃 30 檔星號為非跌停而跌幅≥3.5%），
#   該日交易時段措施仍有效；櫃買當日標題已先改回「跌停」（標題落後，列於 HEADER_LAG_DAYS）。Eve 退回 c2 指出。
# 證交所標題未改字，但星號數量同期暴增（平均每日約 2→27 檔），且金管會措施同時適用上市與上櫃，故兩市場同期採用。
DOWNTICK_35_PERIODS = [(pd.Timestamp("2020-03-20"), pd.Timestamp("2020-06-09")),
                       (pd.Timestamp("2022-10-24"), pd.Timestamp("2023-02-23"))]
HEADER_LAG_DAYS = {pd.Timestamp("2023-02-23")}   # 櫃買標題與規則期間不一致、已逐筆核實的日期
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


_CN = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_num(t):
    """中文數字（一百零九、二十七、十）→ int；阿拉伯／全形數字亦可。"""
    t = t.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if t.isdigit():
        return int(t)
    total, cur = 0, 0
    for ch in t:
        if ch in _CN:
            cur = _CN[ch]
        elif ch == "十":
            total += (cur or 1) * 10
            cur = 0
        elif ch == "百":
            total += (cur or 1) * 100
            cur = 0
        else:
            return None
    return total + cur


_NUM = r"[0-9０-９零〇一二三四五六七八九十百]+"
_RANGE = re.compile(rf"(?:民國)?({_NUM})年({_NUM})月({_NUM})日(?:起)?至(?:民國)?(?:({_NUM})年)?({_NUM})月({_NUM})日")


def detail_period(text):
    """從處置公告內文取出處置期間（起、迄）；取不到回傳 (None, None)。只取第一個『…年…月…日（起）至…月…日』區間。"""
    m = _RANGE.search(str(text))
    if not m:
        return None, None
    y, mo, d, y2, mo2, d2 = [(_cn_num(g) if g else None) for g in m.groups()]
    try:
        s = pd.Timestamp(y + 1911, mo, d)
        e = pd.Timestamp((y2 or y) + 1911, mo2, d2)
    except (TypeError, ValueError):
        return None, None
    if e < s and y2 is None:
        e = pd.Timestamp(y + 1912, mo2, d2)
    return s, e


def disposal_intervals(sv: pd.DataFrame, exclude_flags=("取消／恢復公告", "起訖同日"), max_days=None, conflict="union") -> pd.DataFrame:
    """把處置公告合併成每檔股票互不重疊的處置區間（含頭尾的日曆日，使用時再對交易日曆展開）。
    預設排除「取消／恢復公告」與「起訖同日」列（它們不是新的處置期間）；max_days 給數字則排除期間更長者。
    conflict：表格日期與公告內文日期不符（period_flag 含「表格與內文日期不符」）時的取法：
      "union"（預設）＝取兩者聯集（最早起日至最晚迄日，避免提早解除或晚開始而漏掉處置）；"table"／"detail"＝只取其一；"drop"＝排除。
    注意：取消公告對原處置迄日的影響本層不套用（官方公告內文需人工核對）。"""
    p = sv[(sv["kind"] == "處置")].dropna(subset=["start", "end"]).copy()
    for f in exclude_flags:
        p = p[~p["period_flag"].str.contains(f, regex=False)]
    if max_days is not None:
        p = p[p["period_days"] <= max_days]
    if "detail_start" in p.columns:
        bad = p["period_flag"].str.contains("表格與內文日期不符", regex=False)
        if conflict == "drop":
            p = p[~bad]
        elif conflict == "detail":
            p.loc[bad, "start"], p.loc[bad, "end"] = p.loc[bad, "detail_start"], p.loc[bad, "detail_end"]
        elif conflict == "union":
            p.loc[bad, "start"] = p.loc[bad, ["start", "detail_start"]].min(axis=1)
            p.loc[bad, "end"] = p.loc[bad, ["end", "detail_end"]].max(axis=1)
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
