"""報告數字表格一律由程式從明細產生（C9、D2、E4），不手打。"""
from framework import elon_tools, stats


def result_table(trades, by=("combo",), cluster_unit=None):
    """回傳 (未四捨五入原表, 報告用 markdown)。原表另存全精度 CSV 交件。"""
    raw = stats.ten_table(trades, by=by, cluster_unit=cluster_unit)
    return raw, elon_tools.to_markdown(raw)
