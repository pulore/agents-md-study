# Render an HTML file to PNG with headless Chrome.  python3 render.py in.html out.png W H [scale]
# Optional: the post's PNGs are made from the chart HTML this way. Needs Google Chrome installed.
import subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import WORK
html, png, w, h = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
scale = sys.argv[5] if len(sys.argv) > 5 else '1'
prof = os.path.join(WORK, 'chrome-profile')   # scratch profile inside the git-ignored work folder, never /tmp
cmd = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--headless=new', f'--user-data-dir={prof}',
       '--hide-scrollbars', f'--window-size={w},{h}', f'--force-device-scale-factor={scale}', '--virtual-time-budget=3000',
       f'--screenshot={png}', 'file://' + os.path.abspath(html)]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print(r.returncode, os.path.exists(png) and os.path.getsize(png))
