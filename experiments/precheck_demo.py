"""交件前檢查逐項實測（退回-67，Eve 要求「每項命中或放行的代表輸入與實際輸出」）。

每一項各跑兩個輸入：乾淨輸入（應放行）與單一缺陷輸入（應命中），
把 checks.precheck.run 的實際輸出原樣寫到 experiments/out_precheck/precheck_demo.txt。
用法：BT_STATS_PATH=… python experiments/precheck_demo.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import date, timedelta

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from framework import stats  # noqa: E402
from framework.core import Calendar, Split, freeze_split  # noqa: E402
from framework.ledger import trade_row  # noqa: E402
from checks.precheck import run  # noqa: E402

BT = os.environ.get("BT_STATS_PATH", "/home/claude/vendor/bt_stats_v1.0.py")
OUT = os.path.join(ROOT, "experiments", "out_precheck")


def cal_(n=600):
    d, out = date(2023, 1, 2), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return Calendar(out)


def base(cal, sp):
    rows = []
    for i in range(12):
        a = 5 + i * 10
        rows.append(trade_row(cal, sp, trade_id=i, combo="H5", is_etest=False, symbol=["2330", "2317", "0050", "00981A"][i % 4],
                              direction="long", info_time=f"{cal.days[a - 1]} 14:30", entry_time=f"{cal.days[a]} 09:00",
                              entry_date=cal.days[a], entry_session="open", entry_px=100, exit_date=cal.days[a + 4],
                              exit_session="close", exit_px=100 + (i % 5) - 2, actions=[], cluster=str(cal.days[a]),
                              price_series_hash=f"h{i}"))
    df = pd.DataFrame(rows)
    df["feature_end"] = df["info_time"].str[:10]
    return df


def reported_ok(df, bt):
    from framework.report import result_table
    raw, _ = result_table(df, by=("combo",), cluster_unit="進場日")
    return raw


def lines(res, item):
    return [f"{l:4} {i}" + (f"：{m}" if m else "") for l, i, m in res if i == item]


def main():
    os.makedirs(OUT, exist_ok=True)
    bt = stats.load(BT)
    cal = cal_()
    sp = Split(cal.days[200], cal.days[270])
    td = tempfile.mkdtemp()
    sp_path = os.path.join(td, "split.json")
    freeze_split(sp, cal, max_hold=5, min_gap=40, path=sp_path)
    att = os.path.join(td, "明細.csv")
    open(att, "w").write("x")
    clean = base(cal, sp)
    rep = reported_ok(clean, bt)
    kw = dict(reported=rep, split_path=sp_path, report_text="依附件 3 第 2 頁", manifest_files=[att], cluster_unit="進場日")

    cases = []

    def case(item, desc_hit, mutate, extra=None):
        hit = clean.copy()
        k = dict(kw)
        mutate(hit, k)
        if extra:
            k.update(extra)
        cases.append((item, desc_hit, run(clean, **kw), run(hit, **k)))

    def m_bt(df, k):
        r = k["reported"].copy(); r["bt_stats版本"] = "自寫 stats"; k["reported"] = r
    case("統計經 bt_stats", "結果表 bt_stats版本 欄改成「自寫 stats」", m_bt)

    def m_stamp(df, k):
        df.loc[0, "ret"] = 0.5; df.loc[0, "ret_by"] = "hand"
    case("持有日與報酬由框架計算", "第 0 筆報酬手改為 0.5、ret_by=hand", m_stamp)

    def m_split(df, k):
        df.loc[3, "sample"] = "樣本外"
    case("樣本內外判定式差異筆數為 0", "第 3 筆（進場在樣本內）明細標成樣本外", m_split)

    def m_man(df, k):
        k["manifest_files"] = [att, os.path.join(td, "缺的附件.xlsx")]
    case("清冊列的附件都在", "清冊多列一個不存在的附件", m_man)

    def m_id(df, k):
        df["symbol"] = df["symbol"].astype(object); df.loc[1, "symbol"] = 2317
    case("代號欄為文字格式", "第 1 筆代號以數字 2317 寫入", m_id)

    def m_hash(df, k):
        df.loc[2, "price_series_hash"] = "h0"
    case("價格序列不重複對到不同代號", "第 2 筆（0050）與第 0 筆（2330）價格序列雜湊相同", m_hash)

    def m_ov(df, k):
        df.loc[4, ["symbol", "entry_date", "entry_session"]] = [df.loc[0, "symbol"], df.loc[0, "exit_date"], "open"]
    case("同股同參數持倉不重疊", "第 4 筆改成與第 0 筆同股、在第 0 筆出場日開盤進場", m_ov)

    def m_clu(df, k):
        r = k["reported"].copy(); r["聚合單位數"] = 8; r["聚合p"] = None; k["reported"] = r
    case("有群聚的組合已列聚合 p", "結果表聚合單位 8 < 樣本 12，聚合p 空白", m_clu)

    def m_feat(df, k):
        df.loc[5, "feature_end"] = str(pd.Timestamp(df.loc[5, "info_time"][:10]) + pd.Timedelta(days=3))[:10]
    case("訊號所用資料不晚於訊號日", "第 5 筆訊號資料最後日期晚於訊號日 3 天", m_feat)

    def m_word(df, k):
        k["report_text"] = "本組時點未違反，皆附樣本外"
    case("斷言字眼須附證據位置", "報告文字含「時點未違反」「皆附樣本外」", m_word)

    def m_few(df, k):
        r = k["reported"].copy(); r["聚合單位數"] = 8; k["reported"] = r
    case("聚合單位少於 10", "結果表聚合單位 8（聚合p 有值）", m_few)

    def m_evt(df, k):
        df["announce_date"] = df["info_time"].str[:10]
        df["event_start"] = df["announce_date"]
        df.loc[6, "event_start"] = str(pd.Timestamp(df.loc[6, "announce_date"]) + pd.Timedelta(days=365))[:10]
    case("事件期間起點晚於公告日 60 天以上", "第 6 筆事件期間起點晚於公告 365 天（退回-52 凱碩型態）", m_evt)

    commit = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    buf = io.StringIO()
    with redirect_stdout(buf):
        print(f"交件前檢查逐項實測｜commit {commit}｜bt_stats {bt.VERSION}｜{stats.current()[1]}")
        print("每項：乾淨輸入的實際輸出 → 單一缺陷輸入的實際輸出（原樣）\n")
        summary = []
        for item, desc, r0, r1 in cases:
            a, b = lines(r0, item), lines(r1, item)
            lv0 = a[0].split()[0] if a else "（未輸出＝放行）"
            lv1 = b[0].split()[0] if b else "（未輸出）"
            print(f"■ {item}\n  缺陷輸入：{desc}")
            print("  乾淨：" + (" | ".join(a) if a else "未輸出（該項只在命中時輸出）"))
            print("  缺陷：" + (" | ".join(b) if b else "未輸出"))
            print()
            summary.append(dict(項目=item, 缺陷輸入=desc, 乾淨結果=lv0, 缺陷結果=lv1))
        print("彙總")
        print(pd.DataFrame(summary).to_string(index=False))
    txt = buf.getvalue()
    open(os.path.join(OUT, "precheck_demo.txt"), "w").write(txt)
    pd.DataFrame(summary).to_csv(os.path.join(OUT, "precheck_demo.csv"), index=False, encoding="utf-8-sig")
    print(txt)


if __name__ == "__main__":
    main()
