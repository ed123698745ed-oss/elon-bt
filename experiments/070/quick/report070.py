"""070 快篩報告（HTML → Google 文件）。"""
import html, pickle, sys
import numpy as np, pandas as pd
sys.path.insert(0, "."); sys.path.insert(0, "/home/claude/elon-bt")
from elon_tools import to_markdown

tt = pd.read_pickle("card_ten.pkl"); dd = pd.read_pickle("card_dd.pkl"); nv = pd.read_pickle("nav070.pkl")
t = pd.read_pickle("trades070_full.pkl"); c = pd.read_pickle("cancels070.pkl")
meta = pickle.load(open("meta070.pkl", "rb")); nsel = pickle.load(open("nsel070.pkl", "rb"))
P = lambda v, d=2: "N/A" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v*100:.{d}f}%"
G = lambda v: "N/A" if v is None or (isinstance(v, float) and np.isnan(v)) else (f"{v:.2e}" if abs(v) < 1e-3 else f"{v:.4f}")
E = html.escape


def table(head, rows):
    h = "".join(f"<th>{E(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{E(str(x))}</td>" for x in r) + "</tr>" for r in rows)
    return f'<table border="1" cellpadding="3" style="border-collapse:collapse;font-size:9pt"><tr>{h}</tr>{b}</table>'


LBL = {"Q1": "原版：市值<100億、FCF4季>0、ROE>0、營業利益年增>0、市值÷近4月營收<5、月換股",
       "V-CAP50": "市值上限 50 億", "V-CAP200": "市值上限 200 億", "V-PR3": "市值營收比 <3", "V-PR8": "市值營收比 <8",
       "V-REV3": "營收分母近 3 個月", "V-TOP10": "持股上限 10 檔（市值營收比低→高）", "V-QTR": "每季換股（財報期限次一交易日）",
       "V-LIQ2000萬": "前20日均成交金額 ≥2,000 萬", "V-LIQ5000萬": "前20日均成交金額 ≥5,000 萬"}
ten_rows = [[r.combo, LBL[r.combo], f"{int(r.樣本數):,}", P(r.平均報酬), f"{r.平均持有交易日數:.1f}", P(r.單利年化), P(r.勝率),
             f"{r.賠率R:.2f}", f"{r.凱利:.3f}", P(r.標準差), f"{r.t值:.2f}", G(r.雙尾p), int(r.聚合單位數), G(r.聚合p), G(r.Holm聚合p)]
            for r in tt.itertuples()]
dd_rows = []
for r in dd.itertuples():
    lab = f"{int(r.最長回撤期筆數):,}筆（{int(r.最長回撤期日曆日):,}天）" + ("，未回復" if r.最長回撤期未回復 else "")
    dd_rows.append([r.combo, P(r.最大回撤, 1), P(r.最差三次回撤平均, 1), lab, f"註：{int(r.最長回撤期筆數)} 筆＝{int(r.最長回撤期聚合單位數)} 個進場日" if r.需註記 else ""])
nav_rows = [[r.combo, P(r.年化報酬, 1), P(r.最大回撤, 1), f"{r.平均持股數:.1f}", f"{r.年換手率:.2f}", f"{r.期末淨值:.2f}"] for r in nv.itertuples()]
exc = t[t.excluded_reason.notna()].copy()
exc["類別"] = exc.excluded_reason.str.replace(r"：.*", "", regex=True)
ex_rows = [[k, *[int(v) for v in g.values]] for k, g in exc.groupby("combo")["類別"].value_counts().unstack(fill_value=0).iterrows()]
ex_head = ["組合", *list(exc.groupby("combo")["類別"].value_counts().unstack(fill_value=0).columns)]
cc = c.groupby(["combo", "why"]).size().unstack(fill_value=0)
q1 = tt.set_index("combo").loc["Q1"]
code = "".join(f"<h3>{f}</h3><pre style='font-family:Courier New;font-size:8pt'>{E(open(f).read())}</pre>"
               for f in ["prep070.py", "sim070.py", "stats070.py", "nav070.py", "report070.py"])
H = f"""<html><head><meta charset="utf-8"></head><body>
<h1>070 FinLab範例-小資族優等生｜V01 快篩報告</h1>
<p>Elon｜2026-11-11｜只用樣本內（換股日 ≤ 2022-06-30）；樣本外封存未開｜執行計畫修訂版 57、Elon 工作手冊 V31、研究預設口徑 V04</p>
<h2>決策摘要</h2>
<p>① 結果：原版 Q1 樣本內 {int(q1.樣本數):,} 筆持有段，平均 {P(q1.平均報酬)}、平均持有 {q1.平均持有交易日數:.1f} 個交易日、單利年化 {P(q1.單利年化)}、勝率 {P(q1.勝率)}、R {q1.賠率R:.2f}、聚合 p {G(q1.聚合p)}（96 個進場日）；10 組全部顯著。但加流動性門檻後平均報酬掉到 4.2%（≥2,000 萬）與 3.5%（≥5,000 萬），報酬有一大塊來自成交冷清的小型股。</p>
<p>② 對 Ed 決策的影響：效果強而穩，值得做正式策略包開樣本外；但財報、月營收是 FinMind 現行修訂值（時點未驗證），平均每月持股約 170 檔、多數成交冷清，實單可執行性是主要風險。</p>
<p>③ 要 Ed 選：要不要做正式策略包；若做，送樣本外的組合範圍（建議全部 10 組＋1 組合併組），以及是否要另做「流動性＋持股上限」的 E-Test（例如 ≥2,000 萬且前 10 檔）。</p>
<h2>關卡一核准依據（引用決策紀錄）</h2>
<ul><li>D-070-20261104-1938-1｜關卡一｜V01｜Ed 原文「Ema 去重、發號，關卡一我已經同意」｜範圍：原版 Q1、4.2 優化組、4.3 共通規則、6(d) 研究邊界（L1；樣本內換股日 ≤2022-06-30、隔離帶 2022-07-01～09-30、樣本外 ≥2022-10-01）｜Ema 對話 2026-11-04 19:38</li>
<li>D-070-20261104-1947-1｜可測性預檢｜「6(c) 全照建議」：營收分母原版 4 個月、排除金融保險業、財報 2013 IFRS 起、訊號 2014-05-15 起、一筆交易＝連續持有段、列描述性組合淨值</li>
<li>D-070-20261111-1014-1～4｜可測性補正｜「照建議」：A 改用 elon-bt 共用資料層；B 財報期限次一交易日、月營收 10 日之後第一個交易日起可用；C 市值股數＝普通股股本÷面額（預設 10 元）；D CB 變體不跑</li>
<li>D-070-20261111-1424-1｜其他｜「甲」：現金流量表、上櫃變更交易、產業別加進共用資料層</li></ul>
<h2>資料來源、樣本期間與事件數</h2>
<ul><li>共用資料層標籤：{E(meta['tags'])}</li>
<li>價格與公司行動用 data-20261110r72（2026-11-10 已驗收，開工時最新驗收標籤；D-070-…-1014-1 寫的是 r68，r72 為其後經 Eve 驗收的修正版，減資恢復日參考價已更正）。</li>
<li>樣本：上市櫃普通股（四碼、非 91 存託憑證），含已下市；排除變更交易／管理股票（上市 {meta['FD_START'].get('上市')} 起、上櫃 {meta['FD_START'].get('上櫃')} 起，皆早於訊號起點）、金融保險業（現行產業別 {meta['n_fin']} 檔；查無產業別 {meta['n_ind_unknown']} 檔多為已下市，金融業者因無營業利益科目不會通過營業利益年增條件）、面額未驗證 {len(meta['PAR_BAD_LIST'])} 檔（{', '.join(map(str, meta['PAR_BAD_LIST']))}：EPS 反推股數與股本÷10 不符，不推估面額）。</li>
<li>期間：第一個換股日 2014-05-30，最後 2022-05-31；月換股 97 次、季換股 33 次。跨越樣本內切點仍持有的持有段不列入任一段。</li></ul>
<h2>進出場規則</h2>
<ul><li>每月最後一個交易日收盤後判斷（V-QTR：財報期限次一交易日收盤後），次一交易日開盤先賣後買；續選者續抱，一檔從入選到落選算一筆。等權、無停損。</li>
<li>條件（全部用換股日當時已可用資料）：市值＝換股日未還原收盤×普通股股本÷10；近 4 季自由現金流（營業＋投資現金流，年內累計先轉單季）合計 &gt;0；單季繼續營業單位淨利 &gt;0 且權益總額 &gt;0；單季營業利益年增 &gt;0（去年同季 ≤0 不計算、不納入）；市值÷近 4 個月營收 &lt;5（缺任一月不納入）。</li>
<li>進場開盤漲停、停牌或無開盤成交取消不遞補；出場開盤跌停或停牌順延到第一個可成交開盤。報酬依研究預設口徑 V04「固定股數加實得現金」，價位判斷用未還原價。</li>
<li><b>未計入稅、交易成本與滑價。</b></li></ul>
<h2>策略卡主要組合：樣本內十項統計</h2>
{table(["組合","條件","樣本數","平均報酬","平均持有交易日數","單筆資金周轉年化報酬（單利）","勝率","賠率 R","凱利","標準差","t 值","雙尾 p 值","聚合單位數（進場日）","聚合p","Holm 聚合p"], ten_rows)}
<p>說明：10 組平均報酬都在 3.5%～13% 之間、聚合 p 都 &lt;0.01，Holm 修正後（家族＝9 組優化變體）仍全部顯著。改市值上限、市值營收比門檻、營收分母，結果幾乎不動，代表效果不是某個門檻剛好挑出來的。每季換股平均報酬最高（13.0%），因為持有更久；單利年化看起來差不多（約 23%～28%）。最大落差在流動性：只留成交金額夠大的股票，平均報酬砍半以上、勝率掉到 43%～46%。限制：逐筆 p 很小部分是因為筆數多，結論以聚合 p 為準；同一進場日上百筆高度相關，聚合 p 仍可能偏樂觀。</p>
<h2>回撤三項（等風險法，只供策略間比較）</h2>
{table(["組合","最大回撤","最差三次回撤平均","最長回撤期","註記"], dd_rows)}
<p>說明：原版最大回撤約 9%，季換股最低（3.8%）；流動性組回撤最大、最長回撤期超過 900 天。回撤三項不代表帳戶實際回撤。</p>
<h2>描述性等權組合淨值（只供與 FinLab 對照，不取代十項統計）</h2>
{table(["組合","年化報酬","最大回撤","平均持股數","年換手率","期末淨值"], nav_rows)}
<p>說明：價格用時點一致調整價（隱含股利再投入），開盤取消與落選的資金留現金；原版每月平均要持有約 171 檔，實務上無法照做。持股上限 10 檔年化最高但回撤也最深（約 36%）。</p>
<h2>排除與取消</h2>
{table(ex_head, ex_rows)}
<p>進場取消：{E(', '.join(f'{k}：' + '、'.join(f'{w} {int(n)}' for w, n in r.items() if n) for k, r in cc.iterrows()))}。公司行動資料不足者列未完成，不推估報酬。</p>
<h2>名詞說明</h2>
<ul><li>持有段：一檔股票從入選買進到落選賣出；平均持有交易日數含首尾。</li><li>聚合 p：同一進場日（換股執行日）的報酬先平均，再對各日平均做單樣本 t 檢定。</li><li>單筆資金周轉年化＝平均報酬×252÷平均持有交易日數，不等於帳戶年化。</li></ul>
<h2>尚未測試的範圍</h2>
<ul><li>合併組（卡 4.3：各參數族樣本內最好且優於原版的設定合併）尚未跑，建議正式策略包再做；「有發行 CB」變體依 D-070-…-1014-4 不跑。</li>
<li>樣本外（換股日 ≥2022-10-01）封存未開。</li></ul>
<h2>注意事項</h2>
<ol><li>財報（fin-20261107）、現金流量表與產業別（fincf-20261111）、月營收（revinst-20261111）都是未送驗收的 FinMind 現行修訂值，不是公告當時版本，結果標「時點未驗證」，不得作正式結論。</li>
<li>報酬大部分來自成交冷清的小型股（流動性組平均報酬砍半），可交易性只做到 L1（一價鎖、停牌、零量），開盤價能否買到實際量未驗證，留待小部位實單驗證。</li>
<li>面額：共用層面額變更紀錄只有 35 筆、多為 ETF；以 EPS 反推偵測到 2 檔面額不符者已排除，其餘非 10 元面額但未被偵測到者可能高估或低估市值。</li>
<li>產業別是現行分類回溯；已下市公司多數查無產業別。</li></ol>
<h2>結論</h2>
<p><b>建議做正式策略包</b>：10 組全部列入、開樣本外，另補合併組；並建議加做流動性＋持股上限的 E-Test，因為原版雖然強，但持股數與流動性讓它很難實單照做。快篩結果不得作為交易依據。</p>
<h2>附錄：程式</h2>
<p>程式也在 GitHub elon-bt／experiments/070/quick（含 freeze_split.json 切點凍結紀錄）。共用統計函式 bt_stats 1.2（sha256 e99c85e9…20ee，selftest 與技能基準案例皆通過）只註明版本，不貼本體；出表與自檢用 elon-backtest 技能 elon_tools.py；報酬與交易日曆用 elon-bt framework.core。自檢（selfcheck，含交易日曆、切點、重算一致）全部通過。</p>
{code}
</body></html>"""
open("070_快篩報告.html", "w", encoding="utf-8").write(H)
print(len(H))
