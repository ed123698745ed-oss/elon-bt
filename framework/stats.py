"""統計入口（C1、C5）：只透過 Drive 原版 bt_stats 計算十項統計與聚合 p。

bt_stats 不放進 repo。使用者從 Drive「00_團隊規則／Bot工作手冊」下載原檔後傳入路徑；
本模組核對 sha256 是否為登記版本，再跑 selftest，才載入。
"""
import hashlib

from framework import elon_tools

# 已登記的 bt_stats 原檔雜湊（Drive 檔 1TNOWYLqESHiyAB7sl5BwEu99XLfwo4Ef，9,761 bytes，2026-11-03 核對）
REGISTERED = {
    "1.0": "3869bd4049c0441899ce29676154c70cdf0c7c2c27156d4db1701f74c518d792",
}

_LOADED = {}


def load(path: str, version: str = "1.0"):
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if REGISTERED.get(version) != h:
        raise RuntimeError(f"bt_stats 雜湊不符登記版本 {version}：{h}。不得使用改過或複製修改的版本，回報 Ed。")
    bt = elon_tools.load_bt_stats(path)  # 內含 selftest，未通過即停止
    if bt.VERSION != version:
        raise RuntimeError(f"bt_stats 版本 {bt.VERSION} ≠ {version}")
    _LOADED["bt"] = bt
    _LOADED["sha256"] = h
    return bt


def current():
    if "bt" not in _LOADED:
        raise RuntimeError("尚未以 framework.stats.load() 載入 bt_stats")
    return _LOADED["bt"], _LOADED["sha256"]


def ten_table(trades, by=("combo",), cluster_unit=None):
    bt, _ = current()
    return elon_tools.ten_table(trades, bt, by=by, cluster_unit=cluster_unit)
