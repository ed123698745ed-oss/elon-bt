"""讀 GitHub Release 上的檔案：清冊 JSON、parquet 檔尾（只抓結構與統計，不下載整檔）、整檔下載。"""
import io, json, os, struct, urllib.request

REPO = "ed123698745ed-oss/elon-bt"
UA = {"User-Agent": "elon-bt-catalog"}


def url(tag, name):
    return f"https://github.com/{REPO}/releases/download/{tag}/{name}"


def get(u, rng=None, timeout=120):
    h = dict(UA)
    if rng:
        h["Range"] = rng
    with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=timeout) as r:
        return r.read(), r.headers


def manifest(tag):
    for n in ("manifest.json", "manifest_fin.json", "manifest_revinst.json"):
        try:
            b, _ = get(url(tag, n))
            return n, json.loads(b)
        except Exception:
            continue
    return None, {}


class _Remote(io.RawIOBase):
    """只用 Range 請求讀遠端 parquet；檔尾一次抓回快取。"""

    def __init__(self, u):
        self.u, self.p = u, 0
        _, h = get(u, "bytes=0-0")
        self.size = int(h["Content-Range"].split("/")[1])
        t, _ = get(u, f"bytes={self.size - 8}-{self.size - 1}")
        n = struct.unpack("<I", t[:4])[0]
        self.fs = self.size - 8 - n
        self.foot, _ = get(u, f"bytes={self.fs}-{self.size - 1}")

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.p

    def seek(self, o, w=0):
        self.p = o if w == 0 else (self.p + o if w == 1 else self.size + o)
        return self.p

    def readinto(self, b):
        if self.p >= self.fs:
            d = self.foot[self.p - self.fs:self.p - self.fs + len(b)]
        else:
            d, _ = get(self.u, f"bytes={self.p}-{min(self.p + len(b), self.size) - 1}")
        b[:len(d)] = d
        self.p += len(d)
        return len(d)


def parquet_info(tag, name):
    """回傳 {rows, size, columns:[{name,type}], ranges:{欄: [min,max]}}；min/max 取自檔內統計，只算日期類欄位。"""
    import pyarrow.parquet as pq
    f = _Remote(url(tag, name))
    pf = pq.ParquetFile(f)
    md, sch = pf.metadata, pf.schema_arrow
    cols = [{"name": n, "type": str(t)} for n, t in zip(sch.names, sch.types)]
    dateish = [c["name"] for c in cols if "timestamp" in c["type"] or c["name"] in ("date", "ex_date", "announce", "data_date", "effective", "start", "end")]
    ranges = {}
    for c in dateish:
        i = sch.names.index(c)
        lo = hi = None
        for g in range(md.num_row_groups):
            s = md.row_group(g).column(i).statistics
            if s is None or not s.has_min_max:
                lo = hi = None
                break
            lo = s.min if lo is None else min(lo, s.min)
            hi = s.max if hi is None else max(hi, s.max)
        if lo is not None:
            ranges[c] = [str(lo)[:10], str(hi)[:10]]
    return {"rows": md.num_rows, "size": f.size, "columns": cols, "ranges": ranges}


def download(tag, name, dst):
    with urllib.request.urlopen(urllib.request.Request(url(tag, name), headers=UA), timeout=600) as r, open(dst, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)


def release_tags():
    """列出 repo 全部 Release 標籤（GitHub API；Actions 內用 GITHUB_TOKEN）。失敗回傳 None。"""
    tags, page = [], 1
    h = dict(UA, Accept="application/vnd.github+json")
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    try:
        while True:
            b, _ = get_h(f"https://api.github.com/repos/{REPO}/releases?per_page=100&page={page}", h)
            j = json.loads(b)
            tags += [r["tag_name"] for r in j]
            if len(j) < 100:
                return tags
            page += 1
    except Exception:
        return None


def get_h(u, headers, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(u, headers=headers), timeout=timeout) as r:
        return r.read(), r.headers
