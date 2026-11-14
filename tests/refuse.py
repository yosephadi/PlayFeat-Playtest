"""Refused items: held ~300 ms (CONFIG common.refuseHoldMs), can't be grabbed or stacked on, then fall like any
dropped item. Runs at normal speed so the hold is real time. Usage: refuse.py"""
import sys, time
from playwright.sync_api import sync_playwright
from harness import server, Checks, new_context, Game, finish

check, errors = Checks(), []
KEY = "(it => it ? (it.t === 'flatbread' ? 'flatbread:' + it.st : it.t === 'dish' ? 'dish:' + it.dish : it.t) : null)"
ITEM = {'flatbread:baked': "{t:'flatbread', st:'baked', bake:6, over:0}", 'flatbread:burnt': "{t:'flatbread', st:'burnt', bake:6, over:12}",
        'sorbet': "{t:'sorbet'}", 'drizzle': "{t:'drizzle'}", 'pepper': "{t:'pepper'}"}

with server() as port, sync_playwright() as p:
    b, ctx = new_context(p, port=port)
    g = Game(ctx, port, errors, speed=1)
    g.start('1-6', 'refuse-test')
    K = g.ev('window.__pf.centers()')
    hold = g.ev('window.__pf.CFG.common.refuseHoldMs')
    check('hold time comes from CONFIG (refuseHoldMs = 300)', hold == 300)

    def reset(plate=None, bowl=None):
        g.ev(f"""(() => {{ const S = window.__pf.S; S.plates[0] = {ITEM[plate] if plate else 'null'}; S.bowl = {ITEM[bowl] if bowl else 'null'};
                S.hovering.length = 0; S.falling.length = 0; S.bubbles.length = 0; S.grill[0] = null; S.storage[0] = null; S.storage[1] = null;
                S.seated.forEach(c => {{ c.left = c.patienceMax = 9999; }}); return 1 }})()""")

    def drop(item, target, src=(200, 330)):
        """Put the item in an (ungated) hover slot and touch-drag it onto the target. Returns the game time of the drop."""
        g.ev(f"(() => {{ window.__pf.S.hovering.push({{ item: Object.assign({{id: Math.random()}}, {ITEM[item]}), x: {src[0]}, y: {src[1]}, age: 0 }}); return 1 }})()")
        g.drag({'x': src[0], 'y': src[1]}, target)
        return g.ev('window.__pf.S.t')

    state = lambda: g.ev(f"""(() => {{ const S = window.__pf.S, k = {KEY};
        return {{ t: S.t, bowl: k(S.bowl), plate: k(S.plates[0]), held: k(S.held && S.held.item),
                 hover: S.hovering.map(h => [k(h.item), h.releaseAt != null, Math.round(h.x), Math.round(h.y)]),
                 falling: S.falling.map(f => [k(f.item), Math.round(f.x), Math.round(f.y)]) }}; }})()""")

    # 1) flatbread on the bowl: held, not grabbable, then falls; bowl unchanged; vanishes at the bottom
    reset()
    drop('flatbread:baked', K['bowl'])
    s0 = state()
    check('flatbread on bowl: refused, held at the drop point, bowl unchanged', s0['bowl'] is None and s0['hover'] and s0['hover'][0][0] == 'flatbread:baked' and s0['hover'][0][1], s0)
    hx, hy = s0['hover'][0][2], s0['hover'][0][3]
    g.tap({'x': hx, 'y': hy})          # try to grab it again within 300 ms
    s1 = state()
    check('cannot grab it again during the hold', s1['held'] is None and len(s1['hover']) == 1, s1)
    g.page.wait_for_timeout(hold + 80)  # 300 ms + a few frames
    s2 = state()
    check('after 300 ms + a few frames: not attached, falling, bowl unchanged', s2['hover'] == [] and s2['bowl'] is None and s2['falling'] and s2['falling'][0][0] == 'flatbread:baked', s2)
    check('it falls straight down from where it was held', s2['falling'] and abs(s2['falling'][0][1] - hx) <= 1 and s2['falling'][0][2] >= hy, (hx, hy, s2['falling']))
    g.page.wait_for_function("!window.__pf.S.falling.length", timeout=4000)
    ev = g.ev('window.__pf.S.events')
    check('then it leaves the screen like any dropped item (item_dropped_vanished)', any(e['e'] == 'item_dropped_vanished' and e['item'] == 'flatbread(baked)' for e in ev) and state()['bowl'] is None)
    wp = [e for e in ev if e['e'] == 'wrong_placement']
    check('log: wrong_placement with item, target, time, level', wp and wp[-1]['item'] == 'flatbread(baked)' and wp[-1]['station'] == 'bowl' and 't' in wp[-1] and wp[-1]['level'] == '1-6', wp[-1:])

    # 2) a valid drop still works
    reset()
    drop('sorbet', K['bowl'])
    s = state()
    check('valid drop still works (sorbet into the empty bowl)', s['bowl'] == 'sorbet' and s['hover'] == [] and s['falling'] == [], s)

    # 3) sorbet / drizzle on a plate holding a flatbread: refused with the same hold-then-fall
    for it in ('sorbet', 'drizzle'):
        reset(plate='flatbread:baked')
        drop(it, K['plate'])
        a = state()
        g.page.wait_for_timeout(hold + 80)
        c = state()
        check(f'{it} on the flatbread plate: refused, held, then falls; plate unchanged',
              a['plate'] == 'flatbread:baked' and a['hover'] and a['hover'][0][0] == it and c['hover'] == [] and c['falling'] and c['falling'][0][0] == it and c['plate'] == 'flatbread:baked', (a, c))

    # 4) after the hold it follows the normal rules: it can be caught mid-air
    reset()
    drop('pepper', K['bowl'])
    g.page.wait_for_function("window.__pf.S.falling.length === 1", timeout=2000)
    f = g.ev("(() => { const f = window.__pf.S.falling[0]; return {x: f.x, y: f.y} })()")
    c = g.client(f)
    g.cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': c['x'], 'y': c['y'], 'id': 1}]})
    caught = g.ev("window.__pf.S.held && window.__pf.S.held.item.t")
    g.cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    check('after the hold it can be caught mid-air like any falling item', caught == 'pepper')

    # 5) two refusals in quick succession; the busy bowl refuses even a valid item during the hold
    reset()
    g.ev(f"(() => {{ const S = window.__pf.S; S.hovering.push({{ item: {{id: 1, t: 'pepper'}}, x: 200, y: 330, age: 0 }}, {{ item: {{id: 2, t: 'sorbet'}}, x: 330, y: 330, age: 0 }}); return 1 }})()")
    g.drag({'x': 200, 'y': 330}, K['bowl'], steps=1); t1 = g.ev('window.__pf.S.t')
    g.drag({'x': 330, 'y': 330}, K['bowl'], steps=1); t2 = g.ev('window.__pf.S.t')
    s = state()
    check('second drop on a bowl that is holding a refused item is refused too', t2 - t1 < hold / 1000 and s['bowl'] is None and len(s['hover']) == 2 and all(h[1] for h in s['hover']), (round(t2 - t1, 3), s))
    g.page.wait_for_timeout(hold + 120)
    s = state()
    check('both refused items fall independently', s['hover'] == [] and sorted(x[0] for x in s['falling']) == ['pepper', 'sorbet'], s)
    g.page.wait_for_function("!window.__pf.S.falling.length", timeout=4000)
    drop('sorbet', K['bowl'])
    check('after the hold the bowl accepts drops again', state()['bowl'] == 'sorbet')

    # 6) refused near the screen edge (front storage insert at the right edge): straight down, stays on screen
    reset()
    g.ev("(() => { window.__pf.S.storage[1] = null; return 1 })()")
    edge = {'x': min(1010, K['storage'][1]['x'] + 50), 'y': K['storage'][1]['y']}
    drop('flatbread:burnt', edge)
    a = state()
    g.page.wait_for_timeout(hold + 80)
    c = state()
    check('refused at the right edge: held, then falls straight down inside the screen',
          a['hover'] and a['hover'][0][0] == 'flatbread:burnt' and c['falling'] and abs(c['falling'][0][1] - a['hover'][0][2]) <= 1 and 0 <= c['falling'][0][1] <= 1024, (a, c))

    # 7) the hold is game time: a pause freezes it
    g.page.wait_for_function("!window.__pf.S.falling.length", timeout=4000)
    reset()
    drop('pepper', K['bowl'])
    g.tap(K['pause'])
    g.page.wait_for_timeout(hold + 300)
    s = state()
    check('pause during the hold: the item stays held (game time is frozen)', len(s['hover']) == 1 and s['falling'] == [], s)
    g.page.tap('#resumeBtn')
    g.page.wait_for_timeout(hold + 120)
    s = state()
    check('after resuming it falls', s['hover'] == [] and len(s['falling']) == 1, s)
    check('refused items never change score or customers', g.ev('window.__pf.S.score') == 0 and g.ev('window.__pf.S.lost') == 0)
    finish(check, b, errors)
