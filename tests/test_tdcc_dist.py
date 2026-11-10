"""tdcc_dist 解析：週別年份推定、兩種原檔格式、重疊週一致性。"""
import json
import pandas as pd
from data_layer import tdcc_dist as T


def test_week_year_rollover():
    assert T._week_date("16W01", "12/31") == pd.Timestamp("2015-12-31")
    assert T._week_date("16W14", "04/01") == pd.Timestamp("2016-04-01")
    assert T._week_date("14W01", "-") is None


def test_table_and_compact_merge(tmp_path):
    lv = ";".join(["1"] * 8)
    table = {"stocks": {"2383": {
        "people": {"head": ["週別|統計日期|當週股價|集保庫存(人)|各持股等級股東之持有人數(人)"],
                   "wk": ["16W46;11/18;60;+1;+1;8;" + lv, "16W45;11/11;59;+1;+1;8;" + lv, "15W05;-;50;0;0;-;" + lv]},
        "pct": {"head": ["週別|統計日期|當週股價|集保庫存(萬張)|各持股等級股東之持有比例(%)"],
                "wk": ["16W46;11/18;60;+1;+1;31.8;" + ";".join(["12.5"] * 8), "16W45;11/11;59;+1;+1;31.8;" + ";".join(["12.5"] * 8)]}}}}
    compact = {"head": "資料日期;收盤價;集保庫存(萬張);總股東人數;" + ";".join(["x"] * 16),
               "stocks": {"2383": {"wk": ["20161118;60;31.8;8;" + lv + ";" + ";".join(["12.5"] * 8)]}}}
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(table), encoding="utf-8")
    b.write_text(json.dumps(compact), encoding="utf-8")
    df, log = T.build([str(a), str(b)], str(tmp_path / "out"))
    assert len(df) == 2 and log["overlap_rows"] == 2 and log["overlap_conflicts"] == 0
    assert df.date.min() == pd.Timestamp("2016-11-11") and df.stock_id.dtype.kind in "OU" or str(df.stock_id.dtype) == "str"
    assert (df.holders == 8).all() and T.big_ratio(df, 400).iloc[0] == 37.5
