"""逐筆明細的唯一產生方式：持有日與報酬由框架計算並蓋章，交件前檢查會核對章。"""
from __future__ import annotations

import hashlib
import json

from framework.core import Calendar, Split, _d, norm_id, trade_return

FRAMEWORK_VERSION = "0.1"
RET_STAMP = f"framework.trade_return@{FRAMEWORK_VERSION}"
HOLD_STAMP = f"framework.Calendar.hold_days@{FRAMEWORK_VERSION}"


def load_params(path: str):
    """參數只寫在一個設定檔（C9、D2）；回傳 (參數, sha256)。程式與報告都讀這份。"""
    raw = open(path, "rb").read()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def trade_row(cal: Calendar, split: Split | None, *, trade_id, combo, is_etest, symbol, direction,
              info_time, entry_time, entry_date, entry_session, entry_px,
              exit_date, exit_session, exit_px, actions, cluster=None, price_series_hash=None,
              excluded_reason=None, **extra) -> dict:
    """產生一筆標準明細（elon-backtest 欄位＋框架欄位）。排除的交易 ret 留空並寫原因。"""
    row = dict(trade_id=str(trade_id), combo=str(combo), is_etest=bool(is_etest), symbol=norm_id(symbol),
               direction=direction, info_time=str(info_time), entry_time=str(entry_time),
               entry_date=_d(entry_date).isoformat(), entry_session=entry_session, entry_px=entry_px,
               exit_date=_d(exit_date).isoformat() if exit_date else None, exit_session=exit_session,
               exit_px=exit_px, cluster=cluster, price_series_hash=price_series_hash,
               excluded_reason=excluded_reason or None, ret=None, hold_days=None,
               sample=split.label(entry_date) if split else None,
               ret_by=None, hold_by=None, ret_flags=None)
    row["sample"] = {"IS": "樣本內", "OOS": "樣本外", "GAP": "隔離帶", None: None}[row["sample"]]
    if not excluded_reason:
        tr = trade_return(direction, entry_px, exit_px, entry_date, exit_date, actions)
        row.update(ret=tr.ret, ret_by=RET_STAMP, hold_days=cal.hold_days(entry_date, exit_date),
                   hold_by=HOLD_STAMP, ret_flags="；".join(tr.flags) or None)
    row.update(extra)
    return row
