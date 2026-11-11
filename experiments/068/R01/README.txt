068 V01／R01 原始數據明細
欄位：trade_id 交易編號、combo 組合、is_etest 是否討論衍生、symbol 代號、signal_date 換股訊號日、info_time 資料可用時點、entry_time/entry_date/entry_px 進場（開盤，未還原價）、exit_date/exit_px 出場（開盤）、plan_exit_date 預定出場日、exit_reason 出場原因、ret 報酬（小數；固定股數加實得現金）、hold_days 持有交易日數（含首尾）、cluster 聚合單位（進場日）、sample 樣本內／樣本外／隔離帶／未完成、excluded_reason 排除原因、ret_flags 報酬計算註記。
cancels：進場日開盤漲停／停牌／限幅待查而取消的名額（不遞補）。sens_*：敏感度 162 格（combo＝組合|參數一|參數二）。R01_*：未四捨五入統計表（bt_stats 1.2）；R01_excess：相對加權報酬指數近似超額（描述性）。
資料來源：elon-bt data-20261110r72、data-phase2-20261111c5、fin-20261107、revinst-20261111（GitHub ed123698745ed-oss/elon-bt Releases；下載日 2026-11-11）。單位：價格元、報酬小數。
