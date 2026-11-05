"""bt_stats 執行雜湊與 selftest 實際輸出（退回-67：交件標示版本須附執行證據；只證明本版，不推及其他版本）。"""
import hashlib, os, subprocess, sys
from datetime import datetime, timezone
BT = os.environ.get("BT_STATS_PATH", "/home/claude/vendor/bt_stats_v1.0.py")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
b = open(BT, "rb").read()
r = subprocess.run([sys.executable, BT, "--selftest"], capture_output=True, text=True)
commit = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
txt = (f"執行時間 {datetime.now(timezone.utc).isoformat(timespec='seconds')}｜commit {commit}\n"
       f"檔案 {os.path.basename(BT)}｜{len(b)} bytes｜sha256 {hashlib.sha256(b).hexdigest()}\n"
       f"登記值（framework/stats.py REGISTERED['1.0']）3869bd4049c0441899ce29676154c70cdf0c7c2c27156d4db1701f74c518d792\n"
       f"Python {sys.version.split()[0]}｜selftest 結束碼 {r.returncode}\n--- stdout ---\n{r.stdout}--- stderr ---\n{r.stderr}")
os.makedirs(os.path.join(ROOT, "experiments", "out_precheck"), exist_ok=True)
open(os.path.join(ROOT, "experiments", "out_precheck", "bt_stats_selftest.txt"), "w").write(txt)
print(txt)
