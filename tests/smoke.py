"""Mechanic checks: losses/overtime, useful-bubble rule, order pools, burn timing, pause, replace rule, wrong dish, save warning.
Usage: smoke.py OUTDIR"""
import sys
from playwright.sync_api import sync_playwright
from harness import server, Checks, new_context, Game, finish

OUT = sys.argv[1]
check, errors = Checks(), []
with server() as port, sync_playwright() as p:
    b, ctx = new_context(p, port=port)

    g = Game(ctx, port, errors, speed=12); g.start('1-4')
    g.page.wait_for_selector('#summary:not(.hidden)', timeout=60000)
    rec = g.ev('window.__pf.S.record'); ev = rec['events']
    ups = [e for e in ev if e['e'] == 'customer_stepped_up']
    check('idle 1-4 (refill): everyone who stepped up is lost, score 0, overtime', ups and rec['customersLost'] == len(ups) and rec['score'] == 0 and rec['runTimeSec'] > 90, (len(ups), rec['customersLost'], rec['runTimeSec']))
    check('idle 1-4: orders = pepper first, angry sorbet at #4 and #7', rec['orderSequence'][0] == 'pepper' and [i + 1 for i, o in enumerate(rec['orderSequence']) if o.startswith('ANGRY')] == [4, 7], rec['orderSequence'])
    useful = [e['t'] for e in ev if e['e'] == 'bubble_spawned' and e['useful']]
    check('useful bubble at least every 6 s (within one 1/60 s frame)', max(b2 - a for a, b2 in zip(useful, useful[1:])) <= 6.0 + 1 / 60 + 0.005)
    g.page.close()

    # refill orders are random after the first: they differ between runs
    seqs = set()
    for i in range(4):
        g = Game(ctx, port, errors, speed=8); g.start('1-2')
        g.page.wait_for_function('window.__pf.S.orderSequence.length >= 5', timeout=30000)
        seqs.add(tuple(g.ev('window.__pf.S.orderSequence.slice(0, 5)')))
        g.page.close()
    check('1-2 orders vary between starts (after the fixed first order)', len(seqs) > 1 and all(sq[0] == 'pepper' for sq in seqs), seqs)

    g = Game(ctx, port, errors, speed=4); g.start('1-1')
    K = g.ev('window.__pf.centers()')
    for _ in range(300):
        bub = g.ev("(() => { const b = window.__pf.S.bubbles.find(b => b.ing==='flatbread' && b.y > 70); return b ? {x:b.x,y:b.y} : null })()")
        if bub: break
        g.page.wait_for_timeout(20)
    g.drag(bub, K['grill'])
    g.page.wait_for_timeout(500)
    g.tap(K['pause']); g.page.wait_for_timeout(300)
    t2 = g.ev('window.__pf.S.t'); g.page.wait_for_timeout(400); t3 = g.ev('window.__pf.S.t')
    check('pause freezes time', g.ev('window.__pf.S.paused') and t2 == t3 and g.page.is_visible('#pauseOv'))
    g.page.tap('#resumeBtn')
    g.page.wait_for_function("window.__pf.S.events.some(e => e.e === 'flatbread_burnt')", timeout=20000)
    ev = g.ev('window.__pf.S.events')
    placed = next(e['t'] for e in ev if e['e'] == 'item_placed' and e['on'] == 'grill')
    glow = next(e['t'] for e in ev if e['e'] == 'flatbread_glowing'); burnt = next(e['t'] for e in ev if e['e'] == 'flatbread_burnt')
    check('warning sign window: last 3 s before burn', g.ev('window.__pf.CFG.common.burnWarningSec') == 3)
    check('glow at +14 s, burn at +18 s', abs(glow - placed - 14) < 0.1 and abs(burnt - placed - 18) < 0.1)
    g.drag(K['grill'], K['plate']); g.page.wait_for_timeout(50)
    ev = g.ev('window.__pf.S.events')
    check('burnt flatbread refused by plate', g.ev("window.__pf.S.plates[0] === null") and any(e['e'] == 'wrong_placement' and e['station'] == 'plate' for e in ev))
    g.page.wait_for_function("!window.__pf.S.hovering.length", timeout=3000)  # held ~300 ms (game time), then it falls
    check('refused item falls after the hold, plate untouched', g.ev("window.__pf.S.plates[0] === null"))
    g.ev("(() => { window.__pf.S.storage[0] = {id: 9999, t: 'dish', dish: 'mushroom'}; return 1 })()")
    before = g.ev('[window.__pf.S.seated.length, window.__pf.S.lost]')
    g.drag(K['storage'][0], K['slots'][0])
    check('wrong dish refused, no penalty', any(e['e'] == 'wrong_dish_refused' for e in g.ev('window.__pf.S.events')) and g.ev('[window.__pf.S.seated.length, window.__pf.S.lost]') == before and g.ev('window.__pf.S.storage[0]') is None)
    g.page.close()

    g = Game(ctx, port, errors); g.start('1-3')
    K = g.ev('window.__pf.centers()')
    g.ev("(() => { const S = window.__pf.S; S.storage[0] = {id: 2, t: 'flatbread', st: 'baked', bake: 6, over: 0}; return 1 })()")
    g.drag(K['storage'][0], K['plate'])
    check('baked flatbread goes on the empty plate', g.ev("window.__pf.S.plates[0].st === 'baked'"))
    g.ev("(() => { const S = window.__pf.S; S.storage[1] = {id: 3, t: 'pepper'}; return 1 })()")
    g.drag(K['storage'][1], K['plate'])
    check('pepper on baked flatbread = dish', g.ev("window.__pf.S.plates[0].t === 'dish' && window.__pf.S.plates[0].dish === 'pepper'"))
    g.ev("(() => { const S = window.__pf.S; S.bowl = {id: 4, t: 'sorbet'}; S.storage[1] = {id: 5, t: 'drizzle'}; return 1 })()")
    g.drag(K['storage'][1], K['bowl'])
    check('sorbet then drizzle in bowl = dish', g.ev("window.__pf.S.bowl.dish === 'sorbet'"))
    g.ev("(() => { const S = window.__pf.S; S.storage[0] = {id: 6, t: 'mushroom'}; S.storage[1] = {id: 7, t: 'pepper'}; S.falling.length = 0; return 1 })()")
    g.drag(K['storage'][1], K['storage'][0])
    check('insert replace: old item falls', g.ev("window.__pf.S.storage[0].t === 'pepper' && window.__pf.S.falling[0].item.t === 'mushroom'"))
    g.page.evaluate("Object.defineProperty(document, 'hidden', {value: true, configurable: true}); document.dispatchEvent(new Event('visibilitychange'))")
    check('auto-pause when page hidden', g.ev('window.__pf.S.paused'))
    g.page.evaluate("Object.defineProperty(document, 'hidden', {value: false, configurable: true})")
    g.page.evaluate("(() => { localStorage.setItem = () => { throw new Error('quota') }; return 1 })()")
    g.page.tap('#stopBtn'); g.page.wait_for_selector('#summary:not(.hidden)')
    check('stopped run + save failure shown', g.ev('window.__pf.S.record.ended') == 'stopped' and 'could not be saved' in g.page.inner_text('#status'))
    finish(check, b, errors, ignore=('localStorage save failed',))  # the save failure is forced on purpose above
