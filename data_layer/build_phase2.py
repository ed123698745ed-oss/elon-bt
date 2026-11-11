"""第二期整理：index_daily（加權／櫃買開高低收、加權報酬指數）與 surveillance（處置、注意公告）。

用法：RAW=raw OUT=out python data_layer/build_phase2.py
原則：只轉換官方原始檔；解析不到的欄位留空並在 parse_note 註明，不推估。
可得時點：處置與注意以「公布日期」收盤後為可得（盤後公告），策略最早於次一交易日使用。
"""
import glob, json, os, re
import pandas as pd

try:
    from data_layer.phase2_tools import ban_rule, sec_kind, sec_kind_series, RULE_DROP35, HEADER_LAG_DAYS, detail_period
except ImportError:      # 直接以 python data_layer/build_phase2.py 執行
    from phase2_tools import ban_rule, sec_kind, sec_kind_series, RULE_DROP35, HEADER_LAG_DAYS, detail_period

RAW = os.environ.get("RAW", "raw")
OUT = os.environ.get("OUT", "out")
P2 = os.path.join(RAW, "phase2")


def roc_date(s):
    """'113/01/02'、'113.01.02'、'2024/01/02'、'092年01月02日' → Timestamp；失敗回 NaT。"""
    if s is None:
        return pd.NaT
    s = str(s).strip()
    m = re.match(r"^(\d{2,4})[/.年](\d{1,2})[/.月](\d{1,2})", s)
    if not m:
        return pd.NaT
    y, mo, d = map(int, m.groups())
    if y < 1911:
        y += 1911
    try:
        return pd.Timestamp(y, mo, d)
    except ValueError:
        return pd.NaT


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return float("nan")


def _load(src):
    for f in sorted(glob.glob(os.path.join(P2, src, "*.json"))):
        yield os.path.basename(f)[:-5], json.load(open(f, encoding="utf-8"))


# ---------- index_daily ----------
def index_daily():
    tw = {}
    for _, j in _load("twse_ix"):
        for r in j.get("data") or []:
            d = roc_date(r[0])
            tw[d] = dict(taiex_open=num(r[1]), taiex_high=num(r[2]), taiex_low=num(r[3]), taiex_close=num(r[4]))
    for _, j in _load("twse_tri"):
        for r in j.get("data") or []:
            tw.setdefault(roc_date(r[0]), {})["taiex_tri_close"] = num(r[1])
    for _, j in _load("tpex_ix"):
        for r in (j["tables"][0].get("data") or []):
            tw.setdefault(roc_date(r[0]), {}).update(tpex_open=num(r[1]), tpex_high=num(r[2]), tpex_low=num(r[3]), tpex_close=num(r[4]))
    df = pd.DataFrame.from_dict(tw, orient="index").sort_index()
    df.index.name = "date"
    if df.index.isna().any():
        raise RuntimeError("index_daily 有無法解析的日期")
    cols = ["taiex_open", "taiex_high", "taiex_low", "taiex_close", "taiex_tri_close",
            "tpex_open", "tpex_high", "tpex_low", "tpex_close"]
    return df.reindex(columns=cols).reset_index()


# ---------- surveillance ----------
CN = {"零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn_num(s):
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if s.isdigit():
        return int(s)
    if "十" in s:
        a, _, b = s.partition("十")
        return (CN.get(a, 1) if a else 1) * 10 + (CN.get(b, 0) if b else 0)
    return CN.get(s)


def match_minutes(text):
    m = re.search(r"約每([0-9０-９一二三四五六七八九十兩]+)分鐘", text or "")
    return cn_num(m.group(1)) if m else None


def full_prepay(text):
    t = text or ""
    if "收取全部之買進價金或賣出證券" in t or "收足全部款券" in t or "收取全部" in t:
        return "全部" if not re.search(r"單筆達|多筆累積達", t) else "超過門檻部分"
    return ""


def split_period(s):
    parts = re.split(r"[～~至]", str(s or ""))
    if len(parts) != 2:
        return pd.NaT, pd.NaT
    return roc_date(parts[0]), roc_date(parts[1])


def clean_name(s):
    return re.sub(r"\(\.\./.*\)$", "", str(s or "")).strip()


def surveillance():
    rows = []
    for _, j in _load("twse_punish"):
        for r in j.get("data") or []:
            st, en = split_period(r[6])
            text = str(r[8] or "")
            rows.append(dict(market="上市", kind="處置", announce=roc_date(r[1]), code=str(r[2]).strip(),
                             name=clean_name(r[3]), count=r[4], reason=str(r[5]).strip(), start=st, end=en,
                             measure=str(r[7]).strip(), match_min=match_minutes(text), prepay=full_prepay(text + str(r[7])), detail=text))
    for _, j in _load("tpex_disposal"):
        for r in j["tables"][0].get("data") or []:
            if not str(r[2]).strip():          # 「本日無處置資料」等佔位列
                continue
            st, en = split_period(r[5])
            text = str(r[8] or "")
            rows.append(dict(market="上櫃", kind="處置", announce=roc_date(r[1]), code=str(r[2]).strip(),
                             name=clean_name(r[3]), count=r[4], reason=str(r[6]).strip(), start=st, end=en,
                             measure=str(r[7]).strip(), match_min=match_minutes(text), prepay=full_prepay(text), detail=text))
    for _, j in _load("twse_notice"):
        for r in j.get("data") or []:
            rows.append(dict(market="上市", kind="注意", announce=roc_date(r[5]), code=str(r[1]).strip(),
                             name=clean_name(r[2]), count=r[3], reason=str(r[4]).strip(), detail=str(r[4])))
    for _, j in _load("tpex_attention"):
        for r in j["tables"][0].get("data") or []:
            if not str(r[1]).strip():
                continue
            rows.append(dict(market="上櫃", kind="注意", announce=roc_date(r[5]), code=str(r[1]).strip(),
                             name=clean_name(r[2]), count=r[3], reason=str(r[4]).strip(), detail=str(r[4])))
    df = pd.DataFrame(rows)
    # 跨年處置會出現在兩個年度查詢檔；同一則公告去重
    df = df.drop_duplicates(subset=["market", "kind", "announce", "code", "start", "reason"]).reset_index(drop=True)
    notes = []
    for _, r in df.iterrows():
        n = []
        if pd.isna(r["announce"]):
            n.append("公布日無法解析")
        if r["kind"] == "處置":
            if pd.isna(r["start"]) or pd.isna(r["end"]):
                n.append("處置起迄無法解析")
            if re.search(r"取消(受託|對該)", r["detail"]):
                n.append("公告內容為取消措施，起迄與措施需人工核對")
            if pd.isna(r["match_min"]) and "撮合" in r["detail"] and "分盤" not in r["detail"]:
                n.append("撮合間隔未解析")
            if CAL and pd.notna(r["start"]) and pd.notna(r["announce"]) and r["start"] <= CAL_MAX:
                gap = CAL_IDX.get(r["start"], -99) - CAL_IDX.get(r["announce"], -999) if r["announce"] in CAL_IDX else None
                if gap is not None and not (0 <= gap <= 3):
                    n.append("處置起日距公告逾 3 個交易日（原公告待核）")
            for c, lab in (("start", "起日"), ("end", "迄日")):
                if CAL and pd.notna(r[c]) and r[c] <= CAL_MAX and r[c] not in CAL:
                    n.append(f"處置{lab}非交易日（官方規定遇休市順延，實際日期未核）")
        notes.append("；".join(n))
    df["parse_note"] = notes
    df["count"] = pd.to_numeric(df["count"], errors="coerce")
    df["sec_kind"] = sec_kind_series(df["code"])
    # 處置期間可靠性：只標記、不改值、不推估
    df["period_days"] = (df["end"] - df["start"]).dt.days + 1
    cancel = df["detail"].str.contains("取消|恢復", regex=True) & (df["kind"] == "處置")
    dp = [detail_period(t) if k == "處置" else (None, None) for t, k in zip(df["detail"], df["kind"])]
    df["detail_start"] = pd.to_datetime([a for a, _ in dp])
    df["detail_end"] = pd.to_datetime([b for _, b in dp])
    conflict = df["detail_start"].notna() & ((df["detail_start"] != df["start"]) | (df["detail_end"] != df["end"]))
    flags = []
    for c, same, long_, cf in zip(cancel, df["end"] == df["start"], df["period_days"] > 60, conflict):
        f = []
        if cf:
            f.append("表格與內文日期不符")
        if c:
            f.append("取消／恢復公告")
        if same:
            f.append("起訖同日")
        if long_:
            f.append("期間逾60日")
        flags.append("；".join(f))
    df["period_flag"] = flags
    df.loc[df["kind"] != "處置", "period_flag"] = ""
    # 同市場同代號與前一筆處置重疊（處置延長的正常現象，使用前須合併區間）
    df = df.sort_values(["market", "code", "kind", "start", "announce"], kind="stable").reset_index(drop=True)
    prev_end = df.groupby(["market", "code", "kind"])["end"].transform(lambda x: x.cummax().shift())
    df["overlap_prev"] = (df["kind"] == "處置") & df["start"].notna() & prev_end.notna() & (df["start"] <= prev_end)
    return df


# ---------- 放空限制：融資融券註記（適用次一營業日）與平盤下名單 ----------
TWSE_CODES = set("OX@%!")
TPEX_CODES = set("OX@%!*ABCD0123456789")


def _next_day_map():
    ds = sorted(CAL)
    return {a: b for a, b in zip(ds, ds[1:])}


def margin_flags():
    """每列＝某生效日某證券的融資融券狀態。註記在 D 日資料、適用 D+1（官方：備註欄係表明成交日次一營業日狀況）。"""
    nxt = _next_day_map()
    out = []
    for src, market, codes in (("twse_margin", "上市", TWSE_CODES), ("tpex_margin", "上櫃", TPEX_CODES)):
        for key, j in _load(src):
            d = pd.Timestamp(key)
            eff = nxt.get(d)
            if src == "twse_margin":
                rows = [r for t in j.get("tables", []) if "融資融券彙總" in (t.get("title") or "") for r in (t.get("data") or [])]
            else:
                rows = [r for r in j["tables"][0].get("data") or [] if len(r) > 1]
            for r in rows:
                note = str(r[-1])
                chars = set(note.replace(" ", "").replace(",", ""))
                out.append((d, eff, market, str(r[0]).strip(), "O" in chars, "X" in chars, "!" in chars,
                            "%" in chars, "@" in chars, note.strip(), "".join(sorted(chars - codes))))
    df = pd.DataFrame(out, columns=["data_date", "effective", "market", "code", "stop_fin", "stop_short",
                                    "stop_trade", "short_alloc", "fin_alloc", "note_raw", "unknown_codes"])
    df["parse_note"] = ""
    df["sec_kind"] = sec_kind_series(df["code"])
    df.loc[df.effective.isna(), "parse_note"] = "次一營業日超出交易日曆"
    df.loc[df.unknown_codes != "", "parse_note"] = "註記含官方說明未列符號，資料不足"
    return df


MARK_START = {"上市": pd.Timestamp("2013-09-23"), "上櫃": pd.Timestamp("2013-09-18")}   # 官方名單起日


def _mark_rows(src):
    for key, j in _load(src):
        t = j if src == "twse_mark" else j["tables"][0]
        header = (t.get("fields") or [""])[-1]
        yield pd.Timestamp(key), [r for r in (t.get("data") or []) if len(r) >= 5], header


def downtick_list():
    """平盤下得融（借）券賣出名單：在名單內＝當日該證券受平盤下限制（看 short_susp／sbl_susp／downtick_ban_prev_limit 三個 * 欄）。
    downtick_ban_prev_limit 的意義隨期間改變，以 ban_rule 標明：「跌停」＝前一交易日收盤跌停；「跌幅達3.5%」＝前一交易日收盤跌幅達 3.5% 以上；
    「全面禁止」＝2015-08-24～09-18 全面禁止平盤下放空（所有證券都加註）。各期語意以 experiments/validate_ban_rule.py 逐日對照前日行情驗證。"""
    out = []
    for src, market in (("twse_mark", "上市"), ("tpex_mark", "上櫃")):
        for d, rows, header in _mark_rows(src):
            rule = ban_rule(d)
            if src == "tpex_mark" and (("3.5%" in header) != (rule == RULE_DROP35)) and d not in HEADER_LAG_DAYS:
                raise RuntimeError(f"櫃買名單欄位標題與規則期間不符 {d.date()}: {header}")
            for r in rows:
                f = [str(x).strip() == "*" for x in r[2:5]]
                out.append((d, market, str(r[0]).strip(), *f, rule))
    df = pd.DataFrame(out, columns=["date", "market", "code", "short_susp", "sbl_susp", "downtick_ban_prev_limit", "ban_rule"])
    df["sec_kind"] = sec_kind_series(df["code"])
    return df


def downtick_coverage():
    """平盤下名單逐日覆蓋狀態：有名單／官方回空表（資料缺口）。
    官方起日後某市場回空表、而另一市場同日有名單者，視為資料缺口（不是當天沒有名單），使用者不得當成『無限制』。"""
    st = {}
    for src, market in (("twse_mark", "上市"), ("tpex_mark", "上櫃")):
        for d, rows, _ in _mark_rows(src):
            st[(market, d)] = len(rows)
    out = []
    for (market, d), n in st.items():
        if d < MARK_START[market]:
            continue
        other = "上櫃" if market == "上市" else "上市"
        if n > 0:
            status = "有名單"
        elif st.get((other, d), 0) > 0:
            status = "資料缺口（官方回空表，另一市場同日有名單）"
        else:
            status = "兩市場皆空（待核）"
        out.append((d, market, n, status))
    return pd.DataFrame(sorted(out), columns=["date", "market", "rows", "status"])


def fulldelivery():
    """變更交易（全額交割）每日名單：名單內＝當日須預收款券。
    上市：證交所 TWT85U（2004-12-24 起），kind＝變更交易。
    上櫃：櫃買 afterTrading/chtm（2008-04-09 起），只收「變更交易」或「屬管理股票」為Ｙ者，kind 記兩者；
          只有「停止交易」為Ｙ者不收。2005-06-01～2008-04-08 上櫃名單不在本表（官方 API 無資料），使用者須另行處理。
    period_auction＝分盤集合競價：上市官方以 ** 表示，2007-11-01 前無此欄為 None（未知），不是 False；上櫃取「分盤交易」欄。
    （上櫃名單加入：Ed 2026-11-11 14:24 選甲，D-070-20261111-1424-1）"""
    out = []
    for key, j in _load("twse_fulldelivery"):
        d = pd.Timestamp(key)
        has_col = len(j.get("fields") or []) > 2
        for r in j.get("data") or []:
            if len(r) < 2:
                continue
            pa = (len(r) > 2 and str(r[2]).strip() == "**") if has_col else None
            out.append((d, "上市", str(r[0]).strip(), clean_name(r[1]), pa, "變更交易"))
    for key, j in _load("tpex_chtm"):
        d = pd.Timestamp(key)
        t = j["tables"][0]
        f = t.get("fields") or []
        ia, ip, im = f.index("變更交易"), f.index("分盤交易"), f.index("屬管理股票")
        for r in t.get("data") or []:
            alt, man = str(r[ia]).strip() == "Ｙ", str(r[im]).strip() == "Ｙ"
            if not (alt or man):
                continue
            kind = "；".join(k for k, v in (("變更交易", alt), ("管理股票", man)) if v)
            out.append((d, "上櫃", str(r[0]).strip(), clean_name(r[1]), str(r[ip]).strip() == "Ｙ", kind))
    df = pd.DataFrame(out, columns=["date", "market", "code", "name", "period_auction", "kind"])
    df["period_auction"] = df["period_auction"].astype("boolean")
    df["sec_kind"] = sec_kind_series(df["code"])
    return df


def _cal():
    p = os.environ.get("CAL", "jobs/trading_days.txt")
    if not os.path.exists(p):
        return set(), None
    ds = set(pd.to_datetime(open(p).read().split()))
    return ds, max(ds)


CAL, CAL_MAX = _cal()
CAL_IDX = {d: i for i, d in enumerate(sorted(CAL))}


def main():
    os.makedirs(OUT, exist_ok=True)
    ix = index_daily()
    sv = surveillance()
    ix.to_parquet(os.path.join(OUT, "index_daily.parquet"), index=False)
    mf = margin_flags()
    mf.to_parquet(os.path.join(OUT, "margin_flags.parquet"), index=False)
    fd = fulldelivery()
    fd.to_parquet(os.path.join(OUT, "fulldelivery.parquet"), index=False)
    if len(fd):
        print("fulldelivery", len(fd), fd.groupby("market")["date"].agg(["min", "max", "nunique", "size"]).to_string(), "分盤", int(fd["period_auction"].fillna(False).sum()), "分盤未知", int(fd["period_auction"].isna().sum()), fd["kind"].value_counts().to_dict())
    dl = downtick_list()
    dl.to_parquet(os.path.join(OUT, "downtick_list.parquet"), index=False)
    dc = downtick_coverage()
    dc.to_parquet(os.path.join(OUT, "downtick_coverage.parquet"), index=False)
    print("downtick_coverage", dc.status.value_counts().to_string())
    print(dc[dc.status != "有名單"].to_string())
    print("ban_rule", dl.groupby("ban_rule").date.nunique().to_string())
    print("margin_flags", len(mf), mf.groupby("market").data_date.agg(["min", "max", "nunique"]).to_string())
    print(mf[["stop_fin", "stop_short", "stop_trade", "short_alloc"]].sum().to_string())
    print("margin parse_note", mf.parse_note.value_counts().to_string())
    print("downtick_list", len(dl), dl.groupby("market").date.agg(["min", "max", "nunique"]).to_string())
    print(dl[["short_susp", "sbl_susp", "downtick_ban_prev_limit"]].sum().to_string())
    sv.to_parquet(os.path.join(OUT, "surveillance.parquet"), index=False)
    cf = sv["period_flag"].str.contains("表格與內文日期不符", regex=False)
    print("內文日期可解析", int(sv.detail_start.notna().sum()), "不符", int(cf.sum()))
    print(sv.loc[cf, ["market", "announce", "code", "start", "end", "detail_start", "detail_end"]].to_string())
    print("period_flag", sv.loc[sv.kind == "處置", "period_flag"].value_counts().to_string(), "overlap_prev", int(sv.overlap_prev.sum()))
    for nm, t in (("surveillance", sv), ("margin_flags", mf), ("downtick_list", dl), ("fulldelivery", fd)):
        if len(t):
            print("sec_kind", nm, t["sec_kind"].value_counts().to_dict())
    print("index_daily", len(ix), ix["date"].min().date(), ix["date"].max().date())
    print(ix.notna().sum().to_string())
    print("surveillance", sv.groupby(["market", "kind"]).size().to_string())
    print("parse_note", sv["parse_note"].value_counts().to_string())


if __name__ == "__main__":
    main()
