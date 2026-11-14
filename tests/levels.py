"""Planet 1 with 6 levels and no trash bin: level values, burn multiplier, storage per level, angry by count,
new log columns, and Marathon Rounds unchanged. Usage: levels.py"""
import time
from playwright.sync_api import sync_playwright
from harness import server, Checks, new_context, Game, finish

check, errors = Checks(), []
LEVELS = {  # spots, first order, pool, patience, angryAt, gravity, life, every, useful, storage, burn x, stars
    '1-1': (1, 'pepper', {'pepper': 1}, 45, [], 0.4, 6, 3, 0.8, 0, 2, [20, 40, 60]),
    '1-2': (1, 'pepper', {'pepper': 1}, 45, [], 0.4, 6, 3, 0.8, 0, 1, [20, 40, 60]),
    '1-3': (2, 'pepper', {'pepper': 1, 'mushroom': 1}, 40, [], 0.5, 5, 2.5, 0.65, 0, 1, [20, 45, 65]),
    '1-4': (2, 'pepper', {'pepper': 1, 'mushroom': 1}, 40, [], 0.5, 5, 2.5, 0.65, 2, 1, [20, 45, 65]),
    '1-5': (2, 'sorbet', {'pepper': 1, 'mushroom': 1, 'sorbet': 1}, 40, [], 0.6, 4, 2, 0.6, 2, 1, [35, 60, 75]),
    '1-6': (3, 'pepper', {'pepper': 1, 'mushroom': 1, 'sorbet': 1}, 35, [4, 7], 0.6, 4, 2, 0.6, 2, 1, [50, 85, 105]),
}
SRC = {'x': 200, 'y': 330}  # open air: an item is put hovering here and dragged from here


def hover(g, item_js):
    """Put an item hovering at SRC; returns the event count before."""
    return g.ev(f"""(() => {{ const S = window.__pf.S; S.hovering.length = 0; S.falling.length = 0; S.bubbles.length = 0;
      S.hovering.push({{ item: Object.assign({{id: 7000 + Math.floor(Math.random()*1e6)}}, {item_js}), x: {SRC['x']}, y: {SRC['y']}, age: 0 }});
      return S.events.length; }})()""")


def wait_end(g, timeout=60):
    g.page.wait_for_selector('#summary:not(.hidden)', timeout=timeout * 1000)
    return g.ev('window.__pf.S.record')


def burn_times(g, timeout=20):
    """Put a raw flatbread on the grill; returns (ready - put, glow - put, burnt - put) in game seconds."""
    t0 = g.ev("(() => { const S = window.__pf.S; S.grill[0] = {id: 4242, t: 'flatbread', st: 'raw', bake: 0}; return S.t })()")
    g.page.wait_for_function("window.__pf.S.events.some(e => e.e === 'flatbread_burnt')", timeout=timeout * 1000)
    ev = g.ev('window.__pf.S.events')
    glow = next(e['t'] for e in ev if e['e'] == 'flatbread_glowing')
    burnt = next(e['t'] for e in ev if e['e'] == 'flatbread_burnt')
    return t0, glow - t0, burnt - t0


with server() as port, sync_playwright() as p:
    b, ctx = new_context(p, port=port)

    # --- trash bin gone; level select lists the 6 levels + Marathon Rounds
    g = Game(ctx, port, errors)
    gone = g.ev("""(() => { const pf = window.__pf; return { placement: 'trash' in pf.CFG.placement, sound: 'sfx_trash' in pf.SOUND_CONFIG,
      poly: 'trashPoly' in pf.L, centers: 'trash' in pf.centers() }; })()""")
    check('no trash bin: no placement rule, no sfx_trash, no trash area, no test-hook position', not any(gone.values()), gone)
    btns = g.page.eval_on_selector_all('#levelBtns button.lv', 'bs => bs.map(b => [b.dataset.level, b.textContent])')
    check('panel lists 1-1 ... 1-6 and Marathon Rounds', [x[0] for x in btns] == ['1-1', '1-2', '1-3', '1-4', '1-5', '1-6', 'rounds'], btns)
    check('level names', [x[1] for x in btns[:6]] == ['1-1 First Sale', '1-2 Hot Grill', '1-3 Two Toppings', '1-4 Prep Ahead',
                                                      '1-5 Something Sweet', '1-6 The Angry Alien'], btns)
    g.page.close()

    # --- every level loads with its values
    for lv, (spots, first, pool, pat, angry, grav, life, every, useful, slots, burn, stars) in LEVELS.items():
        g = Game(ctx, port, errors, speed=1); g.start(lv)
        st = g.ev("""(() => { const S = window.__pf.S, rf = S.lv.refill, a = S.events.find(e => e.e === 'customer_arrived');
          return { flow: S.customerFlow, spots: S.refill.spots.length, delay: rf.refillDelaySec, first: S.orderSequence[0], pool: rf.orderPool,
                   pat: rf.patienceSec, firstPat: a && a.patience, angry: rf.angryAt, angryPat: rf.angryPatienceSec, grav: S.lv.gravity,
                   life: S.lv.bubbleLifeSec, every: S.lv.bubbleEverySec, useful: S.lv.usefulBubbleShare, storage: S.storage.length,
                   burn: S.lv.burnTimeMultiplier, stars: S.lv.stars }; })()""")
        want = {'flow': 'refill', 'spots': spots, 'delay': 2, 'first': first, 'pool': pool, 'pat': pat, 'firstPat': pat, 'angry': angry,
                'angryPat': 25, 'grav': grav, 'life': life, 'every': every, 'useful': useful, 'storage': slots, 'burn': burn, 'stars': stars}
        bad = {k: (st[k], v) for k, v in want.items() if st[k] != v}
        check(f'{lv} loads with its values (spots, first order, pool, patience, angryAt, gravity, bubbles, storage, burn, stars)', not bad, bad)
        if lv == '1-5':
            starters = g.ev('window.__pf.S.lv.starterBubbles.map(s => s.ing)')
            check('1-5 starter bubbles are sorbet + drizzle', starters == ['sorbet', 'drizzle'], starters)
        g.page.close()

    # --- releasing an item where the trash was, or in open air: it falls and vanishes
    g = Game(ctx, port, errors, speed=1); g.start('1-6')
    for name, at in (('on the old trash spot', {'x': 60, 'y': 690}), ('in open air', {'x': 200, 'y': 330})):
        n = hover(g, "{t: 'pepper'}")
        g.drag(SRC, at)
        g.page.wait_for_function(f"window.__pf.S.events.slice({n}).some(e => e.e === 'item_dropped_vanished')", timeout=8000)
        ev = [e['e'] for e in g.ev(f'window.__pf.S.events.slice({n})')]
        check(f'release {name}: the item falls and vanishes (no trash event)',
              'item_released_in_air' in ev and 'item_dropped_vanished' in ev and 'item_thrown_away' not in ev, ev)
    g.page.close()

    # --- storage: none on 1-1..1-3 (hidden, can't be used), 2 slots on 1-4
    for lv in ('1-1', '1-2', '1-3', '1-4'):
        g = Game(ctx, port, errors, speed=1); g.start(lv)
        K = g.ev('window.__pf.centers()')
        n = hover(g, "{t: 'pepper'}")
        g.drag(SRC, K['storage'][0])
        st = g.ev(f"""(() => {{ const S = window.__pf.S, ev = S.events.slice({n}).map(e => e.e);
          return {{ len: S.storage.length, stored: ev.includes('item_stored'), air: ev.includes('item_released_in_air'), slot0: S.storage[0] ? S.storage[0].t : null }}; }})()""")
        if lv == '1-4':
            check('1-4: dropping on the storage table stores the item', st['len'] == 2 and st['stored'] and st['slot0'] == 'pepper', st)
        else:
            check(f'{lv}: no storage table; dropping there makes the item fall', st['len'] == 0 and not st['stored'] and st['air'], st)
        g.page.close()

    # --- burn: 1-1 at twice the normal time, 1-2 normal; 1-1 also logs the first serve time
    C = None
    for lv, mult in (('1-1', 2), ('1-2', 1)):
        g = Game(ctx, port, errors, speed=10); g.start(lv)
        C = C or g.ev('window.__pf.CFG.common')
        if lv == '1-1':  # serve the first customer a ready dish from the plate
            K = g.ev('window.__pf.centers()')
            g.page.wait_for_function('window.__pf.S.seated.length > 0 && window.__pf.S.seated[0].seatedT != null')
            g.ev("(() => { window.__pf.S.plates[0] = {id: 9100, t: 'dish', dish: 'pepper'}; return 1 })()")
            g.drag(K['plate'], K['slots'][0])
        t0, glow, burnt = burn_times(g)
        want_glow, want_burn = C['bakeSec'] + C['glowAfterDoneSec'] * mult, C['bakeSec'] + C['burnAfterDoneSec'] * mult
        check(f'{lv}: flatbread glows at {want_glow} s and burns at {want_burn} s after going on the grill (x{mult})',
              abs(glow - want_glow) < 0.15 and abs(burnt - want_burn) < 0.15, (glow, burnt))
        rec = wait_end(g)
        served = [e for e in rec['events'] if e['e'] == 'dish_served']
        if lv == '1-1':
            check('1-1 row: first_serve_s = time of the first dish served', served and rec['firstServeSec'] == round(served[0]['t'], 1) and rec['levelId'] == '1-1',
                  (rec['firstServeSec'], served[:1]))
        else:
            check('1-2 row: burnt_flatbreads = 1 after a forced burn', rec['burntFlatbreads'] == 1, rec['burntFlatbreads'])
            check('1-2 row: first_serve_s blank when nothing was served', rec['firstServeSec'] is None and not served)
        g.page.close()

    # --- 1-6: angry aliens are customers 4 and 7 (idle day)
    g = Game(ctx, port, errors, speed=12); g.start('1-6')
    rec = wait_end(g)
    ups = [e for e in rec['events'] if e['e'] == 'customer_stepped_up']
    check('1-6: customers 4 and 7 are angry and order sorbet', len(ups) >= 7 and [u['n'] for u in ups if u['type'] == 'angry'] == [4, 7]
          and all(u['order'] == 'sorbet' for u in ups if u['type'] == 'angry'), [(u['n'], u['type'], u['order']) for u in ups])

    # --- 1-4 Prep Ahead: a flatbread goes through storage, becomes a dish and is served -> logged
    g = Game(ctx, port, errors, speed=3); g.start('1-4')
    K = g.ev('window.__pf.centers()')
    g.page.wait_for_function('window.__pf.S.seated.length > 0 && window.__pf.S.seated[0].seatedT != null')
    hover(g, "{t: 'flatbread', st: 'baked', bake: 6, over: 0}")
    g.drag(SRC, K['storage'][0])                       # store the baked flatbread
    g.drag(K['storage'][0], K['plate'])                # storage -> plate
    hover(g, "{t: 'pepper'}")
    g.drag(SRC, K['plate'])                            # pepper on top -> Pepper Flatbread
    g.drag(K['plate'], K['slots'][0])                  # serve the first customer (pepper)
    rec = wait_end(g)
    served = [e for e in rec['events'] if e['e'] == 'dish_served']
    check('1-4 row: items_stored and dishes_from_storage count the stored flatbread', rec['itemsStored'] == 1 and rec['dishesFromStorage'] == 1 and len(served) == 1,
          (rec['itemsStored'], rec['dishesFromStorage'], len(served)))
    cols = g.ev('window.__pf.COLS.map(c => c[0])')
    row = g.ev('window.__pf.tsvRow(window.__pf.S.record)').split('\t')
    check('row: new columns at the end (level_id, items_stored, dishes_from_storage, first_serve_s)',
          cols[-4:] == ['level_id', 'items_stored', 'dishes_from_storage', 'first_serve_s'] and row[-4:] == ['1-4', '1', '1', str(rec['firstServeSec'])], (cols[-4:], row[-4:]))
    check('row: items_thrown_away column kept, blank', 'items_thrown_away' in cols and row[cols.index('items_thrown_away')] == '')
    g.page.close()

    # --- Marathon Rounds unaffected: no multiplier, storage locked until 6 / 14 dishes, normal burn
    g = Game(ctx, port, errors, speed=10); g.start('rounds')
    st = g.ev("""(() => { const S = window.__pf.S, CFG = window.__pf.CFG;
      return { burn: S.lv.burnTimeMultiplier ?? null, storage: S.storage.length, unlock: CFG.marathonRounds.storageUnlockAt, rounds: !!S.rounds, flow: S.customerFlow }; })()""")
    check('Marathon Rounds: no burn multiplier, no storage at start, unlocks at 6 and 14', st == {'burn': None, 'storage': 0, 'unlock': [6, 14], 'rounds': True, 'flow': None}, st)
    t0, glow, burnt = burn_times(g)
    check('Marathon Rounds: flatbread burns at the normal time', abs(burnt - (C['bakeSec'] + C['burnAfterDoneSec'])) < 0.15, burnt)
    g.page.close()

    finish(check, b, errors, ignore=('Bubbles drift faster',))
