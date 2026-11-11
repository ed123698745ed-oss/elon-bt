"""解析公開資訊觀測站 t120sg01（轉(交)換公司債發行資料）頁面為一列欄位。日期轉西元；金額去逗號；取不到為 None。"""
import re

LABELS = ["申請日期", "核准日期", "發行日期", "發行期限", "到期日期", "下櫃日期", "債券掛牌情形", "掛牌/發行地點", "掛牌日期",
          "債券代碼", "債券簡稱", "申請發行總額", "實際發行總額", "本月底發行餘額", "發行面額", "發行張數", "發行價格",
          "票面利率", "發行時轉(交)換價格", "轉換溢價率", "轉(交)換期間", "最新轉(交)換價格", "最近轉(交)換價格生效日期",
          "擔保情形", "債券賣回權條件", "債券買回權條件", "下一次賣回權日期", "下一次賣回權價格", "承銷機構", "募集方式",
          "本月發行餘額變動日期", "本月發行餘額變動原因", "公司決議私募有價證券股東會或董事會日期", "債券期別"]
STOP = LABELS + ["發行幣別", "發行日匯率", "債券中文名稱", "發行人", "債券英文名稱", "本次價格重設日期", "下次價格重設日期", "CFI代號",
                 "國際編碼", "本月受理轉(交)換之公司債張數", "是否依約定按時還本", "債息基準日", "轉換匯率", "債息對照表內容",
                 "還本敘述", "是否為永續發展債券", "賣回權收益率", "買回權收益率", "受 託 人", "簽證機構", "過戶機構",
                 "信用評等等級", "限制條款之內容", "備註", "認購對象", "發行辦法之內容", "受託契約內容", "還本付息現金流量明細", "（以佰元價表示"]


def clean_text(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t).replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t)


def roc(s):
    m = re.search(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", s or "")
    if not m:
        return None
    y, mo, d = int(m[1]) + 1911, int(m[2]), int(m[3])
    return f"{y:04d}-{mo:02d}-{d:02d}"


def num(s):
    m = re.search(r"-?[\d,]+(?:\.\d+)?", s or "")
    return float(m.group(0).replace(",", "")) if m else None


def parse(html):
    x = clean_text(html)
    i = x.find("之轉(交)換公司債發行資料")
    if i < 0:
        return None
    x = x[i:]
    pat = "|".join(re.escape(l) for l in sorted(STOP, key=len, reverse=True))
    raw = {}
    for m in re.finditer(rf"({pat})\s*：\s?(.*?)(?=\s*(?:{pat})\s*：|\s*（以佰元價表示|$)", x):
        raw.setdefault(m.group(1), m.group(2).strip())
    g = raw.get
    conv = g("轉(交)換期間") or ""
    cs, ce = (re.findall(r"\d{2,3}/\d{1,2}/\d{1,2}", conv) + [None, None])[:2]
    return {
        "bond_id": (g("債券代碼") or "").strip() or None,
        "short_name": g("債券簡稱"),
        "series": g("債券期別"),
        "raise_way": g("募集方式"),
        "apply_date": roc(g("申請日期")), "approve_date": roc(g("核准日期")),
        "issue_date": roc(g("發行日期")), "tenor": g("發行期限"), "maturity_date": roc(g("到期日期")),
        "delist_date": roc(g("下櫃日期")), "listing_status": g("債券掛牌情形"), "listing_date": roc(g("掛牌日期")),
        "amount_applied": num(g("申請發行總額")), "amount_issued": num(g("實際發行總額")),
        "outstanding_month_end": num(g("本月底發行餘額")),
        "face_value": num(g("發行面額")), "units": num(g("發行張數")), "issue_price": num(g("發行價格")),
        "coupon_rate": num(g("票面利率")),
        "conv_price_issue": num(g("發行時轉(交)換價格")), "conv_premium": num(g("轉換溢價率")),
        "conv_start": roc(cs), "conv_end": roc(ce),
        "conv_price_latest": num(g("最新轉(交)換價格")), "conv_price_latest_eff": roc(g("最近轉(交)換價格生效日期")),
        "guarantee": g("擔保情形"), "put_terms": g("債券賣回權條件"), "call_terms": g("債券買回權條件"),
        "next_put_date": roc(g("下一次賣回權日期")), "next_put_price": num(g("下一次賣回權價格")),
        "underwriter": g("承銷機構"),
        "private_board_date": roc(g("公司決議私募有價證券股東會或董事會日期")),
        "balance_change_date": roc(g("本月發行餘額變動日期")), "balance_change_reason": g("本月發行餘額變動原因"),
    }
