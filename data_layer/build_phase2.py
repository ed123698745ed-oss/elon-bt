"""第二期整理：index_daily（加權／櫃買開高低收、加權報酬指數）與 surveillance（處置、注意公告）。

用法：RAW=raw OUT=out python data_layer/build_phase2.py
原則：只轉換官方原始檔；解析不到的欄位留空並在 parse_note 註明，不推估。
可得時點：處置與注意以「公布日期」收盤後為可得（盤後公告），策略最早於次一交易日使用。
"""
import glob, json, os, re
import pandas as pd

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
            for c, lab in (("start", "起日"), ("end", "迄日")):
                if CAL and pd.notna(r[c]) and r[c] <= CAL_MAX and r[c] not in CAL:
                    n.append(f"處置{lab}非交易日（官方規定遇休市順延，實際日期未核）")
        notes.append("；".join(n))
    df["parse_note"] = notes
    df["count"] = pd.to_numeric(df["count"], errors="coerce")
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
    df.loc[df.effective.isna(), "parse_note"] = "次一營業日超出交易日曆"
    df.loc[df.unknown_codes != "", "parse_note"] = "註記含官方說明未列符號，資料不足"
    return df


def downtick_list():
    """平盤下得融（借）券賣出名單：在名單內＝當日可平盤下放空（另看三個 * 欄）。"""
    out = []
    for src, market in (("twse_mark", "上市"), ("tpex_mark", "上櫃")):
        for key, j in _load(src):
            d = pd.Timestamp(key)
            rows = j.get("data") if src == "twse_mark" else j["tables"][0].get("data")
            for r in rows or []:
                if len(r) < 5:
                    continue
                f = [str(x).strip() == "*" for x in r[2:5]]
                out.append((d, market, str(r[0]).strip(), *f))
    return pd.DataFrame(out, columns=["date", "market", "code", "short_susp", "sbl_susp", "downtick_ban_prev_limit"])


def _cal():
    p = os.environ.get("CAL", "jobs/trading_days.txt")
    if not os.path.exists(p):
        return set(), None
    ds = set(pd.to_datetime(open(p).read().split()))
    return ds, max(ds)


CAL, CAL_MAX = _cal()


def main():
    os.makedirs(OUT, exist_ok=True)
    ix = index_daily()
    sv = surveillance()
    ix.to_parquet(os.path.join(OUT, "index_daily.parquet"), index=False)
    mf = margin_flags()
    mf.to_parquet(os.path.join(OUT, "margin_flags.parquet"), index=False)
    dl = downtick_list()
    dl.to_parquet(os.path.join(OUT, "downtick_list.parquet"), index=False)
    print("margin_flags", len(mf), mf.groupby("market").data_date.agg(["min", "max", "nunique"]).to_string())
    print(mf[["stop_fin", "stop_short", "stop_trade", "short_alloc"]].sum().to_string())
    print("margin parse_note", mf.parse_note.value_counts().to_string())
    print("downtick_list", len(dl), dl.groupby("market").date.agg(["min", "max", "nunique"]).to_string())
    print(dl[["short_susp", "sbl_susp", "downtick_ban_prev_limit"]].sum().to_string())
    sv.to_parquet(os.path.join(OUT, "surveillance.parquet"), index=False)
    print("index_daily", len(ix), ix["date"].min().date(), ix["date"].max().date())
    print(ix.notna().sum().to_string())
    print("surveillance", sv.groupby(["market", "kind"]).size().to_string())
    print("parse_note", sv["parse_note"].value_counts().to_string())


if __name__ == "__main__":
    main()
