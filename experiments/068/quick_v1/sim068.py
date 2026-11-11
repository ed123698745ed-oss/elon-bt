"""068 快篩：模擬（只用樣本內，資料止於 2022-06-30）。
一筆交易＝連續持有段（入選買進→落選賣出）；無停損（依原版）。
換股日收盤後判斷，次一市場交易日開盤先賣後買；續選者續抱。
"""
import os, sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/elon-bt")
from framework.core import Calendar, actions_from_table, trade_return

M = dict(np.load("mats068.npz"))
meta = pickle.load(open("meta068.pkl", "rb"))
dates, stocks, ca = meta["dates"], meta["stocks"], meta["ca"]
T, N = len(dates), len(stocks)
cal = Calendar(dates.date)
IS_END = pd.Timestamp("2022-06-30")
SIG_START = pd.Timestamp("2013-05-16")   # 2013Q1（首份 IFRS 季報）期限 5/15 之次一交易日起可用（D-068-20261104-1947-1②、D-068-…-0018-2）
ROE4_START = pd.Timestamp("2014-04-01")  # 2013 年報期限 3/31 之次一交易日（湊滿 4 季 IFRS；D-068-…-0018-4）
TOL = 1e-12

COMBOS = {   # 原版 M1、對照 M0、4.2 一次改一個參數族（策略卡）；E-Test 另列
    "M0":          dict(L=60, top=30, filt=None),
    "M1":          dict(L=60, top=30, filt="roe"),
    "V-L20":       dict(L=20, top=30, filt="roe"),
    "V-L120":      dict(L=120, top=30, filt="roe"),
    "V-TOP10":     dict(L=60, top=10, filt="roe"),
    "V-FILT1ST":   dict(L=60, top=30, filt="roe", filt_first=True),
    "V-ROE8":      dict(L=60, top=30, filt="roe4", start=ROE4_START),
    "V-LIQ0.5億":  dict(L=60, top=30, filt="roe", liq=5e7),
    "V-LIQ2億":    dict(L=60, top=30, filt="roe", liq=2e8),
    "V-2W":        dict(L=60, top=30, filt="roe", biweekly=True),
    "V-MKT":       dict(L=60, top=30, filt="roe", mkt=True),
    "M1-同期":     dict(L=60, top=30, filt="roe", start=ROE4_START),   # V-ROE8 同期間對照（D-068-…-0018-4）
}
ETESTS = {
    "E-M1-ADJ":    dict(L=60, top=30, filt="roe", adj=True),   # D-068-20261111-0018-7
}
FILT = {"roe": "ROE_Q_POS", "roe4": "ROE4_GT8", "rev": "REV_YOY_POS"}


def selection(i, p):
    """換股日 i 收盤後的入選名單（索引陣列）。"""
    L = p["L"]
    if i - L < 0:
        return np.array([], int)
    X = M["CADJ"] if p.get("adj") else M["CT"]
    a, b = X[i], X[i - L]
    pool = M["listed"][i] & M["listed"][i - L] & ~M["FULLD"][i] & np.isfinite(a) & np.isfinite(b) & (b > 0)
    if p.get("liq"):
        pool &= np.nan_to_num(M["ADV20"][i]) >= p["liq"]
    mom = np.where(pool, a / np.where(b > 0, b, 1.0), -np.inf)
    f = M[FILT[p["filt"]]][i] if p.get("filt") else np.ones(N, bool)
    if p.get("filt_first"):
        mom = np.where(f, mom, -np.inf)
    cand = np.where(np.isfinite(mom))[0]
    order = cand[np.lexsort((cand, -mom[cand]))]     # 動能由大到小，同值依代號
    S = order[:p["top"]]
    if p.get("filt") and not p.get("filt_first"):
        S = S[f[S]]
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
    rebal = M["rebal_2w"] if p.get("biweekly") else M["rebal_m"]
    start = p.get("start", SIG_START)
    hold, pend_buy, pend_sell = {}, {}, {}
    rows, cancels, nsel = [], [], []
    for i in range(T):
        # 1) 開盤：先賣後買；待賣部位每個交易日都重試（防錯 C14）
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
        # 2) 換股日收盤：決定名單
        if rebal[i] and dates[i] >= start:
            S = selection(i, p)
            nsel.append((dates[i], len(S)))
            Sset = set(S.tolist())
            for j in list(hold):
                if j not in Sset and j not in pend_sell:
                    pend_sell[j] = dict(plan=i + 1, why="落選")
            allow_new = (not p.get("mkt")) or (bool(M["mkt_has"][i]) and bool(M["mkt_ok"][i]))
            if allow_new:
                for j in S:
                    if j in hold or j in pend_sell:
                        continue
                    pend_buy[j] = dict(sig=i)
    for j, h in hold.items():
        rows.append(dict(combo=name, j=j, sig_i=h["sig_i"], entry_i=h["entry_i"], entry_px=h["entry_px"],
                         exit_i=None, exit_px=np.nan, plan_exit_i=pend_sell.get(j, {}).get("plan"),
                         exit_reason="跨越樣本內切點（2022-06-30 仍持有）"))
    return rows, cancels, nsel


ACT = {}
def acts(j):
    if j not in ACT:
        ACT[j] = actions_from_table(ca, stocks[j])
    return ACT[j]


def finalize(rows, is_etest):
    out = []
    last_listed_i = T - 1 - M["listed"][::-1].argmax(axis=0)
    for k, r in enumerate(rows):
        j = r["j"]; ent = dates[r["entry_i"]]
        rec = dict(trade_id=f"{r['combo']}-{k+1:06d}", combo=r["combo"], is_etest=is_etest, symbol=stocks[j],
                   signal_date=dates[r["sig_i"]].date().isoformat(),
                   info_time=dates[r["sig_i"]].strftime("%Y-%m-%d 14:30"), entry_time=ent.strftime("%Y-%m-%d 09:00"),
                   entry_date=ent.date().isoformat(), entry_px=r["entry_px"], exit_date=None, exit_px=r["exit_px"],
                   exit_reason=r["exit_reason"], plan_exit_date=None, ret=np.nan, hold_days=np.nan,
                   cluster=ent.date().isoformat(), sample="樣本內", excluded_reason=None, ret_flags=None)
        if r["exit_i"] is None:
            if not M["listed"][T - 1, j] and last_listed_i[j] < T - 1:
                rec["excluded_reason"] = "持有期間下市或停止掛牌，最終現金／權益未取得（缺口）"
            else:
                rec["excluded_reason"] = "持有段跨越樣本內切點，不列入任一段"
            rec["sample"] = "隔離帶"
            out.append(rec); continue
        ex = dates[r["exit_i"]]
        rec["exit_date"] = ex.date().isoformat()
        rec["plan_exit_date"] = dates[min(r["plan_exit_i"], T - 1)].date().isoformat()
        a, b = r["entry_i"], r["exit_i"]
        if r.get("bad_exit"):
            rec["excluded_reason"] = r["bad_exit"]
        elif M["JUMP"][a + 1:b + 1, j].any():
            rec["excluded_reason"] = "持有期間有異常跳動（超出漲跌停且查無公司行動），列未完成"
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


def run_all(combos, is_etest):
    allr, allc, alln = [], [], {}
    for name, p in combos.items():
        rows, cancels, nsel = run(name, p)
        fr = finalize(rows, is_etest)
        allr += fr
        for c in cancels:
            c.update(symbol=stocks[c["j"]], signal_date=dates[c["sig_i"]].date().isoformat(), date=dates[c["i"]].date().isoformat())
        allc += cancels
        alln[name] = nsel
        df = pd.DataFrame(fr)
        print(name, len(df), "納入", int(df.excluded_reason.isna().sum()), "取消", len(cancels), flush=True)
    return pd.DataFrame(allr), pd.DataFrame(allc).drop(columns=["j", "sig_i", "i"]), alln


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "card"
    if which == "card":
        t, c, n = run_all(COMBOS, False)
        t.to_pickle("trades068.pkl"); c.to_pickle("cancels068.pkl"); pickle.dump(n, open("nsel068.pkl", "wb"))
    else:
        t, c, n = run_all(ETESTS, True)
        t.to_pickle("etrades068.pkl"); c.to_pickle("ecancels068.pkl"); pickle.dump(n, open("ensel068.pkl", "wb"))
