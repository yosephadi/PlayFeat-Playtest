"""Every item x every station state: accepted items are placed, refused ones hover, and each refusal logs
wrong_placement + plays sfx_wrong_place. Expected results are written out here from the rule (not read from CFG).
Usage: placement.py"""
import sys
from playwright.sync_api import sync_playwright
from harness import server, Checks, new_context, Game

ITEMS = {
    'flatbread:raw': "{t:'flatbread', st:'raw', bake:0, over:0}", 'flatbread:baked': "{t:'flatbread', st:'baked', bake:6, over:0}",
    'flatbread:burnt': "{t:'flatbread', st:'burnt', bake:6, over:12}", 'pepper': "{t:'pepper'}", 'mushroom': "{t:'mushroom'}",
    'sorbet': "{t:'sorbet'}", 'drizzle': "{t:'drizzle'}", 'dish:pepper': "{t:'dish', dish:'pepper'}",
    'dish:mushroom': "{t:'dish', dish:'mushroom'}", 'dish:sorbet': "{t:'dish', dish:'sorbet'}",
}
ALL = set(ITEMS)
NOT_BURNT = ALL - {'flatbread:burnt'}
# station, starting content, accepted items, JS that reads the station, expected content after a combo
CASES = [
    ('plate', None, {'flatbread:baked', 'dish:pepper', 'dish:mushroom'}),
    ('plate', 'flatbread:baked', {'pepper', 'mushroom'}),
    ('plate', 'dish:pepper', set()),
    ('bowl', None, {'sorbet', 'dish:sorbet'}),
    ('bowl', 'sorbet', {'drizzle'}),
    ('bowl', 'dish:sorbet', set()),
    ('grill', None, {'flatbread:raw', 'flatbread:baked'}),
    ('grill', 'flatbread:raw', {'flatbread:raw', 'flatbread:baked'}),   # full grill: new flatbread replaces (as before)
    ('storage', None, NOT_BURNT),
    ('storage', 'pepper', NOT_BURNT),                                   # occupied insert: replaces (as before)
    ('trash', None, ALL),
]
SLOT = {'plate': 'S.plates[0]', 'bowl': 'S.bowl', 'grill': 'S.grill[0]', 'storage': 'S.storage[0]', 'trash': 'null'}
STATION_NAME = {'plate': 'plate', 'bowl': 'bowl', 'grill': 'grill', 'storage': 'storage1', 'trash': 'trash'}
COMBO = {('flatbread:baked', 'pepper'): 'dish:pepper', ('flatbread:baked', 'mushroom'): 'dish:mushroom', ('sorbet', 'drizzle'): 'dish:sorbet'}

check, errors = Checks(), []
results, refusals = [], 0
with server() as port, sync_playwright() as p:
    b, ctx = new_context(p, port=port)
    g = Game(ctx, port, errors, speed=0.05)   # almost frozen time: nothing bakes or leaves during the test
    g.start('1-3', 'placement-test')
    K = g.ev('window.__pf.centers()')
    target = {'plate': K['plate'], 'bowl': K['bowl'], 'grill': K['grill'], 'storage': K['storage'][0], 'trash': K['trash']}
    src = {'x': 200, 'y': 330}   # empty sky: the item hovers here and is dragged from here
    key_js = "(it => it ? (it.t === 'flatbread' ? 'flatbread:' + it.st : it.t === 'dish' ? 'dish:' + it.dish : it.t) : null)"
    for station, start, accepted in CASES:
        for item in ITEMS:
            setup = f"""(() => {{ const S = window.__pf.S;
              S.plates[0] = null; S.bowl = null; S.grill[0] = null; S.storage[0] = null; S.storage[1] = null;
              S.hovering.length = 0; S.falling.length = 0; S.bubbles.length = 0;
              {SLOT[station] + ' = ' + ITEMS[start] if start else ''};
              S.hovering.push({{ item: Object.assign({{id: 5000 + Math.floor(Math.random()*1e6)}}, {ITEMS[item]}), x: {src['x']}, y: {src['y']}, age: 0 }});
              return [S.events.length, window.__pf.soundLog.length]; }})()"""
            n_ev, n_snd = g.ev(setup)
            g.drag(src, target[station])
            st = g.ev(f"""(() => {{ const S = window.__pf.S, k = {key_js};
              return {{ slot: k({SLOT[station]}), hover: S.hovering.map(h => k(h.item)), falling: S.falling.map(f => k(f.item)),
                       ev: S.events.slice({n_ev}), snd: window.__pf.soundLog.slice({n_snd}).map(s => s.id), shake: S.shake && S.shake.station }}; }})()""")
            want_ok = item in accepted
            ev_names = [e['e'] for e in st['ev']]
            if want_ok:
                expect_slot = None if station == 'trash' else COMBO.get((start, item), item)
                ok = st['hover'] == [] and 'wrong_placement' not in ev_names and st['slot'] == expect_slot
                if station == 'trash':
                    ok = ok and 'item_thrown_away' in ev_names
                if start and station in ('grill', 'storage'):
                    ok = ok and st['falling'] == [start]       # the replaced item pops off
            else:
                refusals += 1
                wp = [e for e in st['ev'] if e['e'] == 'wrong_placement']
                logged_item = item.replace(':', '(') + ')' if item.startswith('flatbread') else item  # describe() format
                ok = st['hover'] == [item] and st['slot'] == start and len(wp) == 1 and wp[0]['item'] == logged_item \
                    and wp[0]['station'] == STATION_NAME[station] and wp[0]['level'] == '1-3' and 't' in wp[0] \
                    and 'sfx_wrong_place' in st['snd'] and st['shake'] == STATION_NAME[station]
            results.append((station, start or 'empty', item, 'accept' if want_ok else 'refuse', ok))
            check(f'{station} [{start or "empty"}] + {item} -> {"placed" if want_ok else "refused"}', ok, st if not ok else '')
    # the summary counts wrong placements
    g.tap(K['pause']); g.page.wait_for_timeout(150); g.page.tap('#stopBtn'); g.page.wait_for_selector('#summary:not(.hidden)')
    rec = g.ev('window.__pf.S.record')
    check('summary counts every wrong placement', rec['wrongPlacements'] == refusals and 'Wrong placements' in g.page.inner_text('#summary .cols'), (rec['wrongPlacements'], refusals))
    check('no penalty for wrong placements', rec['score'] == 0 and rec['customersLost'] == 0)
    b.close()
check('no console errors', not errors, errors[:5])
acc = sum(1 for r in results if r[3] == 'accept')
print(f'{len(results)} combinations: {acc} accepted, {len(results) - acc} refused')
sys.exit(check.report())
