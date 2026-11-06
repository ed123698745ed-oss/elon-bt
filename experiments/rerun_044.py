"""驗收：用框架重跑 044 R1（策略卡 V01），與 2026-10-31 快篩報告並列。

依策略卡 V01 規則；差異只來自框架與資料層：
- 報酬：固定股數＋實得現金（研究預設口徑 V03，Ed 2026-11-03 定案）；原快篩用 V02 參考價比例連乘。
- 訊號分數：同樣以固定股數＋現金計 TR(S)/TR(S−5)。
- 資料：data-20261105（興櫃段剔除、官方除權息漲跌停、公司行動表、跳動旗標）。
- 母體：當日在官方上市或上櫃（資料層主日K；興櫃、未證實身分列已移到隔離檔）；排除 00 開頭（ETF）與 91 開頭（存託憑證）。
  （退回-67 起不再用「現行掛牌日起」判定：轉上市前的合法上櫃期間納入，初次掛牌前五日無漲跌幅不判觸限。）
- 成交：依策略卡 V01（不呼叫通用 judge_fill）——進場日開盤價等於漲停或跌停價即取消（不分方向）；
  出場日收盤做多碰跌停、放空碰漲停即順延到下一個不觸限且有成交的交易日。卡片規則比通用判定嚴格：
  通用 judge_fill 對「收在限價」放行並標「排隊未驗證」，044 卡片則直接取消／順延。無漲跌幅日限價為空，不會觸限。
- 訊號窗或持有期間碰到跳動、資料不足的公司行動 → 該部位未完成，所屬批次不列主統計（與原快篩相同處理）。
- 進場日或出場判定日為限幅待查／缺參考價 → 該部位「未完成：限幅待查資料不足」（退回-68，Eve R03）。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework import stats  # noqa: E402
from framework.core import Calendar, actions_from_table, trade_return  # noqa: E402

OUT = os.environ.get("ELON_OUT", "/home/claude/raw_dl/out")
BT = os.environ.get("BT_STATS_PATH", "/home/claude/vendor/bt_stats_v1.0.py")
RES = os.environ.get("RES_DIR", "/home/claude/rerun044_new")
LAST_S = date(2026, 10, 22)


def main():
    os.makedirs(RES, exist_ok=True)
    stats.load(BT)
    cal = Calendar(pd.read_parquet(f"{OUT}/calendar.parquet")["date"].dt.date)
    st = pd.read_parquet(f"{OUT}/status.parquet")
    cols = ["date", "stock_id", "open", "close", "amount", "limit_up", "limit_down", "no_trade", "jump_flag", "limit_src"]
    dk = pd.read_parquet(f"{OUT}/daily_k.parquet", columns=cols)
    dk = dk[~dk["stock_id"].str[:2].isin(["00", "91"])]
    dk["date"] = dk["date"].dt.date
    days = [d for d in cal.days if d <= date(2026, 11, 4)]
    idx = {d: i for i, d in enumerate(days)}
    dk = dk[dk["date"].isin(idx)]
    ids = sorted(dk["stock_id"].unique())
    col = {s: j for j, s in enumerate(ids)}
    T, N = len(days), len(ids)

    def wide(c, fill=np.nan):
        a = np.full((T, N), fill, dtype=float)
        a[dk["date"].map(idx).values, dk["stock_id"].map(col).values] = dk[c].astype(float).values
        return a
    O, C, AMT, UP, DN = wide("open"), wide("close"), wide("amount", 0.0), wide("limit_up"), wide("limit_down")
    NT = wide("no_trade", 1.0) > 0           # 無資料或無成交＝不可成交
    JP = wide("jump_flag", 0.0) > 0
    # 退回-68（Eve R03）：限幅待查／缺參考價的日子無法判斷是否觸限 → 進出場碰到即列資料不足（不當可成交、也不當取消）
    dk["pending_limit"] = dk["limit_src"].astype(str).str.startswith("待查") | (dk["limit_src"] == "缺參考價")
    PD = wide("pending_limit", 0.0) > 0
    AMT[NT] = 0.0
    ca = pd.read_parquet(f"{OUT}/corp_actions.parquet")
    ca = ca[ca["stock_id"].isin(col)]
    acts = {s: actions_from_table(g, s) for s, g in ca.groupby("stock_id")}
    bad_act = {s: [a.ex_date for a in v if "資料不足" in a.kind] for s, v in acts.items()}

    # 每曆週最後交易日
    wk = pd.Series(days).groupby(pd.Series([d.isocalendar()[:2] for d in days])).max()
    S_list = [d for d in wk.values if date(1999, 2, 5) <= d <= LAST_S]
    cs = np.cumsum(np.vstack([np.zeros((1, N)), AMT]), axis=0)  # 前綴和
    pos_rows, batch_rows = [], []
    for S in S_list:
        i = idx[S]
        if i < 20 or i + 1 >= T:
            continue
        j5 = i - 5
        avg20 = (cs[i] - cs[i - 20]) / 20.0
        elig = (~NT[i]) & (C[i] >= 10) & (avg20 >= 5e7) & ~np.isnan(C[j5]) & ~NT[j5]
        cand = []
        for jj in np.where(elig)[0]:
            s = ids[jj]
            if JP[j5 + 1:i + 1, jj].any():
                continue
            if any(days[j5] < x <= S for x in bad_act.get(s, [])):
                continue
            tr = trade_return("long", C[j5, jj], C[i, jj], days[j5], S, acts.get(s, [])).ret
            cand.append((tr, s, jj))
        n = len(cand)
        if n < 40:
            continue
        k = n // 10
        cand.sort(key=lambda x: (x[0], x[1]))
        legs = {"long": cand[:k], "short": sorted(cand, key=lambda x: (-x[0], x[1]))[:k]}
        E = i + 1
        res = {"long": [], "short": []}
        incomplete = False
        last_exit = E
        for side, sel in legs.items():
            for tr, s, jj in sel:
                o = O[E, jj]
                if PD[E, jj] and not NT[E, jj]:
                    res[side].append(None)
                    incomplete = True
                    pos_rows.append(dict(S=S, side=side, stock_id=s, status="未完成：限幅待查資料不足", ret=None))
                    continue
                if NT[E, jj] or np.isnan(o) or o == UP[E, jj] or o == DN[E, jj]:
                    res[side].append(None)
                    pos_rows.append(dict(S=S, side=side, stock_id=s, status="取消", ret=None))
                    continue
                x = E + 4
                while x < T and (NT[x, jj] or (side == "long" and C[x, jj] == DN[x, jj]) or
                                 (side == "short" and C[x, jj] == UP[x, jj])):
                    x += 1
                stt, r = "完成", None
                if x >= T:
                    stt = "未完成：查無出場"
                elif JP[E + 1:x + 1, jj].any() or any(days[E] < y <= days[x] for y in bad_act.get(s, [])):
                    stt = "未完成：跳動或公司行動資料不足"
                elif PD[E + 4:x + 1, jj].any():
                    stt = "未完成：限幅待查資料不足"
                else:
                    r = trade_return(side, o, C[x, jj], days[E], days[x], acts.get(s, [])).ret
                    last_exit = max(last_exit, x)
                if stt != "完成":
                    incomplete = True
                res[side].append(r)
                pos_rows.append(dict(S=S, side=side, stock_id=s, status=stt, ret=r,
                                     exit=days[x] if x < T else None, delay=(x - E - 4) if x < T else None))
        if all(v is None for v in res["long"]) or all(v is None for v in res["short"]):
            batch_rows.append(dict(S=S, E=days[E], status="一腿全未成交，不建立"))
            continue
        if incomplete:
            batch_rows.append(dict(S=S, E=days[E], status="含未完成部位"))
            continue
        L = sum(v for v in res["long"] if v is not None) / k
        Sh = sum(v for v in res["short"] if v is not None) / k
        batch_rows.append(dict(S=S, E=days[E], status="完成", N=n, k=k, long=L, short=Sh, ret=(L + Sh) / 2,
                               hold_days=cal.hold_days(days[E], days[last_exit])))
    B = pd.DataFrame(batch_rows)
    P = pd.DataFrame(pos_rows)
    B.to_csv(f"{RES}/batches.csv", index=False)
    P.to_csv(f"{RES}/positions.csv", index=False)
    done = B[B["status"] == "完成"].copy()
    bt, sha = stats.current()

    def row(df, r, name):
        s = bt.summarize(df[r].values, hold_days=df["hold_days"].values)
        return {"組": name, **{c: s[c] for c in ["樣本數", "平均報酬", "平均持有交易日數", "單利年化", "勝率", "賠率R", "凱利", "標準差", "t值", "雙尾p"]}}
    done["long_c"], done["short_c"] = done["long"] / 2, done["short"] / 2
    cut = date(2013, 9, 23)
    out = []
    for nm, df in [("全期", done), ("2013-09-23前", done[done["E"] < cut]), ("2013-09-23起", done[done["E"] >= cut]),
                   ("2026年", done[pd.to_datetime(done["E"]).dt.year == 2026])]:
        for r, lab in [("ret", "主報酬"), ("long_c", "多方貢獻"), ("short_c", "空方貢獻")]:
            out.append(row(df, r, f"{nm}｜{lab}"))
    T10 = pd.DataFrame(out)
    T10.to_csv(f"{RES}/ten_stats.csv", index=False)
    summ = {"batches_total": len(B), "status": B["status"].value_counts().to_dict(),
            "positions": P["status"].value_counts().to_dict(), "bt_stats_sha256": sha}
    json.dump(summ, open(f"{RES}/summary.json", "w"), ensure_ascii=False, indent=1, default=str)
    pd.set_option("display.width", 200)
    print(json.dumps(summ, ensure_ascii=False, default=str))
    print(T10.to_string(index=False))


if __name__ == "__main__":
    main()
