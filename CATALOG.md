# 共用資料清單（自動產生，勿手改）

由 `tools/gen_catalog.py` 依 `data_catalog/registry.yml`（標籤與驗收狀態）、`data_catalog/tables.yml`（表說明）與 Release 上的 parquet 檔產生。

**取資料一律用** `from framework.data import load` → `load("表名")`：預設只給已驗收標籤；要用未驗收版本須寫 `allow_candidate=True`，報告第一頁的資料標籤以 `data_tags_used()` 填寫。

圖例：✅ 已驗收　🟡 待驗收／待複審　⚪ 未送驗收　↩️ 已退回　⛔ 已被取代

## 一、各組目前可用標籤

| 組 | 內容 | 預設（已驗收） | 最新未驗收版本 |
|---|---|---|---|
| phase1 | 第一期｜日K、公司行動、市場別、交易日曆 | ✅ data-20261110r72 | — |
| phase2 | 第二期｜指數、處置注意、融資融券註記、平盤下名單、變更交易 | ✅ data-phase2-20261111c5 | — |
| fin | 財報｜綜合損益表、資產負債表（FinMind 現行值） | 無（load 會拒絕，需 allow_candidate） | ⚪ fin-20261107（未送驗收） |
| tdcc | 集保戶股權分散週表（Goodinfo，053 股票池 98 檔） | 無（load 會拒絕，需 allow_candidate） | ⚪ data-tdcc-20261111（未送驗收） |
| fincf | 現金流量表、現行產業別（FinMind 現行值；D-070-20261111-1424-1） | 無（load 會拒絕，需 allow_candidate） | ⚪ fincf-20261111（未送驗收） |
| revinst | 月營收、三大法人買賣超（FinMind 現行值，全市場含已下市） | 無（load 會拒絕，需 allow_candidate） | ⚪ revinst-20261111（未送驗收） |
| cb | 可轉債（含交換債）｜發行基本資料、轉換價格調整 | 無（load 會拒絕，需 allow_candidate） | — |

## 二、資料表一覽

筆數與期間取自 load() 預設會給的標籤；該組沒有已驗收標籤時，取最新未驗收版本（標 🟡／⚪）。

| 表 | 內容 | 用途 | 組 | 筆數 | 期間 | 可得時點 |
|---|---|---|---|---|---|---|
| `calendar` | 交易日曆 | 所有交易日推算（持有天數、次一交易日）的唯一依據 | phase1 ✅ | 6,894 | 1999-01-05～2026-11-03 | 事前已知 |
| `calendar_check` | 交易日曆官方核對 | 查某日是否經證交所／櫃買官方核對 | phase1 ✅ | 6,894 | 1999-01-05～2026-11-03 | 查核用 |
| `daily_k` | 上市櫃日K（含已下市） | 價格、成交量、市場別、漲跌停價、能否成交 | phase1 ✅ | 9,683,930 | 1992-01-04～2026-11-03 | 當日收盤後 |
| `daily_k_quarantine` | 隔離的日K | 只供查核，不供回測 | phase1 ✅ | 567,476 | 1992-01-04～2026-10-29 | 查核用 |
| `corp_actions` | 公司行動（除權息、減資、現增、面額變更） | 還原報酬、配股可賣日、減資恢復日 | phase1 ✅ | 42,664 | 2000-09-01～2026-12-29 | 以 announced 公告日後可得；ex_date 為除權息日 |
| `official_exright` | 官方除權息參考價表 | 除權息日參考價與漲跌停 | phase1 ✅ | 34,664 | 2000-09-01～2026-11-05 | 除權息日前公告 |
| `listing_periods` | 掛牌期間 | 當時母體（universe_on 唯一接受的輸入） | phase1 ✅ | 161,403 | 1962-02-09～2026-11-03 | 事前已知 |
| `market_segments` | 市場別區段 | 上市／上櫃轉換時點 | phase1 ✅ | 162,419 | 1999-01-05～2026-11-03 | 事前已知 |
| `status` | 個股掛牌狀態 | 上市／上櫃／未定，及有無官方上市櫃日 | phase1 ✅ | 3,252 |  | 查核用 |
| `index_daily` | 指數日資料 | 加權與櫃買開高低收、加權報酬指數（超額報酬基準） | phase2 ✅ | 6,900 | 1999-01-05～2026-11-11 | 當日收盤後 |
| `surveillance` | 處置與注意公告 | 處置期間、注意股事件 | phase2 ✅ | 114,506 | 2001-01-02～2026-11-10 | 公布日收盤後可得，最早次一交易日使用 |
| `margin_flags` | 融資融券註記（停資、停券、停止買賣） | 放空腿能否融券、停止買賣 | phase2 ✅ | 8,503,993 | 2001-01-02～2026-11-03 | data_date 收盤後公布，effective（次一交易日）生效 |
| `downtick_list` | 平盤下得融（借）券賣出名單 | 當日能否平盤下放空 | phase2 ✅ | 5,106,024 | 2013-09-18～2026-11-03 | 當日開盤前已知 |
| `downtick_coverage` | 平盤下名單逐日覆蓋狀態 | 判斷某市場某日名單是有資料還是缺口 | phase2 ✅ | 6,403 | 2013-09-18～2026-11-03 | 查核用 |
| `fulldelivery` | 變更交易（全額交割）名單（上市＋上櫃） | 預收款券、分盤集合競價；排除全額交割／管理股票 | phase2 ✅ | 246,447 | 2004-12-24～2026-11-03 | 當日 |
| `financials` | 財報（綜合損益表、資產負債表） | 財報類多空卡的基本面數字 | fin ⚪ | 10,466,736 | 1990-03-31～2026-09-30 | date 為財報期末，不是公告日；可得時點須依法定申報期限另行推算 |
| `cashflow` | 現金流量表（FinMind TaiwanStockCashFlowsStatement） | 營業／投資現金流、自由現金流（070 等） | fincf ⚪ | 2,596,525 | 2008-06-30～2026-09-30 | date 為財報期末，不是公告日；可得時點須依法定申報期限另行推算 |
| `industry` | 現行產業別（FinMind TaiwanStockInfo） | 排除金融保險業等產業篩選 | fincf ⚪ | 2,647 |  | 現行分類，非歷史；回溯使用須在個案揭露 |
| `tdcc_dist` | 集保戶股權分散週表（8 級人數與比例） | 千張／400 張大戶持股比例與人數變化（data_layer.tdcc_dist.big_ratio／big_holders） | tdcc | — | — | 資料日期（週五為主）之後公布；保守以資料日期 + 7 日後首個交易日開盤為可用時點，由策略卡另定 |
| `month_revenue` | 月營收（FinMind TaiwanStockMonthRevenue） | 月營收年增、月增、創新高等訊號（067 濾網⑤、068、073） | revinst ⚪ | 470,592 | 2002-02-01～2026-11-01 | date 為次月 1 日，不是公告日；法定期限為次月 10 日，保守以次月 10 日之後第一個交易日為可用時點，由策略卡另定 |
| `institutional` | 三大法人個股買賣超（FinMind TaiwanStockInstitutionalInvestorsBuySell） | 外資、投信、自營商淨買賣超（067 濾網⑥、048、072） | revinst ⚪ | 24,030,289 | 2005-01-03～2026-11-10 | 當日盤後公布，次一交易日開盤可用 |
| `cb_issues` | 可轉債發行基本資料（每檔一列） | 發行日、到期日、下櫃日、轉換期間、發行總額、發行時轉換價、擔保、票面利率、董事會決議日、訂價日、首次賣回日 | cb | — | — | 各欄日期本身即事件日；董事會決議日、訂價日為種子資料，可得時點以公告日為準 |
| `cb_conv_price` | 可轉債轉換價格調整紀錄 | 各次轉換價調整的生效日與調整前後價格 | cb | — | — | 以申報日（report_date_roc）收盤後可得，effective 為生效日 |

## 三、各表說明

### `calendar`｜交易日曆

- 用途：所有交易日推算（持有天數、次一交易日）的唯一依據
- 主鍵：date
- 可得時點：事前已知
- 注意：以 FinMind 交易日剔除全市場無成交日；1,300 天官方未取得無法核對（見 calendar_check）
- ✅ data-20261110r72：6,894 列；期間 1999-01-05～2026-11-03
- 欄位：`date`、`source`

### `calendar_check`｜交易日曆官方核對

- 用途：查某日是否經證交所／櫃買官方核對
- 主鍵：date
- 可得時點：查核用
- 注意：verdict＝一致／官方未取得
- ✅ data-20261110r72：6,894 列；期間 1999-01-05～2026-11-03
- 欄位：`date`、`finmind_calendar`、`twse_official`、`tpex_official`、`verdict`

### `daily_k`｜上市櫃日K（含已下市）

- 用途：價格、成交量、市場別、漲跌停價、能否成交
- 主鍵：date + stock_id
- 可得時點：當日收盤後
- 注意：limit_src 為「待查」「缺參考價」的列算資料不足，不可判定成交；no_limit_status 標新上市前五日無漲跌幅；jump_flag 為異常跳動旗標；2004-02-11 前上市無官方基準價
- ✅ data-20261110r72：9,683,930 列；期間 1992-01-04～2026-11-03
- 欄位：`date`、`stock_id`、`open`、`high`、`low`、`close`、`volume`、`amount`、`market`、`market_src`、`no_trade`、`price_note`、`prev_close`、`no_limit_status`、`no_limit_src`、`limit_src`、`limit_up`、`limit_down`、`ref_price`、`jump_flag`、`jump_reason`、`prev_gap_days`

### `daily_k_quarantine`｜隔離的日K

- 用途：只供查核，不供回測
- 主鍵：date + stock_id
- 可得時點：查核用
- 注意：興櫃／未掛牌／已下市而官方查無者，及 2004-02-11 前上市身分未證實者
- ✅ data-20261110r72：567,476 列；期間 1992-01-04～2026-10-29
- 欄位：`date`、`stock_id`、`open`、`high`、`low`、`close`、`volume`、`amount`、`market`、`market_src`、`quarantine_reason`

### `corp_actions`｜公司行動（除權息、減資、現增、面額變更）

- 用途：還原報酬、配股可賣日、減資恢復日
- 主鍵：stock_id + ex_date + kind
- 可得時點：以 announced 公告日後可得；ex_date 為除權息日
- 注意：flag 欄列出資料不足原因（例：配股可賣日、無法拆分權息）；share_ratio_inferred 為反推值只供比對；除權息未分類 3,320 筆
- ✅ data-20261110r72：42,664 列；期間 2000-09-01～2026-12-29
- 欄位：`stock_id`、`ex_date`、`kind`、`cash`、`share_ratio`、`cash_date`、`announced`、`source`、`flag`、`reduction_reason`、`ratio_basis`、`share_ratio_inferred`

### `official_exright`｜官方除權息參考價表

- 用途：除權息日參考價與漲跌停
- 主鍵：date + stock_id
- 可得時點：除權息日前公告
- 注意：來源 TWSE TWT49U、TPEx 除權除息計算結果
- ✅ data-20261110r72：34,664 列；期間 2000-09-01～2026-11-05
- 欄位：`date`、`stock_id`、`prev_close`、`ref`、`limit_up`、`limit_down`、`kind`、`cash`、`stock_per_k`、`wv`、`rights_sh`、`src`

### `listing_periods`｜掛牌期間

- 用途：當時母體（universe_on 唯一接受的輸入）
- 主鍵：stock_id + market + start
- 可得時點：事前已知
- 注意：以官方逐日市場別為主
- ✅ data-20261110r72：161,403 列；期間 1962-02-09～2026-11-03
- 欄位：`stock_id`、`market`、`start`、`end`、`basis`

### `market_segments`｜市場別區段

- 用途：上市／上櫃轉換時點
- 主鍵：stock_id + start
- 可得時點：事前已知
- 注意：src 為 TPEx 每日收盤行情、TWSE MI_INDEX 等
- ✅ data-20261110r72：162,419 列；期間 1999-01-05～2026-11-03
- 欄位：`stock_id`、`market`、`start`、`end`、`days`、`src`、`initial`

### `status`｜個股掛牌狀態

- 用途：上市／上櫃／未定，及有無官方上市櫃日
- 主鍵：stock_id
- 可得時點：查核用
- 注意：472 檔「上市或上櫃未定」；verified＝False 者無官方上市櫃日
- ✅ data-20261110r72：3,252 列；期間 —
- 欄位：`stock_id`、`status`、`src`、`start_date`、`end_date`、`verified`

### `index_daily`｜指數日資料

- 用途：加權與櫃買開高低收、加權報酬指數（超額報酬基準）
- 主鍵：date
- 可得時點：當日收盤後
- 注意：加權報酬指數只有收盤、2003 年起；櫃買報酬指數無官方歷史，不提供
- ✅ data-phase2-20261111c5：6,900 列；期間 1999-01-05～2026-11-11
- 欄位：`date`、`taiex_open`、`taiex_high`、`taiex_low`、`taiex_close`、`taiex_tri_close`、`tpex_open`、`tpex_high`、`tpex_low`、`tpex_close`

### `surveillance`｜處置與注意公告

- 用途：處置期間、注意股事件
- 主鍵：market + kind + announce + code + start + reason
- 可得時點：公布日收盤後可得，最早次一交易日使用
- 注意：count 欄為發布快照值，當作歷史時點訊號須另核當時公布值（Eve c5）；先用 sec_kind 篩證券類型；處置區間重疊請用 phase2_tools.disposal_intervals 合併；period_flag 標取消／恢復、起訖同日、期間逾 60 日、表格與內文日期不符（disposal_intervals 預設只取兩者交集、待核日期排除；聯集須指定 conflict="union"）；parse_note 標休市日等待核項目
- ✅ data-phase2-20261111c5：114,506 列；期間 2001-01-02～2026-11-10
- 欄位：`market`、`kind`、`announce`、`code`、`name`、`count`、`reason`、`start`、`end`、`measure`、`match_min`、`prepay`、`detail`、`parse_note`、`sec_kind`、`period_days`、`detail_start`、`detail_end`、`period_flag`、`overlap_prev`

### `margin_flags`｜融資融券註記（停資、停券、停止買賣）

- 用途：放空腿能否融券、停止買賣
- 主鍵：market + data_date + code
- 可得時點：data_date 收盤後公布，effective（次一交易日）生效
- 注意：上市 2001 起、上櫃 2007 起；櫃買 $、E 符號官方未列（21,947 筆資料不足）；早年代碼含義未驗證
- ✅ data-phase2-20261111c5：8,503,993 列；期間 2001-01-02～2026-11-03
- 欄位：`data_date`、`effective`、`market`、`code`、`stop_fin`、`stop_short`、`stop_trade`、`short_alloc`、`fin_alloc`、`note_raw`、`unknown_codes`、`parse_note`、`sec_kind`

### `downtick_list`｜平盤下得融（借）券賣出名單

- 用途：當日能否平盤下放空
- 主鍵：date + market + code
- 可得時點：當日開盤前已知
- 注意：2013-09 起；downtick_ban_prev_limit 的意義看 ban_rule（跌停／跌幅達3.5%／全面禁止，全面禁止期間 ETF 除外）；不在名單者不可平盤下放空；缺口日見 downtick_coverage
- ✅ data-phase2-20261111c5：5,106,024 列；期間 2013-09-18～2026-11-03
- 欄位：`date`、`market`、`code`、`short_susp`、`sbl_susp`、`downtick_ban_prev_limit`、`ban_rule`、`sec_kind`

### `downtick_coverage`｜平盤下名單逐日覆蓋狀態

- 用途：判斷某市場某日名單是有資料還是缺口
- 主鍵：date + market
- 可得時點：查核用
- 注意：櫃買 2019-10-02 為資料缺口（官方回空表），不可當成無限制
- ✅ data-phase2-20261111c5：6,403 列；期間 2013-09-18～2026-11-03
- 欄位：`date`、`market`、`rows`、`status`

### `fulldelivery`｜變更交易（全額交割）名單（上市＋上櫃）

- 用途：預收款券、分盤集合競價；排除全額交割／管理股票
- 主鍵：date + code
- 可得時點：當日
- 注意：上市 2004-12-24 起（TWT85U）；上櫃 2008-04-09 起（櫃買 afterTrading/chtm，kind 記變更交易／管理股票），2005-06～2008-04 上櫃名單不在本表；上市 period_auction 在 2007-11-01 前為空值（未知）；c4 起含上櫃，舊標籤只有上市
- ✅ data-phase2-20261111c5：246,447 列；期間 2004-12-24～2026-11-03
- 欄位：`date`、`market`、`code`、`name`、`period_auction`、`kind`、`sec_kind`

### `financials`｜財報（綜合損益表、資產負債表）

- 用途：財報類多空卡的基本面數字
- 主鍵：stock_id + date + dataset + type
- 可得時點：date 為財報期末，不是公告日；可得時點須依法定申報期限另行推算
- 注意：FinMind 現行（最終修訂）值，非公告當時版本；重編影響須在個案揭露；長表格式（type＝科目、value＝數值）
- ⚪ fin-20261107：10,466,736 列；期間 1990-03-31～2026-09-30
- 欄位：`stock_id`、`date`、`dataset`、`type`、`value`、`origin_name`

### `cashflow`｜現金流量表（FinMind TaiwanStockCashFlowsStatement）

- 用途：營業／投資現金流、自由現金流（070 等）
- 主鍵：stock_id + date + dataset + type
- 可得時點：date 為財報期末，不是公告日；可得時點須依法定申報期限另行推算
- 注意：FinMind 現行（最終修訂）值，非公告當時版本；數值多為年內累計，單季須自行相減（Q4＝全年減前三季）；長表格式
- ⚪ fincf-20261111：2,596,525 列；期間 2008-06-30～2026-09-30
- 欄位：`stock_id`、`date`、`dataset`、`type`、`value`、`origin_name`

### `industry`｜現行產業別（FinMind TaiwanStockInfo）

- 用途：排除金融保險業等產業篩選
- 主鍵：stock_id
- 可得時點：現行分類，非歷史；回溯使用須在個案揭露
- 注意：已下市公司多無列（industry 空＝資料不足，不推估）；is_financial 由產業名含「金融」或「保險」判定
- ⚪ fincf-20261111：2,647 列；期間 —
- 欄位：`stock_id`、`industry`、`finmind_type`、`delisted`、`is_financial`、`source`

### `tdcc_dist`｜集保戶股權分散週表（8 級人數與比例）

- 用途：千張／400 張大戶持股比例與人數變化（data_layer.tdcc_dist.big_ratio／big_holders）
- 主鍵：date + stock_id
- 可得時點：資料日期（週五為主）之後公布；保守以資料日期 + 7 日後首個交易日開盤為可用時點，由策略卡另定
- 注意：來源 Goodinfo 非官方原檔；比例多數僅小數一位（約 ±0.05 個百分點）；目前只收 053 股票池 98 檔；2015-04 前集保為月公布，本表不收；春節等無資料週不產生列

### `month_revenue`｜月營收（FinMind TaiwanStockMonthRevenue）

- 用途：月營收年增、月增、創新高等訊號（067 濾網⑤、068、073）
- 主鍵：stock_id + revenue_year + revenue_month
- 可得時點：date 為次月 1 日，不是公告日；法定期限為次月 10 日，保守以次月 10 日之後第一個交易日為可用時點，由策略卡另定
- 注意：FinMind 現行值，非公告當時版本（更正後數字會覆蓋）；單位為元；303 個代號無資料（多為早期下市或無申報）
- ⚪ revinst-20261111：470,592 列；期間 2002-02-01～2026-11-01
- 欄位：`stock_id`、`date`、`revenue_year`、`revenue_month`、`revenue`、`country`

### `institutional`｜三大法人個股買賣超（FinMind TaiwanStockInstitutionalInvestorsBuySell）

- 用途：外資、投信、自營商淨買賣超（067 濾網⑥、048、072）
- 主鍵：date + stock_id + name
- 可得時點：當日盤後公布，次一交易日開盤可用
- 注意：單位為股；長表格式（name＝法人別）；2012-05 前每年僅約 400～680 檔，之後才接近全市場；外資 2017 起拆出 Foreign_Dealer_Self（外資自營商），Foreign_Investor 為不含外資自營商；自營商 2014 起拆為 Dealer_self／Dealer_Hedging；431 個代號無資料
- ⚪ revinst-20261111：24,030,289 列；期間 2005-01-03～2026-11-10
- 欄位：`date`、`stock_id`、`name`、`buy`、`sell`

### `cb_issues`｜可轉債發行基本資料（每檔一列）

- 用途：發行日、到期日、下櫃日、轉換期間、發行總額、發行時轉換價、擔保、票面利率、董事會決議日、訂價日、首次賣回日
- 主鍵：bond_id
- 可得時點：各欄日期本身即事件日；董事會決議日、訂價日為種子資料，可得時點以公告日為準
- 注意：官方（公開資訊觀測站 t120sg01）為主，缺漏才用 Ed 種子清單（20260830）；每欄有 _src；推算值只在 _est 欄、不進主欄；conflict 列官方與種子不一致者；flags 列多世代歧義、疑年報董事會日等待核；official_status＝未下載／官方查無者主欄全為種子值；代號會回收再用，串接時須同時看發行日

### `cb_conv_price`｜可轉債轉換價格調整紀錄

- 用途：各次轉換價調整的生效日與調整前後價格
- 主鍵：bond_id + effective + price_before + price_after
- 可得時點：以申報日（report_date_roc）收盤後可得，effective 為生效日
- 注意：來源為 Ed 種子清單（MOPS 轉換價格調整公告），已去重；in_issues＝False 的 31 筆代號不在主清單；發行時轉換價另見 cb_issues.conv_price_issue（官方）

## 四、全部標籤

| 組 | 標籤 | 狀態 | 說明 | 程式 commit | 測試 |
|---|---|---|---|---|---|
| phase1 | data-20261105 | ⛔ 已被取代 | 初版；由 r67 起各修正版取代 |  |  |
| phase1 | data-20261105r67 | ⛔ 已被取代 | 由 r68 取代 |  |  |
| phase1 | data-20261105r67b | ⛔ 已被取代 | 由 r68 取代 |  |  |
| phase1 | data-20261105r68 | ✅ 已驗收 | Eve 複審通過（2026-11-06） | c568158 | 建置時 1 項因環境缺檔未過，重測 47 過（test_output_retest.txt） |
| phase1 | data-20261107r69 | ↩️ 已退回 | Eve 2026-11-10 退回：低價股漲跌停取整後等於基準價（99 列） | 7c7b6f0 | 通過 |
| phase1 | data-20261110r70 | ⛔ 已被取代 | 建置時測試在收集階段中斷（缺 pyyaml），由 r70b 取代 |  |  |
| phase1 | data-20261110r70b | ⛔ 已被取代 | 補正 Eve 退回 r69（低價股漲跌停）；未送審，由 r72 取代 |  |  |
| phase1 | data-20261110r71 | ⛔ 已被取代 | 自查補正版，但零價列標記索引錯位；未送審，由 r72 取代 |  |  |
| phase1 | data-20261110r72 | ✅ 已驗收 | Eve 複審通過（2026-11-11）。 補正 Eve 退回 r69（低價股漲跌停）＋自查：開高低為0改空值、盤中價超出推算漲跌停改待查（共 761 列） | 8f9a54a | 通過 |
| phase2 | data-phase2-20261107c1 | ⛔ 已被取代 | 未送審；外部審查後由 c2 取代 |  |  |
| phase2 | data-phase2-20261107c2 | ↩️ 已退回 | Eve 2026-11-10 退回：2023-02-23 ban_rule 錯標、處置表格與內文日期衝突未標 | a7365cb | 通過 |
| phase2 | data-phase2-20261110c3 | ↩️ 已退回 | Eve 2026-11-11 退回：disposal_intervals 預設聯集會把待核日期算成處置日 | e5d5c18 | 通過 |
| phase2 | data-phase2-20261111c4 | ⛔ 已被取代 | 含 c3 退回補正但不含上櫃變更交易（下載未完成時建置）；未送審，由 c5 取代 |  |  |
| phase2 | data-phase2-20261111c5 | ✅ 已驗收 | Eve 驗收通過（2026-11-11，Eve_c5_20261111.md）。補正 Eve 退回 c3（處置區間預設排除待核日期）＋上櫃變更交易名單（2008-04-09 起，Ed 2026-11-11 核准） | 0142b09 | 通過 |
| fin | fin-20261107 | ⚪ 未送驗收 | FinMind 現行（最終修訂）值，非公告當時版本 | 7c7b6f0 |  |
| tdcc | data-tdcc-20261111 | ⚪ 未送驗收 | 2015-05～2026-11；兩份原檔合併，重疊 188 列無衝突；比例多數僅小數一位 |  |  |
| fincf | fincf-20261111 | ⚪ 未送驗收 | 現金流量表 2008-06～2026-09（2 | 4f6ddcb |  |
| revinst | revinst-20261111 | ⚪ 未送驗收 | 月營收 2002-02～2026-11、法人 2005-01～2026-11（2012-05 前覆蓋僅約 400～680 檔）；D-067-20261111-0016-1 | cb6dbee |  |

原始檔倉庫（建置用，不供回測直接讀取）：

- `raw-cb`：可轉債發行基本資料原始頁（公開資訊觀測站 t120sg01）與下載進度
- `raw-phase2`：第二期 12 個官方來源原始檔（每日更新當月／當年檔）
- `raw-market`：第一期官方逐日市場別原始檔與單次探測結果
- `raw-financials`：財報 FinMind 原始回傳
- `raw-progress`：FinMind 下載進度與 StockInfo／Delisting 清單
- `raw-cashflow`：現金流量表 FinMind 原始回傳與下載進度（070 起共用）
- `raw-revinst`：月營收與三大法人 FinMind 原始回傳與下載進度
- `raw-064-annual`：策略064 年報原始檔（個案用）

資料截至日（各來源最後完整檢查日；open_periods 為當時尚未結束、之後會更新的期間）：

- data-phase2-20261107c2：tpex_attention 2026-11-07（open_periods=202611）；tpex_disposal 2026-11-07（open_periods=2026）；tpex_ix 2026-11-07（open_periods=202611）；tpex_margin 2026-11-07；tpex_mark 2026-11-07；twse_fulldelivery 2026-11-07；twse_ix 2026-11-07（open_periods=202611）；twse_margin 2026-11-07；twse_mark 2026-11-07；twse_notice 2026-11-07（open_periods=202611）；twse_punish 2026-11-07（open_periods=2026）；twse_tri 2026-11-07（open_periods=202611）
- data-phase2-20261110c3：tpex_attention 2026-11-09（open_periods=202611）；tpex_disposal 2026-11-09（open_periods=2026）；tpex_ix 2026-11-09（open_periods=202611）；tpex_margin 2026-11-09；tpex_mark 2026-11-09；twse_fulldelivery 2026-11-09；twse_ix 2026-11-09（open_periods=202611）；twse_margin 2026-11-09；twse_mark 2026-11-09；twse_notice 2026-11-09（open_periods=202611）；twse_punish 2026-11-09（open_periods=2026）；twse_tri 2026-11-09（open_periods=202611）
- data-phase2-20261111c5：tpex_attention 2026-11-11（open_periods=202611）；tpex_chtm 2026-11-11；tpex_disposal 2026-11-11（open_periods=2026）；tpex_ix 2026-11-11（open_periods=202611）；tpex_margin 2026-11-11；tpex_mark 2026-11-11；twse_fulldelivery 2026-11-11；twse_ix 2026-11-11（open_periods=202611）；twse_margin 2026-11-11；twse_mark 2026-11-11；twse_notice 2026-11-11（open_periods=202611）；twse_punish 2026-11-11（open_periods=2026）；twse_tri 2026-11-11（open_periods=202611）

## 五、未登記標籤（load() 不會使用，須先登記並送驗收）

- ⚠ `raw-068-revenue`
