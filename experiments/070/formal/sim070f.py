"""070 正式策略包 R01：模擬（全期）。改自快篩 sim070.py：加樣本標籤、E-Test 網格（D-070-20261112-1519-2）、合併組（卡 4.3）。
一筆交易＝連續持有段（入選買進→落選賣出）；無停損、無持股上限、無流動性門檻（原版）。
換股日收盤後判斷，次一市場交易日開盤先賣後買；續選者續抱；等權（逐筆報酬不受權重影響）。
"""
import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/elon-bt")
from framework.core import Calendar, actions_from_table, trade_return

M = dict(np.load("mats070.npz"))
meta = pickle.load(open("meta070.pkl", "rb"))
dates, stocks, ca = meta["dates"], meta["stocks"], meta["ca"]
T, N = len(dates), len(stocks)
cal = Calendar(dates.date)
SIG_START = pd.Timestamp("2014-05-16")   # 卡 6(c)③：2014Q1 財報（期限 5/15）次一交易日起，FCF 近 4 季與營業利益年增才湊齊

COMBOS = {   # 原版 Q1；4.2 一次改一個參數族（CB 變體依 D-070-…-1014-4 不跑）
    "Q1":          dict(cap=100e8, pr=5, rev=4),
    "V-CAP50":     dict(cap=50e8, pr=5, rev=4),
    "V-CAP200":    dict(cap=200e8, pr=5, rev=4),
    "V-PR3":       dict(cap=100e8, pr=3, rev=4),
    "V-PR8":       dict(cap=100e8, pr=8, rev=4),
    "V-REV3":      dict(cap=100e8, pr=5, rev=3),
    "V-TOP10":     dict(cap=100e8, pr=5, rev=4, top=10),
    "V-QTR":       dict(cap=100e8, pr=5, rev=4, quarterly=True),
    "V-LIQ2000萬": dict(cap=100e8, pr=5, rev=4, liq=2e7),
    "V-LIQ5000萬": dict(cap=100e8, pr=5, rev=4, liq=5e7),
    "V-MERGE":     dict(cap=50e8, pr=3, rev=3, top=10, quarterly=True),   # 卡 4.3 合併組（freeze_etest.json）
}
ETESTS = {}
for sch in ("M", "Q", "B"):
    for n_ in (5, 10, 20):
        for lq in (0, 1e7, 2e7):
            ETESTS[f"E-{sch}-N{n_}-L{int(lq/1e4)}"] = dict(cap=100e8, pr=5, rev=4, top=n_, liq=lq or None,
                                                         quarterly=(sch == "Q"), buffer=(sch == "B"))
IS_END, OOS_START = pd.Timestamp("2022-06-30"), pd.Timestamp("2022-10-01")


def selection(i, p, held=()):
    """換股日 i 收盤後的入選名單（索引陣列）。buffer：已持有者排名（市值營收比低→高）≤2N 且仍合格就續抱，再依排名補滿 N 檔。"""
    rev = M["REV4"][i] if p["rev"] == 4 else M["REV3"][i]
    mc = M["MCAP"][i]
    pool = (M["listed"][i] & ~M["FULLD"][i] & ~M["FINANCIAL"] & ~M["PARX"][i] & np.isfinite(M["CT"][i])
            & np.isfinite(mc) & np.isfinite(rev) & (rev > 0))
    if p.get("liq"):
        pool &= np.nan_to_num(M["ADV20"][i]) >= p["liq"]
    ok = pool & (mc < p["cap"]) & M["FCF_POS"][i] & M["ROE_POS"][i] & M["OIG_POS"][i]
    pr = np.where(ok, mc / np.where(rev > 0, rev, np.nan), np.inf)
    ok &= pr < p["pr"]
    S = np.where(ok)[0]
    if p.get("top"):
        S = S[np.lexsort((S, pr[S]))]                    # 市值營收比由低到高，同值依代號
        if p.get("buffer"):
            keep = [j for j in S[:2 * p["top"]] if j in held]
            add = [j for j in S if j not in keep][:max(0, p["top"] - len(keep))]
            S = np.array(sorted(keep + add, key=lambda j: (pr[j], j)), dtype=int)
        else:
            S = S[:p["top"]]
    return S


def can_buy(i, j):
    if not M["present"][i, j] or M["notrade"][i, j] or not np.isfinite(M["O"][i, j]):
        return False, "停牌或無開盤成交"
    if M["badlim"][i, j]:
        return False, "資料不足：限幅待查／缺參考價"
    if M["O"][i, j] <= 0:
        return False, "資料不足：開盤價缺漏"
    lu = M["LU"][i, j]
    if not M["nolim"][i, j] and np.isfinite(lu) and M["O"][i, j] >= lu - 1e-9:
        return False, "開盤漲停"
    return True, ""


def can_sell(i, j):
    if not M["present"][i, j] or M["notrade"][i, j] or not np.isfinite(M["O"][i, j]):
        return False, "停牌或無開盤成交"
    if M["badlim"][i, j]:
        return "bad", "資料不足：出場日限幅待查"
    if M["O"][i, j] <= 0:
        return "bad", "資料不足：出場日開盤價缺漏"
    ld = M["LD"][i, j]
    if not M["nolim"][i, j] and np.isfinite(ld) and M["O"][i, j] <= ld + 1e-9:
        return False, "開盤跌停"
    return True, ""


def run(name, p):
    rebal = M["q_rebal"] if p.get("quarterly") else M["rebal_m"]
    hold, pend_buy, pend_sell = {}, {}, {}
    rows, cancels, nsel = [], [], []
    for i in range(T):
        # 開盤：先賣後買；待賣部位每個交易日都重試（防錯 C14）
        for j in list(pend_sell):
            ok, why = can_sell(i, j)
            if ok:
                h = hold.pop(j); info = pend_sell.pop(j)
                rows.append(dict(combo=name, j=j, sig_i=h["sig_i"], entry_i=h["entry_i"], entry_px=h["entry_px"],
                                 exit_i=i, exit_px=M["O"][i, j] if ok is True else np.nan, plan_exit_i=info["plan"],
                                 exit_reason=info["why"], bad_exit=why if ok == "bad" else None))
        for j, info in list(pend_buy.items()):
            ok, why = can_buy(i, j)
            if ok:
                hold[j] = dict(entry_i=i, entry_px=M["O"][i, j], sig_i=info["sig"])
            else:
                cancels.append(dict(combo=name, j=j, sig_i=info["sig"], i=i, why=why))
        pend_buy = {}
        if rebal[i] and dates[i] >= SIG_START and i < T - 1:
            S = selection(i, p, held=set(hold))
            nsel.append((dates[i], len(S)))
            Sset = set(S.tolist())
            for j in list(hold):
                if j not in Sset and j not in pend_sell:
                    pend_sell[j] = dict(plan=i + 1, why="落選")
            for j in S:
                if j in hold or j in pend_sell:
                    continue
                pend_buy[j] = dict(sig=i)
    for j, h in hold.items():
        rows.append(dict(combo=name, j=j, sig_i=h["sig_i"], entry_i=h["entry_i"], entry_px=h["entry_px"],
                         exit_i=None, exit_px=np.nan, plan_exit_i=pend_sell.get(j, {}).get("plan"),
                         exit_reason="資料終點仍持有"))
    return rows, cancels, nsel


ACT = {}
def acts(j):
    if j not in ACT:
        ACT[j] = actions_from_table(ca, stocks[j])
    return ACT[j]


def finalize(rows):
    out = []
    last_listed_i = T - 1 - M["listed"][::-1].argmax(axis=0)
    for k, r in enumerate(rows):
        j = r["j"]; ent = dates[r["entry_i"]]
        rec = dict(trade_id=f"{r['combo']}-{k+1:06d}", combo=r["combo"], symbol=stocks[j],
                   signal_date=dates[r["sig_i"]].date().isoformat(),
                   entry_date=ent.date().isoformat(), entry_px=r["entry_px"], exit_date=None, exit_px=r["exit_px"],
                   exit_reason=r["exit_reason"], plan_exit_date=None, ret=np.nan, hold_days=np.nan,
                   cluster=ent.date().isoformat(), sample="樣本內", excluded_reason=None, ret_flags=None)
        sig = dates[r["sig_i"]]
        ex = dates[r["exit_i"]] if r["exit_i"] is not None else None
        if sig >= OOS_START:
            rec["sample"] = "樣本外"
        elif sig <= IS_END and ex is not None and ex <= IS_END:
            rec["sample"] = "樣本內"
        else:
            rec["sample"] = "隔離帶"
        if r["exit_i"] is None:
            if not M["listed"][T - 1, j] and last_listed_i[j] < T - 1:
                rec["excluded_reason"] = "持有期間下市或停止掛牌，最終現金／權益未取得（缺口）"
            else:
                rec["excluded_reason"] = "資料終點仍持有，未完成"
            out.append(rec); continue
        if rec["sample"] == "隔離帶":
            rec["excluded_reason"] = "持有段跨越樣本內切點或隔離帶，不列入任一段"
            rec["exit_date"] = ex.date().isoformat()
            out.append(rec); continue
        rec["exit_date"] = ex.date().isoformat()
        rec["plan_exit_date"] = dates[min(r["plan_exit_i"], T - 1)].date().isoformat()
        a, b = r["entry_i"], r["exit_i"]
        if r.get("bad_exit"):
            rec["excluded_reason"] = r["bad_exit"]
        elif M["JUMP"][a:b + 1, j].any():
            rec["excluded_reason"] = "持有期間（進場～出場含首尾）有異常跳動（超出漲跌停且查無公司行動），列未完成"
        else:
            al = acts(j)
            bad = [x for x in al if "資料不足" in x.kind and ent.date() < x.ex_date <= ex.date()]
            if bad:
                rec["excluded_reason"] = "持有期間公司行動資料不足：" + "、".join(f"{x.ex_date}{x.kind}" for x in bad)
            else:
                tr = trade_return("long", r["entry_px"], r["exit_px"], ent, ex, al, "open", "open")
                rec["ret"] = tr.ret
                rec["hold_days"] = cal.hold_days(ent, ex)
                rec["ret_flags"] = "；".join(tr.flags) or None
        out.append(rec)
    return out


if __name__ == "__main__":
    import os
    WHICH = os.environ.get("WHICH", "card")
    SET = COMBOS if WHICH == "card" else ETESTS
    allr, allc, alln = [], [], {}
    for name, p in SET.items():
        rows, cancels, nsel = run(name, p)
        fr = finalize(rows)
        allr += fr
        for c in cancels:
            c.update(symbol=stocks[c["j"]], signal_date=dates[c["sig_i"]].date().isoformat(), date=dates[c["i"]].date().isoformat())
        allc += cancels
        alln[name] = nsel
        df = pd.DataFrame(fr)
        ns = np.array([x[1] for x in nsel])
        print(name, len(df), "納入", int(df.excluded_reason.isna().sum()), "取消", len(cancels),
              "平均入選", round(ns.mean(), 1), "最多", ns.max(), flush=True)
    sfx = "" if WHICH == "card" else "_etest"
    pd.DataFrame(allr).to_pickle(f"trades070{sfx}.pkl")
    pd.DataFrame(allc).drop(columns=["j", "sig_i", "i"]).to_pickle(f"cancels070{sfx}.pkl")
    pickle.dump(alln, open(f"nsel070{sfx}.pkl", "wb"))
