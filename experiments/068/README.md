# 068 FinLab範例-60日動能ROE濾網｜快篩紀錄（只含樣本內 ≤2022-06-30）

- quick_v1：2026-11-11 01:05 快篩第一版（策略卡 M0、M1、M1-同期、9 組變體＋E-M1-ADJ）。
- quick_v2：2026-11-11 追加 E-Test（E-BUF50、E-SKIP20、E-STOP15；D-068-20261111-0949-1）；策略卡組合與 E-M1-ADJ 逐筆與 v1 完全相同。
- 每個資料夾：程式、逐筆明細（trades／etrades，含排除原因）、開盤取消（cancels）、十項統計與回撤三項（未四捨五入 CSV）、等權淨值、報告 HTML、SHA256SUMS。
- 待資料：V-REV（等共用資料層 revinst month_revenue，D-068-20261111-0055-1）；合併組 V-MERGE（挑選協定 merge068.py，等 V-REV）。
- fetch_rev.py／ids068.txt：已停用的 068 自抓月營收（未產生任何結果）。
- 資料標籤：data-20261105r68（已驗收）；fin-20261107、data-phase2-20261110c3（未驗收）。統計：bt_stats 1.2。
