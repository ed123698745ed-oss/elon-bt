"""探測公開資訊觀測站（舊站）頁面與 ajax：讀 jobs/probe_mops.txt，每行「名稱<TAB>URL<TAB>POST 參數（可空）」，
回應存 out_probe/<名稱>.html；Referer 用對應的非 ajax 頁。"""
import os, time, urllib.request
UA = "Mozilla/5.0 (elon-bt probe)"
os.makedirs("out_probe", exist_ok=True)
for line in open("jobs/probe_mops.txt", encoding="utf-8"):
    if not line.strip() or line.startswith("#"):
        continue
    parts = line.rstrip("\n").split("\t")
    name, url = parts[0], parts[1]
    data = parts[2].encode() if len(parts) > 2 and parts[2] else None
    ref = url.replace("ajax_", "")
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Referer": ref}), timeout=60)
        b = r.read()
        open(f"out_probe/{name}.html", "wb").write(b)
        print(name, r.status, len(b))
    except Exception as e:
        print(name, "ERR", e)
    time.sleep(3)
