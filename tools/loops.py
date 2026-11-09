"""Run tools/loop_finder.js in Chrome (Playwright) on the encoded music files and print loop points.
Usage: PYTHON_WITH_PLAYWRIGHT tools/loops.py"""
import os, sys, json, subprocess, socket, time
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', ROOT],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(0.8)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        page = b.new_page()
        page.goto(f'http://127.0.0.1:{port}/tools/')
        page.add_script_tag(path=os.path.join(ROOT, 'tools', 'loop_finder.js'))
        out = {}
        out['music_kitchen'] = page.evaluate("findLoop('/audio/music/shake_and_bake.m4a', {minLag: 30, aMin: 4, endGuard: 6})")
        out['music_title'] = page.evaluate("findLoop('/audio/music/outer_space_loop.m4a', {minLag: 40, aMin: 0.3, endGuard: 0.3})")
        print(json.dumps(out, indent=1))
        b.close()
finally:
    srv.terminate()
