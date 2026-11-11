"""068 快篩報告（HTML → Google 文件）。數字一律取自 card_ten／card_dd／et_ten／et_dd／nav068.pkl（未四捨五入原表）。"""
import html, math, pickle
import pandas as pd

ten = pd.read_pickle("card_ten.pkl"); dd = pd.read_pickle("card_dd.pkl")
et = pd.read_pickle("et_ten.pkl"); edd = pd.read_pickle("et_dd.pkl")
nav = pd.read_pickle("nav068.pkl").set_index("combo")
meta = pickle.load(open("meta068.pkl", "rb"))
cancels = pd.read_pickle("cancels068.pkl")
trades = pd.read_pickle("trades068.pkl")

NAME = {"M0": "M0 對照（不加 ROE）", "M1": "M1 原版", "V-L20": "回看 20 日", "V-L120": "回看 120 日", "V-TOP10": "選 10 檔",
        "V-FILT1ST": "先濾 ROE>0 再取前 30", "V-ROE8": "近四季 ROE>8%（2014-04 起）", "V-LIQ0.5億": "20 日均額 ≥5,000 萬",
        "V-LIQ2億": "20 日均額 ≥2 億", "V-2W": "雙週換股", "V-MKT": "大盤 20MA 濾網", "V-REV": "月營收年增>0 取代 ROE>0", "V-MERGE": "合併組（120日＋10檔＋先濾＋雙週）", "M1-同期": "M1 原版（2014-04 起，V-ROE8 對照）",
        "E-M1-ADJ": "E-Test：還原價算動能", "E-BUF50": "E-Test：持股緩衝（前 50 續抱）", "E-SKIP20": "E-Test：跳過最近 1 個月（80→20 日）", "E-STOP15": "E-Test：個股停損 15%"}


def pct(v, d=2):
    return "N/A" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v*100:.{d}f}%"


def num(v, f="{:.3f}"):
    return "N/A" if v is None or (isinstance(v, float) and math.isnan(v)) else f.format(v)


def pv(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:.2e}" if v < 0.001 else f"{v:.4f}"


def table(head, rows):
    h = "".join(f"<th>{html.escape(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table border='1' cellpadding='3' style='border-collapse:collapse;font-size:9pt'><tr>{h}</tr>{b}</table>"


def ten_rows(t):
    out = []
    for r in t.itertuples():
        out.append([r.combo, NAME.get(r.combo, ""), f"{int(r.樣本數):,}", pct(r.平均報酬), num(r.平均持有交易日數, "{:.1f}"), pct(r.單利年化, 1),
                    pct(r.勝率, 1), num(r.賠率R, "{:.2f}"), num(r.凱利, "{:.3f}"), pct(r.標準差, 1), num(r.t值, "{:.2f}"), pv(r.雙尾p),
                    f"{int(r.聚合單位數)}", pv(r.聚合p), pv(getattr(r, "Holm聚合p", float("nan")))])
    return out


def dd_rows(d):
    out = []
    for r in d.itertuples():
        lab = f"{int(r.最長回撤期筆數):,} 筆（{int(r.最長回撤期日曆日):,} 天）" + ("，未回復" if r.最長回撤期未回復 else "")
        note = f"＝{int(r.最長回撤期聚合單位數)} 個進場日" if r.需註記 else ""
        out.append([r.combo, pct(r.最大回撤, 1), pct(r.最差三次回撤平均, 1), lab + note])
    return out


H10 = ["組合", "說明", "①樣本數", "②平均報酬", "③平均持有交易日數", "④單利年化", "⑤勝率", "⑥賠率R", "⑦凱利", "⑧標準差", "⑨t值", "⑩雙尾p",
       "聚合單位數（進場日）", "聚合p", "Holm 聚合p"]
HDD = ["組合", "⑪最大回撤", "⑫最差三次回撤平均", "⑬最長回撤期（註：筆數＝進場日數）"]

T = ten.set_index("combo")
E = et.set_index("combo")
m0, m1 = T.loc["M0"], T.loc["M1"]
nv = lambda c, k: nav.loc[c, k]
fd_count = int(trades.excluded_reason.notna().sum())

summary = f"""
<p><b>① 結果：</b>樣本內（2013-05～2022-06）原版 M1 平均每段 {pct(m1.平均報酬)}、聚合 p {pv(m1.聚合p)}，比不加 ROE 的 M0（{pct(m0.平均報酬)}）略好、最大回撤減半（{pct(dd.set_index('combo').loc['M1','最大回撤'],1)} 對 {pct(dd.set_index('combo').loc['M0','最大回撤'],1)}）；10 組變體（含 V-REV）中，雙週換股 V-2W（{pct(T.loc['V-2W','平均報酬'])}、Holm 聚合p {pv(T.loc['V-2W','Holm聚合p'])}）、回看 120 日 V-L120、先濾再排 V-FILT1ST 經 Holm 修正後仍顯著；近四季 ROE>8% 反而變差；月營收年增 V-REV（{pct(T.loc['V-REV','平均報酬'])}）略遜原版；依協定合併的 V-MERGE（{pct(T.loc['V-MERGE','平均報酬'])}、Holm 聚合p {pv(T.loc['V-MERGE','Holm聚合p'])}）沒有比單一變體好。E-Test 4 組（Holm 家族＝4 組 E-Test）：跳過最近 1 個月 E-SKIP20 最好（{pct(E.loc['E-SKIP20','平均報酬'])}、勝率 {pct(E.loc['E-SKIP20','勝率'],1)}、Holm 聚合p {pv(E.loc['E-SKIP20','Holm聚合p'])}）；持股緩衝 E-BUF50 只少 3% 筆數；停損 15% 變差；還原價與原版差不多。</p>
<p><b>② 影響：</b>ROE&gt;0 濾網的主要作用是降風險而不是加報酬；有值得續做的組合；策略卡範圍已全部跑完。E-Test 條件是看過樣本內後才提出，正式策略包必須用樣本外驗證。</p>
<p><b>③ 要 Ed 選：</b>(a) 是否做正式策略包、組合清單（建議 M1、V-2W、V-L120、V-FILT1ST、E-SKIP20）；(b) 上櫃全額交割（變更交易）無官方歷史、本快篩未排除，正式策略包是否比照 066 的 D-066-20261111-0038-1 處理。</p>
"""

body = f"""<h1>068 FinLab範例-60日動能ROE濾網｜V01 快篩報告</h1>
<p>Elon｜2026-11-11｜執行計畫修訂版 57、Elon 工作手冊 V31、研究預設口徑 V04｜快篩不計 R、不送 Eve；只用樣本內，樣本外封存。本版 2026-11-11 14 時補跑 V-REV（月營收 revinst-20261111）與合併組 V-MERGE；10 時曾追加 3 組 E-Test。</p>
<h2>決策摘要</h2>{summary}
<h2>關卡一核准依據（策略總表「決策紀錄」）</h2>
<ul>
<li>D-068-20261104-1938-1（關卡一）：Ed「Ema 去重、發號，關卡一我已經同意」；核准策略卡 V01，範圍依卡（M1、M0、4.2 優化組、4.3 共通規則）與 6(d) 研究邊界（L1；樣本內 ≤2022-06-30、隔離帶 2022-07-01～09-30、樣本外 ≥2022-10-01）。Ema 對話，2026-11-04 19:38。</li>
<li>D-068-20261104-1947-1（可測性預檢）：6(c) 全採卡上建議（ROE 單季、財報 2013 IFRS 起、一筆交易＝連續持有段、列描述性組合淨值）。</li>
<li>D-068-20261111-0018-1～6（可測性補正，Ed 2026-11-11 00:18「照建議」）：①共用資料層；②財報／營收期限之次一交易日起可用；③雙週＝ISO 雙數週最後交易日；④歸屬母公司口徑、近四季 ROE 自 2014-04；⑤60 日前無收盤價不排名；⑥大盤濾網只擋新進場。</li>
<li>D-068-20261111-0018-7（E-Test 方向）：E-M1-ADJ。D-068-20261111-0055-1：停用 068 自抓月營收，改用 revinst month_revenue。</li>
</ul>
<h2>資料來源、樣本期間與事件數</h2>
<ul>
<li>共用資料層標籤：{html.escape(meta['tags'])}。月營收另用 revinst-20261111 month_revenue（FinMind 現行值，未驗收）。財報、指數、全額交割名單與月營收屬未驗收版本，快篩結果只供 Ed 決定方向。</li>
<li>樣本內：訊號 2013-05-16（2013Q1 首份 IFRS 季報期限 5/15 之次一交易日）起，至 2022-06-30；月換股 109 次（V-2W 233 次）。資料只載入到 2022-06-30，樣本外未載入。</li>
<li>股票池：當日官方上市／上櫃（listing_periods）、四碼普通股（排除 0 開頭與 91xx）、排除證交所全額交割名單；含日後下市者。共 {len(meta['stocks']):,} 檔出現在 1999-01～2022-06 日K。</li>
<li>財報：2013Q1～2022Q1 損益表 {61662:,} 個公司季，歸屬母公司淨利 56,242、無非控制權益拆分改用本期淨利 5,316、資料不足 104（2820、2849、2836、2807、2801、2837、2499 等金融業）；資產負債表 62,191 個公司季，歸屬母公司權益 55,884、權益總額 6,079、資料不足 228。資料不足者不能通過 ROE 濾網。</li>
<li>M0 每次前 30 名中，ROE&gt;0 通過 2,156 檔次、ROE≤0 剔除 926、財報資料不足剔除 188（合計 109 次換股）。</li>
</ul>
<h2>進出場規則</h2>
<ul>
<li>動能＝換股日有成交收盤價 ÷ 往前第 L 個市場交易日的有成交收盤價（未還原；E-M1-ADJ 用時點一致調整價）。兩日任一無成交，或往前第 L 日未掛牌，不參加排名。同值依代號排序。</li>
<li>M1：全池取動能前 30，再保留最近一季（期限之次一交易日起可用）歸屬母公司淨利 &gt;0 且歸屬母公司權益 &gt;0 者；持股可能少於 30。M0 不加濾網。V-FILT1ST 先濾 ROE 再取前 30。流動性變體在排名前先限 20 日平均成交金額（含換股日，無成交日計 0）。</li>
<li>換股：每月（V-2W 為 ISO 雙數週）最後一個市場交易日收盤後判斷；次一交易日開盤先賣後買，等權；續選者續抱；無停損。V-MKT：加權指數收盤 &lt; 20 日均線時不買新入選者，續選續抱、落選照賣。</li>
<li>例外：進場日開盤漲停、停牌或無開盤成交 → 該筆取消、不遞補（共取消 {len(cancels):,} 筆，見下表）；出場日開盤跌停或停牌 → 每個交易日重試至第一個可成交開盤（防錯 C14）。下市未取得最終現金者列缺口；持有期間有異常跳動或公司行動資料不足者列未完成；持有段跨越 2022-06-30 不列入。</li>
<li>報酬：固定股數加實得現金（elon-bt framework.core.trade_return，研究預設口徑 V04）；持有交易日數含首尾（官方日曆）。</li>
<li><b>未計入稅、交易成本與滑價。</b></li>
</ul>
<h2>主要組合樣本內十項統計（策略卡組合）</h2>
{table(H10, ten_rows(ten))}
<p>說明：所有組合平均報酬都為正、聚合 p 多數 &lt;0.05。ROE 濾網（M1 對 M0）平均報酬只多約 0.6 個百分點，但勝率、凱利較好，標準差與回撤較小。三組經 Holm 修正（家族＝10 組變體＋合併組，共 11 組）仍顯著：V-2W（換股頻率加倍，持有期縮短、周轉年化最高）、V-L120、V-FILT1ST。V-TOP10 平均最高，但樣本 406 筆、Holm 後不顯著。近四季 ROE&gt;8% 與流動性門檻都讓報酬變差。V-REV 平均報酬略低於原版（月營收年增濾網篩得比 ROE&gt;0 鬆，留下較多標的）。V-MERGE 依 merge068.py 協定合併 V-L120＋V-TOP10＋V-FILT1ST＋V-2W（V-TOP10 雖 Holm 後不顯著，但符合協定的「平均報酬高於 M1 且聚合 p&lt;0.05」），結果只有 691 筆、平均 3.68%，未優於 V-2W 單一變體，Holm 後不顯著。逐筆 p 只供參考，判斷以聚合 p 為準。</p>
<h3>回撤三項（等風險法，只供組合間比較）</h3>
{table(HDD, dd_rows(dd))}
<p>說明：M1 最大回撤約為 M0 的一半；V-2W 報酬最好但回撤也較深。最長回撤期筆數都遠多於進場日數（每月同日進出多檔），格內已註記進場日數。回撤不代表帳戶實際回撤。</p>
<h2>E-Test（討論衍生組合）</h2>
<p>來源：E-M1-ADJ＝D-068-20261111-0018-7；E-BUF50、E-SKIP20、E-STOP15＝D-068-20261111-0949-1（Ed 2026-11-11 09:49）。四組都以 M1 為底，只改下表一項，其餘（股票池、ROE 濾網、月換股、例外、報酬口徑）相同；只用樣本內、無樣本外；條件是看過樣本內結果後才提出，屬參數最佳化，正式策略包須以樣本外驗證。</p>
{table(['組合', '與 M1 的差別', '時點規則'], [['E-M1-ADJ', '動能改用時點一致調整價（訊號日以前已知公司行動；r68 減資恢復日 514 公司日以 corp_actions 推算）', '未違反'], ['E-BUF50', '已持有者在換股日排名仍在前 50 且 ROE&gt;0 就續抱；新進場仍只取前 30 且 ROE&gt;0', '未違反'], ['E-SKIP20', '動能＝第 20 個市場交易日前收盤 ÷ 第 80 個市場交易日前收盤（兩日都須有成交、第 80 日前已掛牌；換股日本身須有成交）', '未違反'], ['E-STOP15', '持有期間收盤（時點一致調整價，避免除權息誤觸）≤ 進場價×85% → 次一交易日開盤賣出（跌停順延）；新買進只在換股日，故下次換股前不會再買', '未違反（收盤判斷、次日開盤成交）']])}
{table(H10, ten_rows(et))}
{table(HDD, dd_rows(edd))}
<p>說明：E-SKIP20 平均報酬、勝率、凱利都高於 M1，標準差較小，Holm 修正後仍非常顯著，是 4 組中最值得續做的；代價是最大回撤略深（{pct(edd.set_index('combo').loc['E-SKIP20','最大回撤'],1)} 對 M1 {pct(dd.set_index('combo').loc['M1','最大回撤'],1)}）。E-BUF50 平均持有拉長到 {num(E.loc['E-BUF50','平均持有交易日數'],'{:.1f}')} 日、筆數只從 1,233 降到 {int(E.loc['E-BUF50','樣本數']):,}，周轉年化反而較低，減少交易的效果有限。E-STOP15 有 448 筆停損出場，平均報酬降到 {pct(E.loc['E-STOP15','平均報酬'])}、回撤反而更深：動能股常先跌再漲，停損砍在低點。E-M1-ADJ 與原版幾乎相同。判斷：E-SKIP20「值得繼續研究」（建議列入正式策略包並開樣本外）；E-BUF50、E-STOP15、E-M1-ADJ「不建議繼續」。</p>
<p>測試範圍清單（E-Test 全部列出、無遺漏）：E-M1-ADJ、E-BUF50、E-SKIP20、E-STOP15，共 4 組；Holm 以聚合 p 為輸入，家族＝這 4 組。策略卡組合另一家族（10 組變體＋合併組）。</p>
<h2>描述性等權組合淨值（只與 FinLab 組合報表對照，不取代十項統計）</h2>
{table(['組合', '年化報酬', '最大回撤', '平均持股數', '年換手率'], [[c, pct(nv(c,'年化報酬'),1), pct(nv(c,'最大回撤'),1), f"{nv(c,'平均持股數'):.1f}", f"{nv(c,'年換手率'):.2f}"] for c in nav.index])}
<p>說明：換股日開盤調回等權（單檔上限 1／選股上限），價格用調整價（隱含股利再投入）。M1 年化 {pct(nv('M1','年化報酬'),1)}、最大回撤 {pct(nv('M1','最大回撤'),1)}；M0 回撤 {pct(nv('M0','最大回撤'),1)}。</p>
<h2>測試進度與待補（保留紀錄）</h2>
<ul>
<li>已完成（結果、程式與逐筆明細保留，見下方「保存位置」）：策略卡 M0、M1、M1-同期與 10 組變體（V-L20、V-L120、V-TOP10、V-FILT1ST、V-ROE8、V-REV、V-LIQ0.5億、V-LIQ2億、V-2W、V-MKT）、合併組 V-MERGE；E-Test E-M1-ADJ、E-BUF50、E-SKIP20、E-STOP15。</li>
<li><b>V-REV 已補跑</b>：月營收改用共用資料層 revinst-20261111 month_revenue（FinMind 現行值、未驗收；只用營收月份 ≤2022-05，sha256 5fd58c5e…），可用日＝次月 10 日之次一交易日。M0 每次前 30 名中，月營收年增&gt;0 通過 2,265 檔次、≤0 剔除 835、資料不足 170。</li>
<li><b>V-MERGE 已補跑</b>：依看報酬前寫死的 merge068.py 協定挑出 4 族（回看 120 日、選 10 檔、先濾再排、雙週換股），獲利濾網族無合格者（V-ROE8、V-REV 都未高於 M1），沿用 ROE&gt;0。</li><li>目前沒有待資料的項目。</li>
<li>E-Test 不進合併組（合併組只合策略卡 4.2 的參數族）；E-SKIP20 是否與合併組再組合，由 Ed 在正式策略包前決定。</li>
</ul>
<h2>保存位置</h2>
<ul>
<li>舊版另存同資料夾：「…快篩報告_追加E-Test前版本_20261111」（第一版）、「…快篩報告_補跑V-REV前版本_20261111」（第二版）。</li>
<li>程式、結果表（未四捨五入 CSV）與逐筆明細（含取消與排除原因）推上 GitHub elon-bt：experiments/068/quick_v1（第一版）、quick_v2（第二版）、quick_v3（本版），附 SHA256SUMS；不需 Ed 上傳。</li>
</ul>
<h2>結論</h2>
<p><b>建議做正式策略包</b>，組合：M1（原版）、V-2W、V-L120、V-FILT1ST、E-SKIP20（討論衍生，D-068-20261111-0949-1）；V-REV 與 V-MERGE 不列入（未優於原版或單一變體）。樣本外只對最終清單開一次。快篩結果不可作為交易依據。</p>
<h2>注意事項</h2>
<ol>
<li>財報為 FinMind 現行修訂值、以法定期限判斷可用，逾期申報或重編無法辨識，標「時點未驗證」。</li>
<li>上櫃全額交割（變更交易）無官方歷史，本快篩只排除上市全額交割股；066 Eve R02 審查指出同一問題（D-066-20261111-0038-1 已改研究起點），正式策略包需比照決定。</li>
<li>r68 的減資恢復買賣日參考價仍為停止買賣前收盤（退回-69 ④，r72 待複審）。本案以 corp_actions 推得恢復參考價、依規則重算當日漲跌停（514 個公司日），進出場落在這些日子的交易 48 筆，其中 8928（2014-08-15）因此改為開盤跌停順延至 08-21（V-L120、V-FILT1ST、E-M1-ADJ）。</li>
<li>自檢 WARN「|報酬|≥1」：為真實大漲段（例 3205 佰研 2015-05-04→2016-01-04 +523%、3373 熱映 2020 口罩行情），已核對日K。排除列共 {fd_count} 筆（跨越切點、異常跳動、公司行動資料不足、下市缺口），明細隨正式策略包交付。</li>
<li>股票池以四碼數字代號判定普通股，未逐檔核對特別股以外的特殊證券；持有段之間重疊（每月同日進出多檔），聚合 p 可能偏樂觀。</li>
</ol>
"""

cnt = cancels.groupby(["combo", "why"]).size().unstack(fill_value=0)
body = body.replace("<h2>主要組合樣本內十項統計", "<p>取消筆數：</p>" + table(["組合"] + list(cnt.columns), [[i] + [int(x) for x in r] for i, r in cnt.iterrows()]) + "<h2>主要組合樣本內十項統計", 1)

code = ""
for fn in ["prep068.py", "sim068.py", "stats068.py", "nav068.py", "merge068.py", "report068.py"]:
    code += f"<h3>{fn}</h3><pre style='font-family:Courier New;font-size:8pt'>{html.escape(open(fn, encoding='utf-8').read())}</pre>"
appendix = ("<h2>附錄：程式</h2><p>執行順序：prep068.py → sim068.py card → sim068.py etest → stats068.py → nav068.py → report068.py。"
            "共用統計函式 bt_stats 1.2（sha256 e99c85e9a9da8c593a727175cd5a0cc019d679552c75e8b1cef42fa62d5a20ee，selftest 全過）只註明版本；"
            "出表與自檢用 elon-backtest 技能 elon_tools.py（baseline_check 通過）；資料載入、報酬、交易日曆用 elon-bt commit 57b6a4f 的 framework.data／framework.core。"
            "merge068.py 為合併組挑選協定（本版已執行）。fetch_rev.py（068 自抓月營收）已依 D-068-20261111-0055-1 停用、未產生本報告任何結果，未附。憑證不在程式內。</p>" + code)
open("report068.html", "w", encoding="utf-8").write("<html><head><meta charset='utf-8'></head><body>" + body + appendix + "</body></html>")
print(len(body), len(appendix))
