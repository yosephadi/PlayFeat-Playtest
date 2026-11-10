"""Shared helpers for the Playwright tests: local server, page with touch, touch drags, check list."""
import os, sys, json, time, socket, subprocess
from contextlib import contextmanager

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
BOT = open(os.path.join(HERE, 'bot.js')).read()


def finish(check, browser, errors, ignore=()):
    """Report results first, then close the browser; Chrome occasionally hangs on close, so exit anyway after 15 s."""
    import threading
    errs = [e for e in errors if not any(x in e for x in ignore)]
    check('no console errors', not errs, errs[:5])
    code = check.report()
    sys.stdout.flush()
    threading.Timer(15, lambda: os._exit(code)).start()
    try:
        browser.close()
    finally:
        os._exit(code)


@contextmanager
def server():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', SITE],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    try:
        yield port
    finally:
        srv.terminate()


class Checks:
    def __init__(self):
        self.items = {}

    def __call__(self, name, ok, info=''):
        self.items[name] = {'ok': bool(ok), 'info': info}
        print('CHECK', 'ok ' if ok else 'FAIL', name, file=sys.stderr, flush=True)

    def report(self):
        print(json.dumps(self.items, indent=1, default=str))
        bad = [k for k, v in self.items.items() if not v['ok']]
        print('FAILED CHECKS:', bad if bad else 'none')
        return 1 if bad else 0


def new_context(p, dpr=1, perms=False, port=None):
    b = p.chromium.launch(channel='chrome', headless=True, args=['--autoplay-policy=no-user-gesture-required'])
    ctx = b.new_context(viewport={'width': 1180, 'height': 820}, has_touch=True, device_scale_factor=dpr, accept_downloads=True)
    if perms:
        ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin=f'http://127.0.0.1:{port}')
    return b, ctx


class Game:
    """One page, opened at a level, with touch helpers."""
    def __init__(self, ctx, port, errors, speed=1, query=''):
        self.page = page = ctx.new_page()
        page.on('console', lambda m: errors.append(m.text) if m.type in ('error', 'warning') else None)
        page.on('pageerror', lambda e: errors.append('PAGEERROR ' + str(e)))
        page.goto(f'http://127.0.0.1:{port}/index.html?speed={speed}{query}')
        self.cdp = ctx.new_cdp_session(page)

    def start(self, level, tester='bot', flow=None):
        self.page.tap(f'button.lv[data-level="{level}"]')
        if flow:
            self.page.tap(f'button.fl[data-flow="{flow}"]')
        self.page.fill('#tester', tester)
        self.page.tap('#startBtn')
        self.page.wait_for_function('window.__pf.S && window.__pf.S.t > 0.05')

    def ev(self, js, arg=None):
        return self.page.evaluate(js, arg) if arg is not None else self.page.evaluate(js)

    def client(self, pt):
        return self.page.evaluate('([x,y]) => window.__pf.toClient(x,y)', [pt['x'], pt['y']])

    def drag(self, a, b, steps=5):
        ca, cb = self.client(a), self.client(b)
        self.cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': ca['x'], 'y': ca['y'], 'id': 1}]})
        for i in range(1, steps + 1):
            self.cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': ca['x'] + (cb['x'] - ca['x']) * i / steps, 'y': ca['y'] + (cb['y'] - ca['y']) * i / steps, 'id': 1}]})
        self.cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})

    def tap(self, pt):
        c = self.client(pt)
        self.cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': c['x'], 'y': c['y']}]})
        self.cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})

    def bot_play(self, timeout=400, extras=False, on_tick=None):
        """Let the bot play until the run ends. Returns action counts."""
        actions, did_air, did_trash = {}, False, False
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = self.ev('(() => { const S = window.__pf.S; return {t: S.t, ended: S.ended} })()')
            if st['ended']:
                break
            if on_tick:
                on_tick(st)
            if extras and st['t'] > 10 and not did_trash:
                spare = self.ev("(() => { const b = window.__pf.S.bubbles.filter(b => b.y > 60 && b.y < 300 && b.ing === 'mushroom')[0]; return b ? {x:b.x, y:b.y} : null })()")
                if spare and not did_air:
                    self.drag(spare, {'x': 160, 'y': 330}); did_air = True; actions['air drop'] = 1; continue
                if spare and did_air:
                    self.drag(spare, self.ev('window.__pf.centers().trash')); did_trash = True; actions['trash'] = 1; continue
            act = self.ev(BOT)
            if act.get('ended'):
                break
            if act.get('wait'):
                time.sleep(0.03); continue
            self.drag(act['from'], act['to'])
            actions[act['label']] = actions.get(act['label'], 0) + 1
            time.sleep(0.02)
        return actions
