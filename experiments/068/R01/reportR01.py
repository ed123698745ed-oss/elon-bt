"""068 V01／R01 回測結果（HTML → Google 文件）。數字一律取自未四捨五入的結果檔。"""
import html, math, pickle
import pandas as pd

ten = pd.concat([pd.read_pickle("R01_card_ten.pkl"), pd.read_pickle("R01_et_ten.pkl")], ignore_index=True)
dd = pd.concat([pd.read_pickle("R01_card_dd.pkl"), pd.read_pickle("R01_et_dd.pkl")], ignore_index=True)
ex = pd.read_pickle("R01_excess.pkl")
nav = pd.read_pickle("navR01.pkl")
sj = pd.read_pickle("sensR01_judge.pkl"); ss = pd.read_pickle("sensR01_stats.pkl")
meta = pickle.load(open("metaR01.pkl", "rb"))
q = pd.read_pickle("archive_v1/card_ten.pkl")   # 快篩 r68 樣本內（v1；V-REV、V-MERGE 取 quick_v3）
q3 = pd.read_pickle("card_ten.pkl")
qe = pd.read_pickle("et_ten.pkl")
tr = pd.concat([pd.read_pickle("tradesR01.pkl"), pd.read_pickle("etradesR01.pkl")], ignore_index=True)

NAME = {"M0": "M0 對照（不加 ROE）", "M1": "M1 原版", "V-L20": "回看 20 日", "V-L120": "回看 120 日", "V-TOP10": "選 10 檔",
        "V-FILT1ST": "先濾 ROE 再取前 30", "V-ROE8": "近四季 ROE>8%", "V-REV": "月營收年增>0 取代 ROE>0",
        "V-LIQ0.5億": "20 日均額 ≥5,000 萬", "V-LIQ2億": "20 日均額 ≥2 億", "V-2W": "雙週換股", "V-MKT": "大盤 20MA 濾網",
        "V-MERGE": "合併組（120日＋10檔＋先濾＋雙週）", "M1-同期": "M1（2014-04 起，V-ROE8 對照）",
        "E-M1-ADJ": "E-Test：還原價算動能", "E-BUF50": "E-Test：持股緩衝（前 50 續抱）", "E-SKIP20": "E-Test：跳過最近 1 個月", "E-STOP15": "E-Test：停損 15%"}
CARD = ["M0", "M1", "M1-同期", "V-L20", "V-L120", "V-TOP10", "V-FILT1ST", "V-ROE8", "V-REV", "V-LIQ0.5億", "V-LIQ2億", "V-2W", "V-MKT", "V-MERGE"]
ET = ["E-M1-ADJ", "E-BUF50", "E-SKIP20", "E-STOP15"]


def isna(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def pct(v, d=2):
    return "N/A" if isna(v) else f"{v*100:.{d}f}%"


def num(v, f="{:.3f}"):
    return "N/A" if isna(v) else f.format(v)


def pv(v):
    return "—" if isna(v) else (f"{v:.1e}" if v < 0.001 else f"{v:.4f}")


def table(head, rows):
    h = "".join(f"<th>{html.escape(str(x))}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table border='1' cellpadding='2' style='border-collapse:collapse;font-size:8pt'><tr>{h}</tr>{b}</table>"


H10 = ["組合", "段", "①樣本數", "②平均報酬", "③平均持有交易日數", "④單利年化", "⑤勝率", "⑥賠率R", "⑦凱利", "⑧標準差", "⑨t值", "⑩雙尾p",
       "聚合單位數", "聚合p", "Holm聚合p"]


def ten_rows(cs):
    out = []
    for c in cs:
        for r in ten[ten.combo == c].itertuples():
            na = f"（N/A：{r._19}）" if False else ""
            out.append([c, r.sample, f"{int(r.樣本數):,}", pct(r.平均報酬), num(r.平均持有交易日數, "{:.1f}"), pct(r.單利年化, 1), pct(r.勝率, 1),
                        num(r.賠率R, "{:.2f}"), num(r.凱利, "{:.3f}"), pct(r.標準差, 1), num(r.t值, "{:.2f}"), pv(r.雙尾p), int(r.聚合單位數), pv(r.聚合p), pv(r.Holm聚合p)])
    return out


def dd_rows(cs):
    out = []
    for c in cs:
        for r in dd[dd.combo == c].itertuples():
            lab = f"{int(r.最長回撤期筆數):,} 筆（{int(r.最長回撤期日曆日):,} 天）" + ("，未回復" if r.最長回撤期未回復 else "")
            if r.需註記:
                lab += f"［＝{int(r.最長回撤期聚合單位數)} 個進場日］"
            out.append([c, r.sample, pct(r.最大回撤, 1), pct(r.最差三次回撤平均, 1), lab])
    return out


T = ten.set_index(["combo", "sample"])
def g(c, s, k):
    return T.loc[(c, s), k]

oos_ok = [c for c in CARD + ET if c != "M1-同期" and g(c, "樣本外", "平均報酬") > 0 and g(c, "樣本外", "聚合p") < 0.05]
oos_pos = [c for c in CARD + ET if c != "M1-同期" and g(c, "樣本外", "平均報酬") > 0]
n_oos_units = int(g("M1", "樣本外", "聚合單位數"))

summary = f"""
<p><b>① 結果：</b>18 組的樣本外（2022-10～2026-11，{n_oos_units} 個換股月）平均報酬全部為正（例 M1 {pct(g('M1','樣本外','平均報酬'))}、E-SKIP20 {pct(g('E-SKIP20','樣本外','平均報酬'))}），但依凍結的判讀標準（樣本外聚合 p&lt;0.05），只有 V-L20 達標（聚合 p {pv(g('V-L20','樣本外','聚合p'))}，Holm 後 {pv(g('V-L20','樣本外','Holm聚合p'))}），且其敏感度 9 格中僅 3 格樣本外顯著，屬尖峰。V-REV 敏感度最穩（樣本外 5／9 格顯著），但現行參數樣本外聚合 p {pv(g('V-REV','樣本外','聚合p'))} 未達標。描述性比較：樣本外期間加權報酬指數同期平均約 +4.8%／筆，18 組相對大盤的近似超額報酬全部不顯著、多數為負；等權組合年化（M1 約 14%）落後加權指數同期（約 34%）。</p>
<p><b>② 影響：</b>本次回測沒有值得執行的候選組合。樣本內的強勢主要來自市場本身（樣本內超額報酬也多不顯著），樣本外的正報酬是 2022-10 起的多頭行情帶來的；依執行計畫「無候選結案」，預設不送 Eve。</p>
<p><b>③ 要 Ed 選：</b>結案（依手冊 6-D 交結案存檔；本報告與附件已在策略包資料夾），或指定續做方向（例如以超額報酬重新定義假說另開策略卡）。另請確認第二期由 c4 改用已驗收 c5（D-068-20261111-2032-1）。</p>
"""

body = f"""<h1>068 FinLab範例-60日動能ROE濾網｜V01／R01 回測結果</h1>
<p>Elon｜2026-11-11｜執行計畫修訂版 57、Elon 工作手冊 V31、研究預設口徑 V04｜策略卡 V01、策略包 R01。</p>
<h2>決策摘要</h2>{summary}
<h2>關卡一核准依據與相關決定（策略總表「決策紀錄」）</h2>
<ul>
<li>D-068-20261104-1938-1：關卡一核准策略卡 V01（範圍依卡；研究邊界：可交易性 L1、樣本內 ≤2022-06-30、隔離帶 2022-07-01～09-30、樣本外 ≥2022-10-01）。D-068-20261104-1947-1：6(c) 全採卡上建議。</li>
<li>D-068-20261111-0018-1～6：可測性補正（共用資料層、期限次一交易日起可用、雙週 ISO、歸屬母公司口徑、60 日前無收盤不排名、大盤濾網只擋新進場）；-0018-7：E-M1-ADJ。D-068-20261111-0055-1：月營收用 revinst。D-068-20261111-0949-1：E-BUF50、E-SKIP20、E-STOP15。</li>
<li>D-068-20261111-1507-1：做正式策略包，18 組全開樣本外、全做敏感度（敏感度範圍超出手冊 4-B「只對候選」，屬 Ed 指定加做）。D-068-20261111-1510-1：第一期改用 r72。D-068-20261111-1510-2：等第二期含上櫃變更交易名單的版本；D-068-20261111-2032-1：c4 被取代、改用已驗收 c5（Elon 登記，待 Ed 確認）。</li>
</ul>
<h2>⓪ 符號與名詞定義</h2>
{table(['名詞', '定義'], [
 ['換股日 t', '每月（V-2W／V-MERGE：ISO 雙數週）最後一個市場交易日；收盤後判斷、次一交易日開盤先賣後買'],
 ['動能', '換股日有成交收盤 ÷ 往前第 L 個市場交易日有成交收盤（未還原；E-M1-ADJ 用時點一致調整價；E-SKIP20 用第 20 日前÷第 80 日前）'],
 ['ROE>0', '換股日當時已過法定期限（期限日之次一交易日起）最近一季：歸屬母公司淨利>0 且歸屬母公司權益>0（無非控制權益拆分者用本期淨利／權益總額）'],
 ['一筆交易', '連續持有段：入選買進到落選（或停損）賣出；續選續抱不另計'],
 ['樣本內／隔離帶／樣本外／最新年度', '出場日 ≤2022-06-30／與 2022-07-01～09-30 重疊／進場訊號日 ≥2022-10-01／樣本外中訊號日在 2026 年者（子集）'],
 ['未完成', '資料最後一日（2026-11-03）仍持有、持有期間下市缺口、異常跳動或公司行動資料不足者，不列入統計'],
 ['持有交易日數', '官方交易日曆含首尾；單利年化＝平均報酬×252÷平均持有交易日數'],
 ['聚合 p', '以進場日（換股執行日）為聚合單位，單位內報酬先平均再做單樣本 t 檢定；結論以聚合 p 為準'],
 ['Holm 聚合 p', '家族一＝策略卡 10 組變體＋V-MERGE；家族二＝4 組 E-Test；樣本內、樣本外各自修正'],
 ['近似超額', '個股報酬減加權報酬指數（進場日前一日收盤→出場日前一日收盤）；指數無開盤報酬值，故為近似，只作描述']])}
<h2>① 測試期間與資料</h2>
<ul>
<li>樣本：訊號 2013-05-16～2026-11-03（資料最後一日）。凍結紀錄：elon-bt experiments/068/freeze_068_R01.md（2026-11-11 15:38，sha256 d3653bfb…9d86）與補充 1（20:31，第二期改 c5），均在載入任何樣本外報酬前提交。</li>
<li>資料標籤：{html.escape(meta['tags'])}；月營收 revinst-20261111 month_revenue（未送驗收）。財報與月營收為 FinMind 現行修訂值，時點未驗證。</li>
<li>股票池：當日官方上市／上櫃普通股（四碼、非 91xx），排除證交所全額交割與櫃買變更交易／管理股票（c5 上櫃名單 2008-04-09 起，涵蓋全樣本）；含日後下市者。</li>
</ul>
<h2>② 進出場規則</h2>
<p>同快篩報告（D-068-20261111-0018-1～6）：全池取動能前 N 名，再保留 ROE&gt;0（V-FILT1ST 先濾後排）；換股日次一交易日開盤等權買進，續選續抱、落選開盤賣出；進場開盤漲停／停牌取消不遞補；出場開盤跌停／停牌每日重試順延；報酬依固定股數加實得現金（研究預設口徑 V04）。各組只改策略卡 4.2 或 E-Test 所列一項參數。r72 仍有參考價＝前收的 7 個減資恢復日，以 corp_actions 推算恢復參考價與漲跌停（與快篩同做法）。<b>未計入稅、交易成本與滑價。</b></p>
<h2>③ 結果表（十項統計）</h2>
<h3>策略卡組合</h3>{table(H10, ten_rows(CARD))}
<h3>E-Test（討論衍生，6-A；條件與來源見下節）</h3>{table(H10, ten_rows(ET))}
<p>說明：樣本內 18 組中 17 組聚合 p&lt;0.05（V-ROE8 除外），與快篩一致；樣本外平均報酬全部為正，逐筆 p 多數顯著，但以換股月為單位的聚合 p 只有 V-L20 &lt;0.05（48 個月、同月持股高度同漲同跌，有效樣本小）。最新年度（2026，9 個換股月）平均報酬高但聚合單位數 &lt;10，檢定力不足。</p>
<h3>回撤三項（等風險法，只供組合間比較）</h3>{table(['組合', '段', '⑪最大回撤', '⑫最差三次回撤平均', '⑬最長回撤期'], dd_rows(CARD + ET))}
<h2>④ 結論</h2>
<p><b>本次回測沒有值得執行的候選組合。</b>主要數據原因：</p>
<ol>
<li>依凍結判讀，樣本外成立（平均報酬&gt;0 且聚合 p&lt;0.05）只有 V-L20；其敏感度樣本外僅 3／9 格顯著（尖峰），樣本內反而是 20 日回看表現較差的一組，不列候選。</li>
<li>V-REV 敏感度最穩（樣本內 8／9、樣本外 5／9 格顯著），但現行參數樣本外聚合 p {pv(g('V-REV','樣本外','聚合p'))}，且近似超額 {pct(ex.set_index('combo／sample').loc['V-REV｜樣本外','平均報酬'])}，不列候選。</li>
<li>相對大盤：樣本外 18 組近似超額全部不顯著、多數為負；等權淨值年化落後加權指數；樣本內近似超額也只有 V-2W、E-SKIP20 聚合 p&lt;0.05。動能前 30＋ROE&gt;0 的報酬大致是市場報酬，2022-10 後的強勢來自多頭行情。</li>
</ol>
<p>此結論只是研究判斷。依執行計畫「無候選結案」，預設不送 Eve，由 Ed 決定結案或指定續做。</p>
<h2>⑤ 其後</h2>
<h3>敏感度測試（18 組 × 9 格＝162 格，格點依凍結紀錄第 5 節；單格 p 未做多重檢定修正）</h3>
{table(['組合', '格數', '樣本內正報酬格', '樣本內聚合p顯著格', '樣本外正報酬格', '樣本外聚合p顯著格', '內外同方向格', '判讀'], [[r.combo, r.格數, r.樣本內正報酬格, r.樣本內聚合p顯著格, r.樣本外正報酬格, r.樣本外聚合p顯著格, r.內外同方向格, r.判讀] for r in sj.itertuples()])}
<p>說明：162 格平均報酬全部為正、內外同方向；但樣本外聚合 p 顯著的格數普遍不足一半，只有 V-REV 達「穩健」門檻。中心格（現行參數）36 列與主結果逐筆一致。完整 162 格 × 2 段十項統計在原始數據明細 sens_grid.csv。</p>
{table(['格', '樣本內平均', '樣本內聚合p', '樣本外平均', '樣本外聚合p'], [[r.cid + ('（現行）' if r.center else ''), pct(r.平均報酬_i), pv(r.聚合p_i), pct(r.平均報酬_o), pv(r.聚合p_o)] for r in ss[ss['sample']=='樣本內'].merge(ss[ss['sample']=='樣本外'][['cid','平均報酬','聚合p']], on='cid', suffixes=('_i','_o')).itertuples()])}
<h3>描述性：相對加權報酬指數的近似超額報酬</h3>
{table(['組合｜段', '樣本數', '近似超額平均', '同期指數平均', '超額勝率', 't值', '聚合p'], [[r._1, f"{int(r.樣本數):,}", pct(r.平均報酬), pct(r.基準平均), pct(r.勝率,1), num(r.t值,'{:.2f}'), pv(r.聚合p)] for r in ex.itertuples()])}
<h3>描述性：等權組合淨值（樣本內、樣本外各自從空手開始）</h3>
{table(['組合', '段', '年化報酬', '最大回撤', '平均持股數', '年換手率'], [[r.combo, r.段, pct(r.年化報酬,1), pct(r.最大回撤,1), f"{r.平均持股數:.1f}", f"{r.年換手率:.2f}"] for r in nav.itertuples()])}
<p>同期加權指數（價格）年化：樣本內 2013-05-16～2022-06-30 約 6.4%，樣本外 2022-10-01～2026-11-03 約 33.5%。</p>
<h3>快篩（r68）與 R01（r72＋c5）樣本內對照</h3>
{table(['組合', '快篩樣本數', '快篩平均', '快篩聚合p', 'R01樣本數', 'R01平均', 'R01聚合p'], [[c, f"{int(src.loc[c,'樣本數']):,}", pct(src.loc[c,'平均報酬']), pv(src.loc[c,'聚合p']), f"{int(g(c,'樣本內','樣本數')):,}", pct(g(c,'樣本內','平均報酬')), pv(g(c,'樣本內','聚合p'))] for c, src in [(c, (q3 if c in ('V-REV','V-MERGE') else (qe if c.startswith('E-') else q)).set_index('combo')) for c in CARD + ET]])}
<p>說明：差異來自 r72 公司行動與限幅修正、c5 上櫃全額交割排除改變了部分月份的前 30 名，以及樣本內改為「出場日 ≤2022-06-30」；方向與顯著性結論不變。</p>
<h3>修訂紀錄與檔案對應（R01 首版）</h3>
<ul><li>本文件（回測結果，含注意事項）；程式附錄另見「068_FinLab範例-60日動能ROE濾網_V01_R01_程式附錄」；原始數據明細「068_FinLab範例-60日動能ROE濾網_V01_R01_原始數據明細.zip」（18 組逐筆交易、開盤取消、敏感度 162 格統計、未四捨五入統計表），均由 Elon 直接建在本策略包資料夾，無需 Ed 上傳。敏感度 162 格的逐筆交易（約 68 MB）放 elon-bt experiments/068/R01/sens_trades.csv.gz（附 sha256），程式與全部明細亦另存同處。</li></ul>
<h2>⑥ 注意事項</h2>
<ol>
<li>財報（fin-20261107）與月營收（revinst-20261111）未送驗收，為 FinMind 現行修訂值，時點未驗證。</li>
<li>樣本外以換股月聚合僅 48 單位，個股持有期互相重疊，聚合 p 仍可能偏樂觀；最新年度 9 單位，檢定力不足。</li>
<li>未完成或排除：跨隔離帶 {int((tr['sample']=='隔離帶').sum()):,} 筆、資料最後一日仍持有 {int((tr.excluded_reason=='資料最後一日仍持有，未完成').sum())} 筆、公司行動資料不足／異常跳動／限幅待查 {int(tr.excluded_reason.fillna('').str.contains('資料不足|異常跳動|限幅').sum())} 筆（全 18 組合計），明細附原因。</li>
<li>樣本外切點依關卡一核准，看報酬前凍結；第二期由 c4 改 c5 屬偏離，已另開補充並在看樣本外前提交。</li>
</ol>
"""
open("reportR01.html", "w", encoding="utf-8").write("<html><head><meta charset='utf-8'></head><body>" + body + "</body></html>")
print(len(body))
