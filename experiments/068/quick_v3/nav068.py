"""068 快篩：描述性等權組合淨值（只供與 FinLab 組合型報表對照，不取代十項統計）。
做法同 066 nav：換股執行日開盤把持股調回等權（單檔上限＝1／選股檔數上限，餘額留現金）；其餘日子各部位隨價格漂移；
開盤取消與落選賣出的資金留現金到下次換股。價格用時點一致調整價（收盤/F、開盤/F；比例調整，隱含股利再投入）。
範圍：2013-05-16～2022-06-30（樣本內）；持有期間下市缺口的部位以最後收盤價轉現金（只影響本描述表）。
"""
import pickle
import numpy as np, pandas as pd

M = dict(np.load("mats068.npz")); meta = pickle.load(open("meta068.pkl", "rb"))
dates, stocks = meta["dates"], meta["stocks"]
T = len(dates)
OA, CA = M["O"] / M["F"], M["C"] / M["F"]
sidx = {s: k for k, s in enumerate(stocks)}
di = {d.date().isoformat(): k for k, d in enumerate(dates)}


def nav(t, combo, top=30, biweekly=False, start="2013-05-16"):
    g = t[t.combo == combo]
    ent, ex = {}, {}
    for r in g.itertuples():
        j = sidx[r.symbol]; a = di[r.entry_date]
        ent.setdefault(a, []).append((r.trade_id, j))
        if isinstance(r.exit_date, str):
            ex.setdefault(di[r.exit_date], []).append(r.trade_id)
    reb = M["rebal_2w"] if biweekly else M["rebal_m"]
    reb_exec = set((np.where(reb)[0] + 1).tolist())
    s0 = dates.searchsorted(pd.Timestamp(start))
    pos, cash, navs, turn, nh = {}, 1.0, [], 0.0, []
    for i in range(s0, T):
        for tid, p in pos.items():
            o = OA[i, p[0]]
            if np.isfinite(o) and o > 0 and np.isfinite(p[2]) and p[2] > 0:
                p[1] *= o / p[2]; p[2] = o
        for tid in ex.get(i, []):
            if tid in pos:
                cash += pos[tid][1]; turn += pos[tid][1]; del pos[tid]
        newp = ent.get(i, [])
        for tid, j in newp:
            pos[tid] = [j, 0.0, OA[i, j]]
        total = cash + sum(p[1] for p in pos.values())
        if (i in reb_exec or newp) and pos:
            w = total / max(len(pos), 1)
            w = min(w, total / top)
            for p in pos.values():
                turn += abs(w - p[1]); p[1] = w
            cash = total - w * len(pos)
        for tid, p in pos.items():
            c = CA[i, p[0]]
            if np.isfinite(c) and c > 0 and np.isfinite(p[2]) and p[2] > 0:
                p[1] *= c / p[2]; p[2] = c
        navs.append(cash + sum(p[1] for p in pos.values())); nh.append(len(pos))
    s = pd.Series(navs, index=dates[s0:T])
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    return dict(combo=combo, 年化報酬=s.iloc[-1] ** (1 / yrs) - 1, 最大回撤=(s / s.cummax() - 1).min(),
                平均持股數=float(np.mean(nh)), 年換手率=turn / 2 / yrs / float(s.mean()), 期末淨值=s.iloc[-1]), s


if __name__ == "__main__":
    import sim068 as S
    res, curves = [], {}
    for f, combos in (("trades068.pkl", S.COMBOS), ("etrades068.pkl", S.ETESTS)):
        try:
            t = pd.read_pickle(f)
        except FileNotFoundError:
            continue
        for c, p in combos.items():
            if c not in set(t.combo):
                continue
            st = p.get("start", S.SIG_START)
            r, s = nav(t, c, top=p["top"], biweekly=bool(p.get("biweekly")), start=str(st.date()))
            res.append(r); curves[c] = s; print(r, flush=True)
    pd.DataFrame(res).to_pickle("nav068.pkl"); pd.DataFrame(curves).to_pickle("navcurve068.pkl")
