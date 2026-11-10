# elon-bt

Ai Bot Team｜Elon 多空配置共用資料層與回測框架。

**有哪些資料可用、驗收了沒：看 [CATALOG.md](CATALOG.md)。取資料一律用 `framework.data.load()`（預設只給已驗收標籤）。**

設計依據：Drive 03_策略包《Elon_多空配置共用資料層與回測框架_一頁設計_V01_20261103》。

## 結構

```
data_layer/   下載與清理程式（日K、公司行動、市場別、交易日曆…）
framework/    必經函式（交易日、當時母體、成交判定、報酬、樣本切分、統計呼叫、設定檔）
checks/       交件前自動檢查（FAIL／WARN）
tests/        回歸測試（過去退回案例）
manifest/     資料清冊（來源、下載日、版本、筆數、sha256）
.github/workflows/  手動觸發的資料建置
```

## 規則

- 資料檔不進 repo，發佈在 Releases；標籤與驗收狀態登記在 data_catalog/registry.yml（依 Eve 結果），清單由 tools/gen_catalog.py 自動產生。
- bt_stats 不放 repo：執行時由 Drive 原檔載入並核對 sha256。
- FinMind token 只放 repo Secrets（FINMIND_TOKEN_1～4），不寫進程式。
- 缺值不推估，標「資料不足」；代號一律文字。
