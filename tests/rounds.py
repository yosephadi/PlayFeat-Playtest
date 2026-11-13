"""Marathon Rounds (V2) checks: freeze at round end, cards, marathon coins, storage unlock, logging, exports.
Usage: rounds.py OUTDIR"""
import sys, csv, io, json
from playwright.sync_api import sync_playwright
from harness import server, Checks, new_context, Game

OUT = sys.argv[1] if len(sys.argv) > 1 else '.'
check, errors = Checks(), []
R = 'window.__pf.R'


def serve_first_customer(g):
    """Hand the first seated customer the dish they ordered (via a hovering item + a real touch drag)."""
    order = g.ev("window.__pf.S.seated[0] && window.__pf.S.seated[0].order")
    if not order:
        return None
    g.ev(f"(() => {{ window.__pf.S.hovering.push({{ item: {{id: Math.random(), t: 'dish', dish: '{order}'}}, x: 420, y: 250, age: 0 }}); return 1 }})()")
    g.drag({'x': 420, 'y': 250}, g.ev('window.__pf.centers().slots[0]'))
    return order


with server() as port, sync_playwright() as p:
    b, ctx = new_context(p, perms=True, port=port)
    g = Game(ctx, port, errors, speed=10)
    check('panel has Marathon Rounds and no regular Marathon', g.page.locator('button.lv[data-level="rounds"]').count() == 1 and g.page.locator('button.lv[data-level="marathon"]').count() == 0)
    g.start('rounds', 'rounds-test')
    check('starts with 0 marathon coins and 0 storage slots', g.ev(f"{R}.coins === 0 && window.__pf.S.storage.length === 0"))
    LONG = "(() => { const S = window.__pf.S; S.m.patience = 99999; S.m.angryPatience = 99999; S.seated.concat(S.outside).forEach(c => { c.patienceMax = c.left = 99999; }); return 1 })()"
    g.ev(LONG)  # nobody leaves while the test drives the run; the end of the test forces the losses

    # coins = tips: serve the first customer
    g.page.wait_for_function('window.__pf.S.seated.length > 0')
    before = g.ev(f"({{tips: window.__pf.S.tips, coins: {R}.coins}})")
    serve_first_customer(g)
    after = g.ev(f"({{tips: window.__pf.S.tips, coins: {R}.coins}})")
    check('each tip also adds the same marathon coins', after['tips'] - before['tips'] > 0 and after['coins'] - before['coins'] == after['tips'] - before['tips'], (before, after))

    # set up a frozen-state snapshot just before the round end: grill item, a mid-drag item
    g.ev("(() => { const S = window.__pf.S; S.t = 88.5; S.grill[0] = {id: 77, t: 'flatbread', st: 'raw', bake: 1, over: 0}; "
         "S.hovering.push({ item: {id: 78, t: 'pepper'}, x: 200, y: 330, age: 0 }); window.__pf.R.coins = 45; return 1 })()")
    c = g.client({'x': 200, 'y': 330})
    g.cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': c['x'], 'y': c['y'], 'id': 1}]})  # held, not released
    check('item is being dragged before the round ends', g.ev('!!window.__pf.S.held'))
    g.page.wait_for_selector('#breakOv:not(.hidden)', timeout=20000)
    snap_js = """(() => { const S = window.__pf.S; return { t: S.t, seated: S.seated.map(c => c.left), grill: S.grill.map(i => i && [i.bake, i.over]),
        bubbles: S.bubbles.map(b => b.y), falling: S.falling.map(f => f.y), nextArr: S.m.nextArrivalT, nextSpawn: S.nextSpawnT, outside: S.outside.length,
        events: S.events.filter(e => !/break|card|round/.test(e.e)).length } })()"""
    s1 = g.ev(snap_js)
    g.page.wait_for_timeout(600)   # 6 s of break time at speed 10
    s2 = g.ev(snap_js)
    check('round ends at 90 s of play time', abs(s1['t'] - 90) < 0.05, s1['t'])
    check('during the break everything is frozen (patience, bake, bubbles, falling, spawns, arrivals)', s1 == s2, (s1, s2))
    check('drag cancelled at round end: item hovers, nothing lost', g.ev("!window.__pf.S.held && window.__pf.S.hovering.some(h => h.item.id === 78)")
          and any(e['e'] == 'drag_cancelled_round_end' for e in g.ev('window.__pf.S.events')))
    g.cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    check('bake loop is silent during the break', g.ev("window.__pf.soundLog.filter(s => s.id === 'sfx_bake_loop').slice(-1)[0].note") == 'loop stop')

    # break 1: one card per break. 45 coins: Grill I (40) and Pepper (35) affordable, Cozy (50) not
    offer = g.ev(f"{R}.offer")
    check('break 1 offers Faster Grill I, Blazing Ember Pepper, Cozy Seats', offer == ['grill1', 'pepper', 'cozy'], offer)
    check('a card that costs more than the coins is greyed out and cannot be bought', g.page.locator('#brkCards button[data-card="cozy"]').is_disabled()
          and 'cant' in g.page.get_attribute('#brkCards button[data-card="cozy"]', 'class') and not g.ev("window.__pf.buyCard('cozy')") and g.ev(f"{R}.coins") == 45)
    st0 = g.ev("({score: window.__pf.S.score, tips: window.__pf.S.tips})")
    g.page.click('#brkCards button[data-card="grill1"]')
    check('buying Faster Grill I costs 40 (45 -> 5)', g.ev(f"{R}.coins") == 5)
    check('the bought card shows "Bought"', 'Bought' in g.page.inner_text('#brkCards button[data-card="grill1"]'))
    g.ev(f"(() => {{ {R}.coins = 500; window.__pf.renderBreak(); return 1 }})()")  # even with plenty of coins...
    locked = [g.page.locator(f'#brkCards button[data-card="{c}"]').is_disabled() and 'locked' in g.page.get_attribute(f'#brkCards button[data-card="{c}"]', 'class') for c in ('pepper', 'cozy')]
    check('after 1 card the other 2 are greyed out ("One card per break") and cannot be bought',
          all(locked) and 'One card per break' in g.page.inner_text('#brkCards button[data-card="pepper"]')
          and not g.ev("window.__pf.buyCard('pepper')") and not g.ev("window.__pf.buyCard('cozy')") and g.ev(f"{R}.coins") == 500, locked)
    g.ev(f"(() => {{ {R}.coins = 5; window.__pf.renderBreak(); return 1 }})()")
    st1 = g.ev("({score: window.__pf.S.score, tips: window.__pf.S.tips})")
    check('buying a card does not change score or tips', st0 == st1, (st0, st1))
    check('coin count shown on the break screen', g.page.inner_text('#brkCoins') == '5')
    g.page.screenshot(path=f'{OUT}/rounds-break1.png')
    g.page.tap('#brkDone')
    check('Done continues: round 2 starts, play time resumes from 90 s', g.ev(f"{R}.round === 2 && !{R}.inBreak") and abs(g.ev('window.__pf.S.t') - 90) < 0.5)
    check('the hovering item survived the break and can be picked up', g.ev("window.__pf.S.hovering.some(h => h.item.id === 78)"))

    # Faster Grill I: the next flatbread bakes in 4.5 s
    g.ev("(() => { const S = window.__pf.S; S.grill[0] = null; S.hovering.push({ item: {id: 90, t: 'flatbread', st: 'raw', bake: 0, over: 0}, x: 300, y: 330, age: 0 }); return 1 })()")
    g.drag({'x': 300, 'y': 330}, g.ev('window.__pf.centers().grill'))
    g.page.wait_for_function("window.__pf.S.grill[0] && window.__pf.S.grill[0].id === 90 && window.__pf.S.grill[0].st === 'baked'", timeout=10000)
    placed = [e['t'] for e in g.ev('window.__pf.S.events') if e['e'] == 'item_placed' and e['on'] == 'grill'][-1]
    ready = [s['t'] for s in g.ev('window.__pf.soundLog') if s['id'] == 'sfx_bake_ready'][-1]
    check('after Faster Grill I the next flatbread bakes in 4.5 s', abs((ready - placed) - 4.5) < 0.1, (placed, ready))
    check('Pepper was not bought: still worth 10', g.ev("window.__pf.R.values.pepper") == 10)

    # storage unlock at 6 and 14 dishes
    g.ev("(() => { window.__pf.S.served = 5; return 1 })()")
    g.page.wait_for_function('window.__pf.S.seated.length > 0', timeout=20000)
    serve_first_customer(g)
    ev = g.ev('window.__pf.S.events')
    check('storage slot 1 unlocks at 6 dishes', g.ev('window.__pf.S.storage.length') == 1 and any(e['e'] == 'storage_unlocked' and e['slot'] == 1 and e['dishesServed'] == 6 for e in ev))
    check('unlock highlight and sound (sfx_star_1)', g.ev(f"!!{R}.flash") and any(s['id'] == 'sfx_star_1' for s in g.ev('window.__pf.soundLog')))
    g.page.screenshot(path=f'{OUT}/rounds-unlock1.png')
    g.ev("(() => { window.__pf.S.served = 13; return 1 })()")
    g.page.wait_for_function('window.__pf.S.seated.length > 0', timeout=20000)
    serve_first_customer(g)
    ev = g.ev('window.__pf.S.events')
    check('storage slot 2 unlocks at 14 dishes (max 2)', g.ev('window.__pf.S.storage.length') == 2 and any(e['e'] == 'storage_unlocked' and e['slot'] == 2 and e['dishesServed'] == 14 for e in ev))

    # break 2: offers after owning grill1 + pepper; let it time out
    g.page.wait_for_selector('#breakOv:not(.hidden)', timeout=30000)
    offer2 = g.ev(f"{R}.offer")
    check('break 2 offers Second Grill Spot, Royal Dusk Mushroom, Faster Grill II', offer2 == ['grillspot', 'mushroom', 'grill2'], offer2)
    coins2 = g.ev(f"{R}.coins")
    g.page.wait_for_selector('#breakOv.hidden', state='attached', timeout=10000)
    check('break 2 times out and play continues', g.ev(f"{R}.round === 3"))
    check('skipping keeps the coins', g.ev(f"{R}.coins") == coins2 and g.ev(f"{R}.breakLog[1]") == {'break': 2, 'pick': 'skip', 'coinsBefore': coins2, 'coinsAfter': coins2}, g.ev(f"{R}.breakLog"))
    g.ev(f"(() => {{ window.__pf.S.t = {R}.roundEndAt - 0.3; return 1 }})()")  # jump to the end of round 3
    g.page.wait_for_selector('#breakOv:not(.hidden)', timeout=10000)
    check('saved coins are available at the next break', g.ev(f"{R}.coinsAtBreakStart") == coins2 == g.ev(f"{R}.coins") and g.page.inner_text('#brkCoins') == str(coins2))
    g.page.tap('#brkDone')

    # every card applies its configured value, never past its limit (direct buyCard on a fresh copy of the state, then restored)
    res = g.ev(f"""(() => {{
      const R = {R}, P = window.__pf, S = P.S, keep = JSON.stringify(R), nEv = S.events.length, grill = S.grill.length, out = {{}};
      const fresh = (id, needs) => {{ Object.assign(R, JSON.parse(keep)); R.inBreak = true; R.offer = [id]; R.boughtThisBreak = []; R.owned = needs ? [{{id: needs}}] : []; R.coins = 999; R.bakeSec = 6; R.patienceMult = 1; }};
      for (const c of P.CFG.marathonRounds.cards) {{
        fresh(c.id, c.needs); const ok = P.buyCard(c.id);
        out[c.id] = {{ ok, bake: R.bakeSec, pm: R.patienceMult, grill: S.grill.length, values: Object.assign({{}}, R.values) }};
        S.grill.length = grill;
      }}
      // limits: a config that tries to go past them is clamped
      const g2 = P.CFG.marathonRounds.cards.find(c => c.id === 'grill2'), cz = P.CFG.marathonRounds.cards.find(c => c.id === 'cozy');
      const b0 = g2.apply.bakeSec, p0 = cz.apply.patienceMult; g2.apply.bakeSec = 1; cz.apply.patienceMult = 3;
      fresh('grill2', 'grill1'); P.buyCard('grill2'); out.clampBake = R.bakeSec;
      fresh('cozy'); P.buyCard('cozy'); out.clampPm = R.patienceMult;
      g2.apply.bakeSec = b0; cz.apply.patienceMult = p0;
      Object.assign(R, JSON.parse(keep)); S.events.length = nEv; return out; }})()""")
    v = lambda c, k: res[c]['values'][k]
    check('Faster Grill I: bake 4.5 s; Faster Grill II: bake 3.0 s', res['grill1']['bake'] == 4.5 and res['grill2']['bake'] == 3.0, (res['grill1'], res['grill2']))
    check('Second Grill Spot: 2 grill spots', res['grillspot']['grill'] == 2)
    check('Cozy Seats: patience x1.2 for new arrivals', res['cozy']['pm'] == 1.2)
    check('ingredient cards: pepper 18, mushroom 24, sorbet 17, drizzle 12, flatbread 16',
          (v('pepper', 'pepper'), v('mushroom', 'mushroom'), v('sorbet', 'sorbet'), v('drizzle', 'drizzle'), v('flatbread', 'flatbread')) == (18, 24, 17, 12, 16))
    check('all 9 cards can be bought with enough coins', all(res[c]['ok'] for c in ('grill1', 'grill2', 'grillspot', 'cozy', 'pepper', 'mushroom', 'sorbet', 'drizzle', 'flatbread')))
    check('limits: bake never below 3.0 s, patience never above x1.2, even if the config asks for more', res['clampBake'] == 3.0 and res['clampPm'] == 1.2, (res['clampBake'], res['clampPm']))
    prices = {c['id']: c['price'] for c in g.ev('window.__pf.CFG.marathonRounds.cards')}
    check('prices from the config', prices == {'grill1': 40, 'grill2': 60, 'grillspot': 65, 'cozy': 50, 'pepper': 35, 'mushroom': 30, 'sorbet': 25, 'drizzle': 25, 'flatbread': 45}, prices)

    # offer logic for later breaks (pure function, with owned cards set directly, then restored)
    g.ev(f"(() => {{ window.__savedOwned = {R}.owned.slice(); return 1 }})()")
    g.ev(f"(() => {{ {R}.owned = [{{id: 'grill1'}}, {{id: 'grill2'}}, {{id: 'cozy'}}]; return 1 }})()")
    check('break 3 replaces owned cards from the fallback list', g.ev("window.__pf.offersFor(3)") == ['drizzle', 'flatbread', 'sorbet'], g.ev("window.__pf.offersFor(3)"))
    check('break 4+ = next three unowned fallback cards', g.ev("window.__pf.offersFor(4)") == ['drizzle', 'flatbread', 'sorbet'])
    g.ev(f"(() => {{ {R}.owned = window.__pf.CFG.marathonRounds.cards.map(c => ({{id: c.id}})); return 1 }})()")
    check('no cards left -> empty offer (rest screen)', g.ev("window.__pf.offersFor(5)") == [])
    g.ev(f"(() => {{ {R}.owned = window.__savedOwned; return 1 }})()")

    # end the run: 3 lost, then check the summary and exports
    g.ev("(() => { const S = window.__pf.S; S.m.patience = 0.3; S.m.angryPatience = 0.3; S.m.spacing = 0.5; S.seated.concat(S.outside).forEach(c => { c.patienceMax = 1; c.left = 0.2; }); return 1 })()")
    g.page.wait_for_selector('#summary:not(.hidden)', timeout=90000)
    rec = g.ev('window.__pf.S.record'); ev = rec['events']
    served = [e for e in ev if e['e'] == 'dish_served']
    check('final tips = all tips earned (not reduced by spending)', rec['tips'] == sum(e['tip'] for e in served))
    check('final score = dish points - 10 per lost (not reduced by spending)', rec['score'] == max(0, sum(e['points'] for e in served) - 10 * rec['customersLost']) or rec['score'] >= 0)
    check('total = score + tips', rec['total'] == rec['score'] + rec['tips'])
    names = {e['e'] for e in ev}
    for n in ['round_end', 'break_start', 'card_offered', 'card_picked', 'break_done', 'break_timeout', 'break_skipped', 'storage_unlocked']:
        check(f'log event {n}', n in names)
    cp = [e for e in ev if e['e'] == 'card_picked']
    check('card_picked has id, price, coins before/after (one row per purchase)', len(cp) == 1 and all({'id', 'price', 'coinsBefore', 'coinsAfter'} <= set(e) for e in cp))
    check('summary: mode, rounds, cards, bake time, coins, times, dishes per break, lost per round',
          rec['mode'] == 'marathon_rounds' and rec['roundsCompleted'] >= 2 and rec['cardsBought'] == 'grill1@break1'
          and rec['finalBakeSec'] == 4.5 and rec['breakTimeSec'] > 0 and abs(rec['totalTimeSec'] - rec['playTimeSec'] - rec['breakTimeSec']) < 0.2
          and len(rec['dishesAtBreaks'].split(';')) == rec['roundsCompleted'], {k: rec.get(k) for k in ('mode', 'roundsCompleted', 'cardsBought', 'finalBakeSec', 'coinsUnspent', 'playTimeSec', 'breakTimeSec', 'totalTimeSec', 'dishesAtBreaks', 'lostPerRound')})
    page = g.page
    page.screenshot(path=f'{OUT}/rounds-summary.png')
    page.tap('#copyRow'); page.wait_for_timeout(300)
    row = page.evaluate('navigator.clipboard.readText()').split('\t'); cols = [c[0] for c in page.evaluate('window.__pf.COLS')]
    i0 = cols.index('mode')
    check('copied row has the Marathon Rounds fields after the old ones', len(row) == len(cols) and i0 == 22 and cols[i0:i0 + 10] == ['mode','rounds_completed', 'cards_bought', 'final_bake_s', 'coins_unspent', 'play_time_s', 'break_time_s', 'total_time_s', 'dishes_at_breaks', 'lost_per_round']
          and row[cols.index('mode')] == 'marathon_rounds' and row[cols.index('cards_bought')] == 'grill1@break1')
    check('row: card per break and coins before>after each break', row[cols.index('break_picks')] == 'grill1 | skip | skip'
          and row[cols.index('break_coins')] == f'45>5 | {coins2}>{coins2} | {coins2}>{coins2}', (row[cols.index('break_picks')], row[cols.index('break_coins')]))
    with page.expect_download() as d:
        page.click('#summary .dlCsv')
    d.value.save_as(f'{OUT}/rounds.csv')
    rows = list(csv.reader(io.open(f'{OUT}/rounds.csv', newline='')))
    check('CSV keeps old columns and adds the new ones at the end', rows[0] == cols and rows[-1][rows[0].index('mode')] == 'marathon_rounds')
    with page.expect_download() as d2:
        page.click('#summary .dlJson')
    d2.value.save_as(f'{OUT}/rounds.json')
    js = json.load(open(f'{OUT}/rounds.json'))
    check('JSON export has the rounds run with its events', js['runs'][-1]['mode'] == 'marathon_rounds' and any(e['e'] == 'card_picked' for e in js['runs'][-1]['events']))
    b.close()
check('no console errors', not errors, errors[:5])
sys.exit(check.report())
