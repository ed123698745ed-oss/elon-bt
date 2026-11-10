# 共用資料清單（自動產生，勿手改）

由 `tools/gen_catalog.py` 依 `data_catalog/registry.yml`（標籤與驗收狀態）、`data_catalog/tables.yml`（表說明）與 Release 上的 parquet 檔產生。

**取資料一律用** `from framework.data import load` → `load("表名")`：預設只給已驗收標籤；要用未驗收版本須寫 `allow_candidate=True`，報告第一頁的資料標籤以 `data_tags_used()` 填寫。

圖例：✅ 已驗收　🟡 待驗收／待複審　⚪ 未送驗收　↩️ 已退回　⛔ 已被取代

## 一、各組目前可用標籤

| 組 | 內容 | 預設（已驗收） | 最新未驗收版本 |
|---|---|---|---|
| phase1 | 第一期｜日K、公司行動、市場別、交易日曆 | ✅ data-20261105r68 | 🟡 data-20261110r70b（待複審） |
| phase2 | 第二期｜指數、處置注意、融資融券註記、平盤下名單、變更交易 | 無（load 會拒絕，需 allow_candidate） | 🟡 data-phase2-20261110c3（待驗收） |
| fin | 財報｜綜合損益表、資產負債表（FinMind 現行值） | 無（load 會拒絕，需 allow_candidate） | ⚪ fin-20261107（未送驗收） |

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
| `index_daily` | 指數日資料 | 加權與櫃買開高低收、加權報酬指數（超額報酬基準） | phase2 🟡 | 6,898 | 1999-01-05～2026-11-09 | 當日收盤後 |
| `surveillance` | 處置與注意公告 | 處置期間、注意股事件 | phase2 🟡 | 114,476 | 2001-01-02～2026-11-09 | 公布日收盤後可得，最早次一交易日使用 |
| `margin_flags` | 融資融券註記（停資、停券、停止買賣） | 放空腿能否融券、停止買賣 | phase2 🟡 | 8,503,993 | 2001-01-02～2026-11-03 | data_date 收盤後公布，effective（次一交易日）生效 |
| `downtick_list` | 平盤下得融（借）券賣出名單 | 當日能否平盤下放空 | phase2 🟡 | 5,106,024 | 2013-09-18～2026-11-03 | 當日開盤前已知 |
| `downtick_coverage` | 平盤下名單逐日覆蓋狀態 | 判斷某市場某日名單是有資料還是缺口 | phase2 🟡 | 6,403 | 2013-09-18～2026-11-03 | 查核用 |
| `fulldelivery` | 證交所變更交易（全額交割）名單 | 預收款券、分盤集合競價 | phase2 🟡 | 107,618 | 2004-12-24～2026-11-03 | 當日 |
| `financials` | 財報（綜合損益表、資產負債表） | 財報類多空卡的基本面數字 | fin ⚪ | 10,466,736 | 1990-03-31～2026-09-30 | date 為財報期末，不是公告日；可得時點須依法定申報期限另行推算 |

## 三、各表說明

### `calendar`｜交易日曆

- 用途：所有交易日推算（持有天數、次一交易日）的唯一依據
- 主鍵：date
- 可得時點：事前已知
- 注意：以 FinMind 交易日剔除全市場無成交日；1,300 天官方未取得無法核對（見 calendar_check）
- ✅ data-20261105r68：6,894 列；期間 1999-01-05～2026-11-03
- 🟡 data-20261110r70b：6,894 列；期間 1999-01-05～2026-11-03
- 欄位：`date`、`source`

### `calendar_check`｜交易日曆官方核對

- 用途：查某日是否經證交所／櫃買官方核對
- 主鍵：date
- 可得時點：查核用
- 注意：verdict＝一致／官方未取得
- ✅ data-20261105r68：6,894 列；期間 1999-01-05～2026-11-03
- 🟡 data-20261110r70b：6,894 列；期間 1999-01-05～2026-11-03
- 欄位：`date`、`finmind_calendar`、`twse_official`、`tpex_official`、`verdict`

### `daily_k`｜上市櫃日K（含已下市）

- 用途：價格、成交量、市場別、漲跌停價、能否成交
- 主鍵：date + stock_id
- 可得時點：當日收盤後
- 注意：limit_src 為「待查」「缺參考價」的列算資料不足，不可判定成交；no_limit_status 標新上市前五日無漲跌幅；jump_flag 為異常跳動旗標；2004-02-11 前上市無官方基準價
- ✅ data-20261105r68：9,683,930 列；期間 1992-01-04～2026-11-03
- 🟡 data-20261110r70b：9,683,930 列；期間 1992-01-04～2026-11-03
- 欄位：`date`、`stock_id`、`open`、`high`、`low`、`close`、`volume`、`amount`、`market`、`market_src`、`no_trade`、`prev_close`、`no_limit_status`、`no_limit_src`、`ref_price`、`limit_src`、`limit_up`、`limit_down`、`jump_flag`、`jump_reason`、`prev_gap_days`

### `daily_k_quarantine`｜隔離的日K

- 用途：只供查核，不供回測
- 主鍵：date + stock_id
- 可得時點：查核用
- 注意：興櫃／未掛牌／已下市而官方查無者，及 2004-02-11 前上市身分未證實者
- ✅ data-20261105r68：567,476 列；期間 1992-01-04～2026-10-29
- 🟡 data-20261110r70b：567,476 列；期間 1992-01-04～2026-10-29
- 欄位：`date`、`stock_id`、`open`、`high`、`low`、`close`、`volume`、`amount`、`market`、`market_src`、`quarantine_reason`

### `corp_actions`｜公司行動（除權息、減資、現增、面額變更）

- 用途：還原報酬、配股可賣日、減資恢復日
- 主鍵：stock_id + ex_date + kind
- 可得時點：以 announced 公告日後可得；ex_date 為除權息日
- 注意：flag 欄列出資料不足原因（例：配股可賣日、無法拆分權息）；share_ratio_inferred 為反推值只供比對；除權息未分類 3,320 筆
- ✅ data-20261105r68：42,664 列；期間 2000-09-01～2026-12-29
- 🟡 data-20261110r70b：42,664 列；期間 2000-09-01～2026-12-29
- 欄位：`stock_id`、`ex_date`、`kind`、`cash`、`share_ratio`、`cash_date`、`announced`、`source`、`flag`、`reduction_reason`、`ratio_basis`、`share_ratio_inferred`

### `official_exright`｜官方除權息參考價表

- 用途：除權息日參考價與漲跌停
- 主鍵：date + stock_id
- 可得時點：除權息日前公告
- 注意：來源 TWSE TWT49U、TPEx 除權除息計算結果
- ✅ data-20261105r68：34,664 列；期間 2000-09-01～2026-11-05
- 🟡 data-20261110r70b：34,664 列；期間 2000-09-01～2026-11-05
- 欄位：`date`、`stock_id`、`prev_close`、`ref`、`limit_up`、`limit_down`、`kind`、`cash`、`stock_per_k`、`wv`、`rights_sh`、`src`

### `listing_periods`｜掛牌期間

- 用途：當時母體（universe_on 唯一接受的輸入）
- 主鍵：stock_id + market + start
- 可得時點：事前已知
- 注意：以官方逐日市場別為主
- ✅ data-20261105r68：161,403 列；期間 1962-02-09～2026-11-03
- 🟡 data-20261110r70b：161,403 列；期間 1962-02-09～2026-11-03
- 欄位：`stock_id`、`market`、`start`、`end`、`basis`

### `market_segments`｜市場別區段

- 用途：上市／上櫃轉換時點
- 主鍵：stock_id + start
- 可得時點：事前已知
- 注意：src 為 TPEx 每日收盤行情、TWSE MI_INDEX 等
- ✅ data-20261105r68：162,419 列；期間 1999-01-05～2026-11-03
- 🟡 data-20261110r70b：162,419 列；期間 1999-01-05～2026-11-03
- 欄位：`stock_id`、`market`、`start`、`end`、`days`、`src`、`initial`

### `status`｜個股掛牌狀態

- 用途：上市／上櫃／未定，及有無官方上市櫃日
- 主鍵：stock_id
- 可得時點：查核用
- 注意：472 檔「上市或上櫃未定」；verified＝False 者無官方上市櫃日
- ✅ data-20261105r68：3,252 列；期間 —
- 🟡 data-20261110r70b：3,252 列；期間 —
- 欄位：`stock_id`、`status`、`src`、`start_date`、`end_date`、`verified`

### `index_daily`｜指數日資料

- 用途：加權與櫃買開高低收、加權報酬指數（超額報酬基準）
- 主鍵：date
- 可得時點：當日收盤後
- 注意：加權報酬指數只有收盤、2003 年起；櫃買報酬指數無官方歷史，不提供
- 🟡 data-phase2-20261110c3：6,898 列；期間 1999-01-05～2026-11-09
- 欄位：`date`、`taiex_open`、`taiex_high`、`taiex_low`、`taiex_close`、`taiex_tri_close`、`tpex_open`、`tpex_high`、`tpex_low`、`tpex_close`

### `surveillance`｜處置與注意公告

- 用途：處置期間、注意股事件
- 主鍵：market + kind + announce + code + start + reason
- 可得時點：公布日收盤後可得，最早次一交易日使用
- 注意：先用 sec_kind 篩證券類型；處置區間重疊請用 phase2_tools.disposal_intervals 合併；period_flag 標取消／恢復、起訖同日、期間逾 60 日、表格與內文日期不符（合併區間預設取聯集）；parse_note 標休市日等待核項目
- 🟡 data-phase2-20261110c3：114,476 列；期間 2001-01-02～2026-11-09
- 欄位：`market`、`kind`、`announce`、`code`、`name`、`count`、`reason`、`start`、`end`、`measure`、`match_min`、`prepay`、`detail`、`parse_note`、`sec_kind`、`period_days`、`detail_start`、`detail_end`、`period_flag`、`overlap_prev`

### `margin_flags`｜融資融券註記（停資、停券、停止買賣）

- 用途：放空腿能否融券、停止買賣
- 主鍵：market + data_date + code
- 可得時點：data_date 收盤後公布，effective（次一交易日）生效
- 注意：上市 2001 起、上櫃 2007 起；櫃買 $、E 符號官方未列（21,947 筆資料不足）；早年代碼含義未驗證
- 🟡 data-phase2-20261110c3：8,503,993 列；期間 2001-01-02～2026-11-03
- 欄位：`data_date`、`effective`、`market`、`code`、`stop_fin`、`stop_short`、`stop_trade`、`short_alloc`、`fin_alloc`、`note_raw`、`unknown_codes`、`parse_note`、`sec_kind`

### `downtick_list`｜平盤下得融（借）券賣出名單

- 用途：當日能否平盤下放空
- 主鍵：date + market + code
- 可得時點：當日開盤前已知
- 注意：2013-09 起；downtick_ban_prev_limit 的意義看 ban_rule（跌停／跌幅達3.5%／全面禁止，全面禁止期間 ETF 除外）；不在名單者不可平盤下放空；缺口日見 downtick_coverage
- 🟡 data-phase2-20261110c3：5,106,024 列；期間 2013-09-18～2026-11-03
- 欄位：`date`、`market`、`code`、`short_susp`、`sbl_susp`、`downtick_ban_prev_limit`、`ban_rule`、`sec_kind`

### `downtick_coverage`｜平盤下名單逐日覆蓋狀態

- 用途：判斷某市場某日名單是有資料還是缺口
- 主鍵：date + market
- 可得時點：查核用
- 注意：櫃買 2019-10-02 為資料缺口（官方回空表），不可當成無限制
- 🟡 data-phase2-20261110c3：6,403 列；期間 2013-09-18～2026-11-03
- 欄位：`date`、`market`、`rows`、`status`

### `fulldelivery`｜證交所變更交易（全額交割）名單

- 用途：預收款券、分盤集合競價
- 主鍵：date + code
- 可得時點：當日
- 注意：只有上市，2004-12-24 起；period_auction 在 2007-11-01 前為空值（未知）；櫃買變更交易無官方歷史
- 🟡 data-phase2-20261110c3：107,618 列；期間 2004-12-24～2026-11-03
- 欄位：`date`、`market`、`code`、`name`、`period_auction`、`sec_kind`

### `financials`｜財報（綜合損益表、資產負債表）

- 用途：財報類多空卡的基本面數字
- 主鍵：stock_id + date + dataset + type
- 可得時點：date 為財報期末，不是公告日；可得時點須依法定申報期限另行推算
- 注意：FinMind 現行（最終修訂）值，非公告當時版本；重編影響須在個案揭露；長表格式（type＝科目、value＝數值）
- ⚪ fin-20261107：10,466,736 列；期間 1990-03-31～2026-09-30
- 欄位：`stock_id`、`date`、`dataset`、`type`、`value`、`origin_name`

## 四、全部標籤

| 組 | 標籤 | 狀態 | 說明 | 程式 commit | 測試 |
|---|---|---|---|---|---|
| phase1 | data-20261105 | ⛔ 已被取代 | 初版；由 r67 起各修正版取代 |  |  |
| phase1 | data-20261105r67 | ⛔ 已被取代 | 由 r68 取代 |  |  |
| phase1 | data-20261105r67b | ⛔ 已被取代 | 由 r68 取代 |  |  |
| phase1 | data-20261105r68 | ✅ 已驗收 | Eve 複審通過（2026-11-06） | c568158 | 建置時 1 項因環境缺檔未過，重測 47 過（test_output_retest.txt） |
| phase1 | data-20261107r69 | ↩️ 已退回 | Eve 2026-11-10 退回：低價股漲跌停取整後等於基準價（99 列） | 7c7b6f0 | 通過 |
| phase1 | data-20261110r70 | ⛔ 已被取代 | 建置時測試在收集階段中斷（缺 pyyaml），由 r70b 取代 |  |  |
| phase1 | data-20261110r70b | 🟡 待複審 | 補正 Eve 退回 r69：漲跌停取整後不足一升降單位以一單位計 | e3c4580 | 通過 |
| phase2 | data-phase2-20261107c1 | ⛔ 已被取代 | 未送審；外部審查後由 c2 取代 |  |  |
| phase2 | data-phase2-20261107c2 | ↩️ 已退回 | Eve 2026-11-10 退回：2023-02-23 ban_rule 錯標、處置表格與內文日期衝突未標 | a7365cb | 通過 |
| phase2 | data-phase2-20261110c3 | 🟡 待驗收 | 補正 Eve 退回 c2：3.5% 期間延至 2023-02-23、新增 2015 全面禁止期間、處置內文日期比對 | e5d5c18 | 通過 |
| fin | fin-20261107 | ⚪ 未送驗收 | FinMind 現行（最終修訂）值，非公告當時版本 | 7c7b6f0 |  |

原始檔倉庫（建置用，不供回測直接讀取）：

- `raw-phase2`：第二期 12 個官方來源原始檔（每日更新當月／當年檔）
- `raw-market`：第一期官方逐日市場別原始檔與單次探測結果
- `raw-financials`：財報 FinMind 原始回傳
- `raw-progress`：FinMind 下載進度與 StockInfo／Delisting 清單
- `raw-064-annual`：策略064 年報原始檔（個案用）

資料截至日（各來源最後完整檢查日；open_periods 為當時尚未結束、之後會更新的期間）：

- data-phase2-20261107c2：tpex_attention 2026-11-07（open_periods=202611）；tpex_disposal 2026-11-07（open_periods=2026）；tpex_ix 2026-11-07（open_periods=202611）；tpex_margin 2026-11-07；tpex_mark 2026-11-07；twse_fulldelivery 2026-11-07；twse_ix 2026-11-07（open_periods=202611）；twse_margin 2026-11-07；twse_mark 2026-11-07；twse_notice 2026-11-07（open_periods=202611）；twse_punish 2026-11-07（open_periods=2026）；twse_tri 2026-11-07（open_periods=202611）
- data-phase2-20261110c3：tpex_attention 2026-11-09（open_periods=202611）；tpex_disposal 2026-11-09（open_periods=2026）；tpex_ix 2026-11-09（open_periods=202611）；tpex_margin 2026-11-09；tpex_mark 2026-11-09；twse_fulldelivery 2026-11-09；twse_ix 2026-11-09（open_periods=202611）；twse_margin 2026-11-09；twse_mark 2026-11-09；twse_notice 2026-11-09（open_periods=202611）；twse_punish 2026-11-09（open_periods=2026）；twse_tri 2026-11-09（open_periods=202611）

## 五、未登記標籤（load() 不會使用，須先登記並送驗收）

（無）
