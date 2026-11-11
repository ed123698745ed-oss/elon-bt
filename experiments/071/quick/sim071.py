"""071 快篩：模擬（只用樣本內；資料止於 2020-07-01）。
主統計單位＝一期（季或月）組合報酬：R＝0.7×多方等權報酬＋h×放空 0050 報酬（h＝空方比例，原版 0.3）。
多方：換股日收盤後判斷，次一交易日開盤調回等權；進場開盤漲停、停牌或無開盤成交取消、不遞補、權重留現金（報酬 0）。
出場（落選）開盤跌停或停牌順延到第一個可成交開盤。續選者續抱（持有段不另計新的一筆）。
期報酬：每檔自本期開盤（續抱者為上期期末標價）到下期換股執行日開盤（不可成交則順延到第一個可成交開盤），
固定股數加實得現金（framework.core.trade_return）；持有期間異常跳動或公司行動資料不足者，自該期多方平均剔除並逐筆列出。
"""
import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/elon-bt")
from framework.core import Calendar, actions_from_table, trade_return

M = dict(np.load("mats071.npz"))
meta = pickle.load(open("meta071.pkl", "rb"))
dates, stocks, ca = meta["dates"], meta["stocks"], meta["ca"]
T, N = len(dates), len(stocks)
cal = Calendar(dates.date)
J50 = int(np.where(stocks == "0050")[0][0])
IS_ENTRY_END, ISO_FIRST = pd.Timestamp("2020-06-30"), pd.Timestamp("2020-07-01")
COMMON = np.array([s != "0050" for s in stocks])

COMBOS = {   # 原版 H1；4.2 一次改一個參數族（台指期避險組依 D-071-20261104-1947-1 放第二階段，不跑）
    "H1":       dict(q=0.20, h=0.30),
    "V-P10":    dict(q=0.10, h=0.30),
    "V-P30":    dict(q=0.30, h=0.30),
    "V-H0":     dict(q=0.20, h=0.00),
    "V-H50":    dict(q=0.20, h=0.50),
    "V-H70":    dict(q=0.20, h=0.70),
    "V-MON":    dict(q=0.20, h=0.30, monthly=True),
    "V-TOP20":  dict(q=0.20, h=0.30, liq=5e7, top=20),
    "V-LIQ":    dict(q=0.20, h=0.30, liq=5e7),
    "V-QUAL":   dict(q=0.20, h=0.30, qual=True),
}


def selection(i, p):
    pb = M["PBR"][i]
    pool = M["listed"][i] & COMMON & ~M["FULLD"][i] & np.isfinite(pb) & (pb > 0)
    if pool.sum() == 0:
        return np.array([], int), np.nan, 0
    thr = float(np.quantile(pb[pool], p["q"]))
    ok = pool & (pb < thr)
    if p.get("liq"):
        ok &= np.nan_to_num(M["ADV20"][i]) >= p["liq"]
    if p.get("qual"):            # 近四季稅後純益 > 0：官方本益比有值（官方：每股稅後純益 ≤0 不計算本益比）
        ok &= np.isfinite(M["PE"][i]) & (M["PE"][i] > 0)
    S = np.where(ok)[0]
    if p.get("top"):
        S = S[np.lexsort((S, pb[S]))][:p["top"]]
    return S, thr, int(pool.sum())


def tradable(i, j):
    return M["present"][i, j] and not M["notrade"][i, j] and np.isfinite(M["O"][i, j]) and M["O"][i, j] > 0 \
        and not M["badlim"][i, j]


def can_buy(i, j):
    if not tradable(i, j):
        return False, "停牌或無開盤成交" if not M["badlim"][i, j] else "資料不足：限幅待查／缺參考價"
    lu = M["LU"][i, j]
    if not M["nolim"][i, j] and np.isfinite(lu) and M["O"][i, j] >= lu - 1e-9:
        return False, "開盤漲停"
    return True, ""


def can_sell(i, j):
    if not tradable(i, j):
        return False
    ld = M["LD"][i, j]
    return not (not M["nolim"][i, j] and np.isfinite(ld) and M["O"][i, j] <= ld + 1e-9)


def first_sell(i, j):
    """自 i 起第一個可成交（非開盤跌停）的開盤；找不到回傳 None。"""
    for t in range(i, T):
        if can_sell(t, j):
            return t
    return None


def first_mark(i, j):
    """續抱者期末標價：自 i 起第一個有成交的開盤（不檢查跌停，續抱不需賣出）。"""
    for t in range(i, T):
        if tradable(t, j):
            return t
    return None


ACT = {}
def acts(j):
    if j not in ACT:
        ACT[j] = actions_from_table(ca, stocks[j])
    return ACT[j]


def leg_return(direction, j, a, b):
    """a、b 為索引（開盤）；回傳 (ret, 排除原因)。"""
    if M["JUMP"][a + 1:b + 1, j].any():
        return np.nan, "持有期間有異常跳動（超出漲跌停且查無公司行動），列未完成"
    al = acts(j)
    bad = [x for x in al if "資料不足" in x.kind and dates[a].date() < x.ex_date <= dates[b].date()]
    if bad:
        return np.nan, "持有期間公司行動資料不足：" + "、".join(f"{x.ex_date}{x.kind}" for x in bad)
    tr = trade_return(direction, M["O"][a, j], M["O"][b, j], dates[a], dates[b], al, "open", "open")
    return tr.ret, None


def sample_of(a, b):
    if b is None:
        return "隔離帶"
    if dates[a] <= IS_ENTRY_END and dates[b] <= ISO_FIRST:
        return "樣本內"
    return "隔離帶"


def run(name, p):
    sig = np.where(M["is_me"] if p.get("monthly") else M["is_qe"])[0]
    sig = sig[sig < T - 1]
    ex = sig + 1                                   # 換股執行日（次一交易日開盤）
    hold = {}                                      # j -> dict(entry_i, entry_px, sig_i, mark_i)
    periods, segs, cancels, legrows, nsel = [], [], [], [], []
    for kk in range(len(sig) - 1):
        i_sig, a, b_plan = sig[kk], ex[kk], ex[kk + 1]
        S, thr, npool = selection(i_sig, p)
        Sset = set(S.tolist())
        nsel.append((dates[i_sig], len(S), thr, npool))
        # 開盤：落選者賣出（順延到第一個可成交開盤），持有段結束
        for j in [j for j in hold if j not in Sset]:
            h = hold.pop(j)
            t = first_sell(a, j)
            segs.append(dict(combo=name, j=j, sig_i=h["sig_i"], entry_i=h["entry_i"], exit_i=t, plan_exit_i=a,
                             exit_reason="落選"))
        # 新入選者買進
        for j in S:
            if j in hold:
                continue
            ok, why = can_buy(a, j)
            if ok:
                hold[j] = dict(entry_i=a, sig_i=i_sig, mark_i=a)
            else:
                cancels.append(dict(combo=name, j=j, sig_i=i_sig, i=a, why=why))
        # 本期多方報酬
        contrib, excl = [], []
        for j in S:
            if j not in hold:
                contrib.append(0.0)                 # 進場取消：權重留現金
                continue
            st = hold[j]["mark_i"]
            en = first_mark(b_plan, j)
            if en is None:
                excl.append((stocks[j], "期末無成交（停牌延續至資料終點或下市），最終現金／權益未取得（缺口）"))
                h = hold.pop(j)
                segs.append(dict(combo=name, j=j, sig_i=h["sig_i"], entry_i=h["entry_i"], exit_i=None,
                                 plan_exit_i=b_plan, exit_reason="期末無成交"))
                continue
            ret, why = leg_return("long", j, st, en)
            if why:
                excl.append((stocks[j], why)); hold[j]["mark_i"] = en; continue
            contrib.append(ret)
            hold[j]["mark_i"] = en
        L = float(np.mean(contrib)) if contrib else np.nan
        # 0050 放空腿（同期開盤到開盤）
        st50 = a; en50 = first_mark(b_plan, J50)
        s_ret, s_why = leg_return("short", J50, st50, en50) if en50 is not None else (np.nan, "0050 期末無成交")
        flags = []
        if dates[a] in meta["STOP_SHORT"]:
            flags.append("0050 進場日停券")
        R = 0.7 * L + p["h"] * s_ret if p["h"] > 0 else 0.7 * L
        smp = sample_of(a, b_plan)
        periods.append(dict(combo=name, sig_date=dates[i_sig], entry_date=dates[a], exit_date=dates[b_plan],
                            n_sel=len(S), n_cancel=sum(1 for j in S if j not in hold), n_excl=len(excl),
                            excl=excl, L=L, S=s_ret, R=R, flags="；".join(flags) or None, sample=smp,
                            hold_days=cal.hold_days(dates[a], dates[b_plan]), short_excl=s_why))
    # 期末仍持有的持有段
    for j, h in hold.items():
        segs.append(dict(combo=name, j=j, sig_i=h["sig_i"], entry_i=h["entry_i"], exit_i=None, plan_exit_i=None,
                         exit_reason="資料終點（2020-07-01）仍持有"))
    return periods, segs, cancels, nsel


def finalize_segs(segs):
    out = []
    for n, s in enumerate(segs):
        j = s["j"]; a = s["entry_i"]; b = s["exit_i"]
        rec = dict(trade_id=f"{s['combo']}-S{n+1:06d}", combo=s["combo"], symbol=stocks[j],
                   signal_date=dates[s["sig_i"]].date().isoformat(), entry_date=dates[a].date().isoformat(),
                   entry_px=M["O"][a, j], exit_date=None, exit_px=np.nan, exit_reason=s["exit_reason"],
                   plan_exit_date=None if s["plan_exit_i"] is None else dates[s["plan_exit_i"]].date().isoformat(),
                   ret=np.nan, hold_days=np.nan, cluster=dates[a].date().isoformat(), sample="隔離帶",
                   excluded_reason=None)
        if b is None:
            rec["excluded_reason"] = "持有段未在樣本內結束（跨越隔離帶或資料終點），不列入任一段" if s["plan_exit_i"] is None \
                else "出場順延至資料終點後（停牌延續或下市），最終現金／權益未取得（缺口）"
            out.append(rec); continue
        rec["exit_date"] = dates[b].date().isoformat(); rec["exit_px"] = M["O"][b, j]
        rec["sample"] = sample_of(a, b)
        if rec["sample"] != "樣本內":
            rec["excluded_reason"] = "持有段跨越隔離帶，不列入任一段"
            out.append(rec); continue
        ret, why = leg_return("long", j, a, b)
        if why:
            rec["excluded_reason"] = why
        else:
            rec["ret"] = ret; rec["hold_days"] = cal.hold_days(dates[a], dates[b])
        out.append(rec)
    return out


if __name__ == "__main__":
    P, Sg, Cn, Ns = [], [], [], {}
    for name, p in COMBOS.items():
        periods, segs, cancels, nsel = run(name, p)
        P += periods; Sg += finalize_segs(segs)
        for c in cancels:
            c.update(symbol=stocks[c["j"]], signal_date=dates[c["sig_i"]].date().isoformat(),
                     date=dates[c["i"]].date().isoformat())
        Cn += cancels; Ns[name] = nsel
        pdf = pd.DataFrame(periods); ns = np.array([x[1] for x in nsel])
        print(name, "期數", len(pdf), "樣本內", int((pdf["sample"] == "樣本內").sum()), "平均檔數", round(ns.mean(), 1),
              "最少", ns.min(), "最多", ns.max(), "取消", len(cancels), "剔除", int(pdf.n_excl.sum()), flush=True)
    pd.to_pickle(pd.DataFrame(P), "periods071.pkl"); pd.to_pickle(pd.DataFrame(Sg), "segs071.pkl")
    pd.to_pickle(pd.DataFrame(Cn).drop(columns=["j", "sig_i", "i"]), "cancels071.pkl"); pickle.dump(Ns, open("nsel071.pkl", "wb"))
