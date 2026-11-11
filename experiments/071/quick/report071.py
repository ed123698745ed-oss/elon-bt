"""071 快篩報告（HTML → Google 文件）。"""
import html, pickle, sys
import numpy as np, pandas as pd

tt = pd.read_pickle("card_ten.pkl"); dd = pd.read_pickle("card_dd.pkl"); L = pd.read_pickle("legL.pkl")
Sx = pd.read_pickle("legS.pkl"); G = pd.read_pickle("seg.pkl"); nv = pd.read_pickle("nav.pkl")
st = pd.read_pickle("sens_ten.pkl"); P = pd.read_pickle("periods071.pkl"); cn = pd.read_pickle("cancels071.pkl")
meta = pickle.load(open("meta071.pkl", "rb"))
E = html.escape
Pc = lambda v, d=2: "N/A" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v*100:.{d}f}%"
Gf = lambda v: "N/A" if v is None or (isinstance(v, float) and np.isnan(v)) else (f"{v:.2e}" if abs(v) < 1e-3 else f"{v:.4f}")
Ff = lambda v, d=2: "N/A" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{d}f}"


def table(head, rows):
    h = "".join(f"<th>{E(str(x))}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{E(str(x))}</td>" for x in r) + "</tr>" for r in rows)
    return f'<table border="1" cellpadding="3" style="border-collapse:collapse;font-size:9pt"><tr>{h}</tr>{b}</table>'


LBL = {"H1": "原版：PBR 最低 20%、空 0050 30%、每季", "V-P10": "PBR 最低 10%", "V-P30": "PBR 最低 30%",
       "V-H0": "空方 0%（純多，70% 多方＋30% 現金）", "V-H50": "空方 50%", "V-H70": "空方 70%（多空等額）",
       "V-MON": "每月換股", "V-TOP20": "前20日均額 ≥5,000 萬且 PBR 最低 20 檔", "V-LIQ": "前20日均額 ≥5,000 萬（不限檔數）",
       "V-QUAL": "近四季稅後純益 >0（以官方本益比有值判定）"}
TEN_H = ["組合", "條件", "樣本數", "平均報酬", "平均持有交易日數", "單筆資金周轉年化報酬（單利）", "勝率", "賠率 R", "凱利",
         "標準差", "t 值", "雙尾 p 值"]


def tenrow(r, lab=True):
    out = [r.combo, LBL.get(r.combo, "")] if lab else [r.combo]
    return out + [int(r.樣本數), Pc(r.平均報酬), Ff(r.平均持有交易日數, 1), Pc(r.單利年化), Pc(r.勝率), Ff(r.賠率R),
                  Ff(r.凱利, 3), Pc(r.標準差), Ff(r.t值), Gf(r.雙尾p)]


main_rows = [tenrow(r) + [Gf(r.holm)] for r in tt.rename(columns={"Holm p": "holm"}).itertuples()]
dd_rows = [[r.combo, Pc(r.最大回撤, 1), Pc(r.最差三次回撤平均, 1),
            f"{int(r.最長回撤期筆數)}筆（{int(r.最長回撤期日曆日):,}天）" + ("，未回復" if r.最長回撤期未回復 else "")] for r in dd.itertuples()]
L_rows = [tenrow(r) for r in L.itertuples()]
S_rows = [tenrow(r, lab=False) for r in Sx.itertuples()]
G_rows = [tenrow(r) + [int(r.聚合單位數), Gf(r.聚合p)] for r in G.itertuples()]
st_rows = [tenrow(r) for r in st.itertuples()]
nv_rows = [[r.combo, Pc(r.年化, 1), Pc(r.期末回撤最大, 1), Ff(r.平均持股數, 1), int(r.最少持股), Ff(r.期末淨值)] for r in nv.itertuples()]
PI = P[P["sample"] == "樣本內"]
ex = {}
for r in PI.itertuples():
    for _, w in r.excl:
        k = w.split("：")[0]; ex.setdefault(r.combo, {}).setdefault(k, 0); ex[r.combo][k] += 1
ex_cols = sorted({k for d in ex.values() for k in d})
ex_rows = [[c] + [ex.get(c, {}).get(k, 0) for k in ex_cols] + [int((cn.combo == c).sum())] for c in tt.combo]
cc = cn.groupby(["combo", "why"]).size().unstack(fill_value=0)
h1 = tt.set_index("combo").loc["H1"]; h0 = tt.set_index("combo").loc["V-H0"]; s50 = Sx.iloc[0]
q = tt.set_index("combo").loc["V-QUAL"]; lq = tt.set_index("combo").loc["V-LIQ"]; tp = tt.set_index("combo").loc["V-TOP20"]
flag_q = P[(P.combo == "H1") & P["flags"].notna()].entry_date.dt.date.astype(str).tolist()
flag_m = P[(P.combo == "V-MON") & P["flags"].notna()].entry_date.dt.date.astype(str).tolist()
code = "".join(f"<h3>{f}</h3><pre style='font-family:Courier New;font-size:8pt'>{E(open(f).read())}</pre>"
               for f in ["prep071.py", "sim071.py", "stats071.py", "sens071.py", "report071.py"])
CHECK = [
    ("A1 當時上市櫃身分", "適用｜通過", "listing_periods（官方逐日市場別）判定換股日身分"),
    ("A2 固定股數加實得現金", "適用｜通過", "framework.core.trade_return；0050 分割 2025-06 在樣本外，本次未用到"),
    ("A3 訊號資料時點", "適用｜通過", "官方每日淨值比即當日公布值；本益比同；訊號日收盤後判斷、次一交易日開盤成交"),
    ("A5 缺值不推估", "適用｜通過", "淨值比缺值或 ≤0 不納入；公司行動資料不足、期末無成交者剔除並列出"),
    ("A7 含已下市", "適用｜通過", "daily_k／listing_periods 含已下市；期末無成交者列缺口"),
    ("A11 回傳日期核對", "適用｜通過", "fetch_pbr.py 逐筆核對 date／title，月底 494 檔全部 ok"),
    ("A14 全額交割名單涵蓋", "適用｜通過", f"上市 {meta['FD_RANGE']['上市']['min']} 起、上櫃 {meta['FD_RANGE']['上櫃']['min']} 起；研究起點 2008-04-09 之後才有訊號"),
    ("B1/B2 不偷看", "適用｜通過", "選股只用訊號日資料；期間剔除只依資料缺口，不依報酬"),
    ("B3 市場交易日", "適用｜通過", "selfcheck 持有日與日曆一致"),
    ("B5 可交易性", "適用｜部分", "多方 L1（一價鎖、停牌、零量）；0050 L2：停券日已標記，強制回補未建模（D-071-…-2354-5）"),
    ("C1 bt_stats", "適用｜通過", "bt_stats 1.2（sha256 e99c85e9…20ee），selftest 與基準案例通過"),
    ("C7 持倉不重疊", "適用｜說明", "期報酬列為前後相接的開盤到開盤，前期出場＝後期進場同一開盤（設計如此）"),
    ("C15 例外照卡", "適用｜通過", "進場取消不遞補留現金；出場順延到第一個可成交開盤；未加入「再度入選取消賣出」"),
    ("D1/D5/D7 樣本外", "適用｜通過", "切點看報酬前凍結（sha256 5daf3f5f…）；快篩只用樣本內，selfcheck 通過"),
    ("E6 本表", "適用", "2026-11-12 交件前重讀防錯清單現行版"),
]
H = f"""<html><head><meta charset="utf-8"></head><body>
<h1>071 FinLab範例-低淨值比多空對沖｜V01 快篩報告</h1>
<p>Elon｜2026-11-12｜只用樣本內（進場日 ≤2020-06-30）；樣本外封存未開｜執行計畫修訂版 57、Elon 工作手冊 V31、研究預設口徑 V04（卡上 V03；本案用到的報酬口徑兩版相同）</p>
<h2>決策摘要</h2>
<p>① 結果：原版 H1 樣本內 {int(h1.樣本數)} 季，平均每季 {Pc(h1.平均報酬)}、勝率 {Pc(h1.勝率)}、R {h1.賠率R:.2f}、p {h1.雙尾p:.3f}；但 0050 放空腿本身每季平均 {Pc(s50.平均報酬)}（p {s50.雙尾p:.3f}），避險在拖累。不避險的 V-H0 平均 {Pc(h0.平均報酬)}、p {h0.雙尾p:.3f}。9 組變體 Holm 修正後最小 {Gf(tt['Holm p'].min())}，都不顯著。可執行版本（V-LIQ／V-TOP20，限成交金額 ≥5,000 萬）平均降到 {Pc(lq.平均報酬)}／{Pc(tp.平均報酬)}、p {lq.雙尾p:.2f}／{tp.雙尾p:.2f}，不顯著。</p>
<p>② 對 Ed 決策的影響：低淨值比效果在樣本內有、但不強（單組 p≈0.02，多重檢定後不成立），而且集中在成交冷清的小型股；原版平均每季要持有約 282 檔，實單無法照做。淨值比資料是新建、尚未驗收的 pbr-20261112m，結果不得作正式結論。</p>
<p>③ 要 Ed 選：結案、做正式策略包（開一次樣本外，建議組合見結論），或先做 E-Test（例如成交金額門檻 ≥2,000 萬＋品質濾網、空頭期才避險）。</p>
<h2>關卡一核准依據（引用決策紀錄）</h2>
<ul><li>D-071-20261104-1938-1｜關卡一｜V01｜Ed 原文「Ema 去重、發號，關卡一我已經同意」｜範圍：原版 H1、4.2 優化組、4.3 共通規則、6(d) 研究邊界（L1＋L2）｜Ema 對話 2026-11-04 19:38</li>
<li>D-071-20261104-1947-1｜可測性預檢｜「6(c) 全照建議」：季組合報酬為主、多方逐筆為輔；原版不設檔數上限；台指期避險組放第二階段；淨值比起點由 Elon 試取</li>
<li>D-071-20261111-2354-1～5｜可測性補正｜「都依照建議執行」：A 改用 elon-bt 共用資料層、官方每日淨值比加進共用層；B 研究起點 2008-04-09、切點依 6(d) 重算凍結；C 季組合報酬口徑；D 品質濾網；E 0050 放空腿 L2</li></ul>
<h2>資料來源、樣本期間與事件數</h2>
<ul><li>共用資料層標籤：{E(meta['tags'])}</li>
<li>淨值比：證交所 BWIBBU_d（2005-09-02 起）、櫃買 peQryDate（2007-01-02 起）官方每日原檔，GitHub Actions 抓取，每筆核對回傳日期；本版只含每月最後一個交易日（月底 255／239 個全部取得），其餘交易日下載中，不影響本案（只在月底／季底選股）。</li>
<li>股票池：換股日當時上市、上櫃普通股（四碼、非 91 存託憑證，含日後下市者）；排除當日變更交易（全額交割）／管理股票；淨值比缺值或 ≤0 不納入。分位數以當日全部有效值計算，多方取「低於分位數」者。</li>
<li>期間：研究起點 2008-04-09（上櫃變更交易名單起點，D-071-…-2354-2）。季換股訊號 2008-06-30～2020-03-31 共 48 季；月換股 146 個月。切點凍結：071_切點凍結紀錄_sha256-5daf3f5f.json（2026-11-11 23:57，看報酬前）。</li></ul>
<h2>進出場規則</h2>
<ul><li>每季（V-MON 每月）最後一個交易日收盤後判斷，次一交易日開盤調整：落選者賣出、新入選者買進、續選者續抱；多方調回等權，合計 70% 名目。空方放空 0050，名目 h（原版 30%）。</li>
<li>一期組合報酬＝0.7×多方等權報酬＋h×放空 0050 報酬；各腿自本期開盤到下期換股執行日開盤，依研究預設口徑「固定股數加實得現金」計算（放空補償股利）。進場取消的名額報酬計 0（留現金）。期中異常跳動、公司行動資料不足或期末無成交者，自該期多方平均剔除並逐筆列出（不以 0 代替）。</li>
<li>進場開盤漲停、停牌或無開盤成交取消、不遞補；出場開盤跌停或停牌順延到第一個可成交開盤。無停損。</li>
<li><b>未計入稅、交易成本、借券費與滑價。</b></li></ul>
<h2>策略卡主要組合：樣本內十項統計（一季組合報酬為一筆）</h2>
{table(TEN_H + ["Holm p（9 組變體）"], main_rows)}
<p>說明：H1 每季平均約 2.5%、p≈0.02，但 9 組變體做 Holm 修正後沒有一組顯著。改分位（10%、30%）結果差不多；空方比例越高、平均越低（0%→70%：3.07%→1.39%），因為樣本內 0050 長期上漲，放空腿是虧的。加流動性門檻後平均報酬砍半、不顯著。品質濾網（V-QUAL）勝率最高、p 最低。H1 等 9 組少 1 季：2008Q4 的 0050 放空腿碰到共用資料層跳動旗標（見注意事項 2），該季列未完成；V-H0 不用空方，所以是 48 季。</p>
<h2>回撤三項（等風險法，只供策略間比較）</h2>
{table(["組合", "最大回撤", "最差三次回撤平均", "最長回撤期"], dd_rows)}
<p>說明：一季一筆、每筆部位依標準差縮放，所以回撤數字小；最長回撤期以季數計，流動性組長達 25～28 季（6～7 年）。回撤三項不代表帳戶實際回撤。</p>
<h2>報酬拆解</h2>
<h3>多方腿（每期多方等權報酬，未乘 0.7）</h3>
{table(TEN_H, L_rows)}
<h3>0050 放空腿（每期）</h3>
{table(["組合", "樣本數", "平均報酬", "平均持有交易日數", "單筆資金周轉年化報酬（單利）", "勝率", "賠率 R", "凱利", "標準差", "t 值", "雙尾 p 值"], S_rows)}
<h3>多方持有段（一檔從入選到落選為一筆，聚合單位＝進場日）</h3>
{table(TEN_H + ["聚合單位數", "聚合p"], G_rows)}
<p>說明：多方本身強（持有段平均持有約一年多、聚合 p 都 &lt;0.05），但放空 0050 每季平均虧 {Pc(-s50.平均報酬)}。持有段 |報酬| ≥100% 的長抱個案存在（自檢 WARN，非百分數誤植）。</p>
<h2>描述性組合淨值（期報酬連乘，只供與 FinLab 對照，不取代十項統計）</h2>
{table(["組合", "年化報酬", "最大回撤（期末）", "平均持股數", "最少持股", "期末淨值"], nv_rows)}
<h2>對照：2008Q4 0050 放空腿照實計算</h2>
{table(TEN_H, st_rows)}
<p>說明：把 2008Q4 的 0050 放空腿照實計算後，H1 平均略降到 {Pc(st.set_index('combo').loc['H1','平均報酬'])}（該季多方大跌、放空腿的獲利補不回），結論不變。只作對照，不取代主表。</p>
<h2>排除與取消（樣本內，期×檔）</h2>
{table(["組合"] + ex_cols + ["進場取消"], ex_rows)}
<p>進場取消原因：{E('；'.join(f'{k}：' + '、'.join(f'{w} {int(n)}' for w, n in r.items() if n) for k, r in cc.iterrows()))}。</p>
<h2>名詞說明</h2>
<ul><li>一期組合報酬：本期換股執行日開盤到下期換股執行日開盤；平均持有交易日數含首尾。</li>
<li>持有段：一檔從入選買進到落選賣出。聚合 p：同一進場日的報酬先平均，再對各日平均做 t 檢定。</li>
<li>單筆資金周轉年化＝平均報酬×252÷平均持有交易日數，不等於帳戶年化。</li></ul>
<h2>尚未測試的範圍</h2>
<ul><li>台指期避險組：依 D-071-20261104-1947-1 放第二階段。</li>
<li>合併組（卡 4.3）：樣本內優於原版的設定為 V-P10（最低 10%）、V-H0（不避險）、V-QUAL；建議在正式策略包再做。</li>
<li>樣本外（進場日 ≥2020-10-01）封存未開。</li></ul>
<h2>注意事項</h2>
<ol><li>淨值比標籤 pbr-20261112m 是新建、未送驗收（只含月底），結果標「未驗收」，不得作正式結論；全量版下載完成後送 Eve 驗收。</li>
<li>共用資料層 r72 在 2008-10-13～24（跌幅 3.5% 期間）有 8 列跳動旗標疑為規則推算捨入差一檔（例：0050 2008-10-16 推算跌停 39.16、官方成交 39.15），影響本案 2008Q4 放空腿與少數多方期報酬；已另列對照，資料層問題回報 Ed／Eve，不在本案自行修改。</li>
<li>0050 放空腿可交易性（L2）：進場日落在停券期間 季 {len(flag_q)} 次（{', '.join(flag_q)}）、月 {len(flag_m)} 次（{', '.join(flag_m)}）；收益分配前強制回補未建模，實務要靠借券或台指期，未驗證、留待小部位實單驗證。</li>
<li>V-QUAL 以官方本益比有值判定「近四季稅後純益 >0」（官方：每股稅後純益 ≤0 不計算本益比），未用 fin-20261107（Eve 2026-11-11 已退回）；與卡上「近四季稅後淨利」的差異：官方用每股稅後純益，正負號相同。這是 D-071-…-2354-4 之外的實作選擇，請 Ed 確認。</li>
<li>原版每期平均持有約 282 檔（最少 230 檔），實單無法照做；報酬主要來自成交冷清的小型股。</li></ol>
<h2>防錯清單逐條對照（E6）</h2>
{table(["條目", "適用／結果", "證據"], CHECK)}
<h2>結論</h2>
<p><b>建議先由 Ed 決定方向，Elon 的建議是做正式策略包、開一次樣本外</b>：組合為 H1、V-H0、V-P10、V-QUAL 與合併組（V-P10＋V-H0＋V-QUAL），其餘 6 組照卡紀律一併開樣本外列出。理由：單組 p≈0.02、方向一致，但多重檢定後不顯著，只有樣本外能回答是不是運氣；同時要有心理準備，原版持股太多、可執行版本不顯著，即使樣本外通過，可交易性仍是主要風險。若 Ed 認為可執行性不足，就直接結案。快篩結果不得作為交易依據。</p>
<h2>附錄：程式</h2>
<p>程式也在 GitHub elon-bt／experiments/071/quick（含切點凍結紀錄）。共用統計函式 bt_stats 1.2（sha256 e99c85e9…20ee，selftest 與技能基準案例皆通過）只註明版本，不貼本體；出表與自檢用 elon-backtest 技能 elon_tools.py；報酬與交易日曆用 elon-bt framework.core；淨值比下載與建置程式見 elon-bt data_layer/fetch_pbr.py、build_pbr.py。selfcheck（交易日曆、切點、重算一致、回撤重算）全部通過；WARN 2 項已於上文說明（期報酬前後相接、長抱持有段 |報酬|≥100%）。</p>
{code}
</body></html>"""
open("071_快篩報告.html", "w", encoding="utf-8").write(H)
print(len(H))
