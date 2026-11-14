"""Marathon Rounds bubble supply: 70% needed, 3 s guarantee, interval follows demand within limits, on-screen cap,
logging; customer arrivals and the patience/spacing ramp unchanged; story-day bubbles unchanged.
Usage: bubbles.py"""
from playwright.sync_api import sync_playwright
from harness import server, Checks, new_context, Game, finish

check, errors = Checks(), []
P = 'window.__pf'

with server() as port, sync_playwright() as p:
    b, ctx = new_context(p, port=port)
    BC = None

    # ---------- direct checks on a paused run (deterministic set-ups) ----------
    g = Game(ctx, port, errors, speed=1); g.start('rounds', 'bubble-test')
    BC = g.ev(f'{P}.CFG.marathonRounds.bubbles')
    check('bubble settings in config', BC['usefulBubbleShare'] == 0.7 and BC['minBubbleIntervalSec'] == 0.8 and BC['maxBubbleIntervalSec'] == 2
          and BC['guaranteeSec'] == 3 and BC['maxBubblesOnScreen'] == 8 and BC['supplyMargin'] == 1.3, BC)
    SETUP = f"""([orders, left]) => {{ const S = {P}.S; S.paused = true; S.bubbles.length = 0; S.held = null; S.falling.length = 0; S.hovering.length = 0;
        S.grill.fill(null); S.plates.fill(null); S.bowl = null; S.storage.fill(null); S.served = 10;  // stage 2: all five ingredients
        S.seated = orders.map((o, i) => ({{ id: 9000 + i, type: 'regular', order: o, patienceMax: 99, left: left, seatedT: S.t - 1, arrivalT: S.t - 1 }}));
        return 1 }}"""
    g.ev(SETUP, [['pepper', 'sorbet'], 30])
    check('neededList: oldest order first, minus the kitchen', g.ev(f"{P}.neededList().map(n => n.k)") == ['flatbread', 'pepper', 'sorbet', 'drizzle'])
    g.ev(f"(() => {{ {P}.S.plates[0] = {{id: 1, t: 'flatbread', st: 'baked', bake: 6, over: 0}}; return 1 }})()")
    check('a flatbread on the plate is no longer needed', g.ev(f"{P}.neededList().map(n => n.k)") == ['pepper', 'sorbet', 'drizzle'])

    # share: 600 spawns with something needed and no guarantee due -> ~70% picked from the needed list
    res = g.ev(f"""(() => {{ const S = {P}.S, out = {{useful: 0, random: 0, guaranteed: 0, ings: {{}}}};
        for (let i = 0; i < 600; i++) {{
          S.bubbles.length = 0; S.needSince = {{}}; for (const k of ['flatbread','pepper','mushroom','sorbet','drizzle']) S.lastSeen[k] = S.t;
          {P}.spawnRoundsBubble(); const e = S.events[S.events.length - 1]; out[e.kind]++; out.ings[e.ing] = (out.ings[e.ing] || 0) + 1;
        }} return out; }})()""")
    share = res['useful'] / 600
    check('about 70% of bubbles carry a needed ingredient from the list (600 spawns, 0.64-0.76)', 0.64 <= share <= 0.76 and res['guaranteed'] == 0, (share, res))
    check('the needed bubble is the oldest needed ingredient without a bubble on screen (pepper here)', res['ings'].get('pepper', 0) >= res['useful'], res['ings'])
    check('the other 30% are random from the stage ingredients', set(res['ings']) <= {'flatbread', 'pepper', 'mushroom', 'sorbet', 'drizzle'} and len(res['ings']) >= 4, res['ings'])

    # nothing needed -> random
    g.ev(SETUP, [[], 30])
    res = g.ev(f"""(() => {{ const S = {P}.S, k = {{}}; for (let i = 0; i < 100; i++) {{ S.bubbles.length = 0; {P}.spawnRoundsBubble();
        const e = S.events[S.events.length - 1]; k[e.kind] = (k[e.kind] || 0) + 1; }} return k; }})()""")
    check('empty neededList -> all bubbles random', res == {'random': 100}, res)

    # guarantee: needed for 3 s without a bubble -> next bubble is that ingredient
    g.ev(SETUP, [['mushroom'], 30])
    G = f"""(age) => {{ const S = {P}.S; S.bubbles.length = 0; for (const k of ['flatbread','pepper','mushroom','sorbet','drizzle']) S.lastSeen[k] = S.t - 20;
        S.needSince = {{ flatbread: S.t, mushroom: S.t - age }}; {P}.spawnRoundsBubble(); const e = S.events[S.events.length - 1]; return [e.kind, e.ing]; }}"""
    got = [tuple(g.ev(G, 3.05)) for _ in range(20)]
    check('a needed ingredient missing for 3 s is the next bubble (every time)', all(x == ('guaranteed', 'mushroom') for x in got), got[:3])
    got = [tuple(g.ev(G, 2.5)) for _ in range(40)]
    check('not yet 3 s -> no forced bubble', not any(k == 'guaranteed' for k, _ in got), got[:5])

    # interval follows demand, within [min, max]
    IV = f"""([orders, left, spacing]) => {{ const S = {P}.S; S.m.spacing = spacing; S.seated.forEach(c => c.left = left); return {P}.roundsBubbleInterval({P}.neededList()); }}"""
    g.ev(SETUP, [[], 40]); calm = g.ev(IV, [[], 40, 15])
    three = ['pepper', 'mushroom', 'sorbet']  # 6 ingredients needed
    steps = []
    for left in (30, 20, 10, 0.6):            # less patience left = more ingredients needed per second
        g.ev(SETUP, [three, left]); steps.append(g.ev(IV, [three, left, 15]))
    low, high, extreme = steps[1], steps[2], steps[3]
    g.ev(SETUP, [[], 40]); fast_arrivals = g.ev(IV, [[], 40, 3])
    check('no demand -> max interval (2 s, the old interval)', calm == 2, calm)
    check('interval gets shorter as demand rises (6 needed, patience left 30 / 20 / 10 / 0.6 s)', steps[0] >= steps[1] > steps[2] > steps[3], steps)
    check('interval never below 0.8 s', extreme == 0.8 and all(0.8 <= x <= 2 for x in (calm, low, high, extreme, fast_arrivals)), (calm, low, high, extreme, fast_arrivals))
    check('arrival rate alone (3 s between customers) -> ~0.81 s', abs(fast_arrivals - 0.7 / (1.3 * 2 / 3)) < 0.01, fast_arrivals)

    # cap: with the cap set to 3, a 4th bubble waits
    g.ev(SETUP, [['pepper'], 30])
    r = g.ev(f"""(() => {{ const S = {P}.S, B = {P}.CFG.marathonRounds.bubbles, cap0 = B.maxBubblesOnScreen; B.maxBubblesOnScreen = 3;
        const ok = []; for (let i = 0; i < 6; i++) ok.push({P}.spawnRoundsBubble()); const n = S.bubbles.length; B.maxBubblesOnScreen = cap0; return [ok, n]; }})()""")
    check('bubbles on screen never exceed the cap (cap 3: spawns 4-6 wait)', r == [[True, True, True, False, False, False], 3], r)
    g.page.close()

    # ---------- a bot-played run ----------
    g = Game(ctx, port, errors, speed=4)
    g.start('rounds', 'bot-bubbles')
    g.ev(f"(() => {{ window.__maxB = 0; setInterval(() => {{ const S = {P}.S; if (S) window.__maxB = Math.max(window.__maxB, S.bubbles.length); }}, 16); return 1 }})()")
    g.bot_play(timeout=420)
    g.page.wait_for_selector('#summary:not(.hidden)', timeout=20000)
    rec = g.ev(f'{P}.S.record'); ev = rec['events']
    bub = [e for e in ev if e['e'] == 'bubble_spawned' and 'interval' in e]
    nd = [e for e in bub if e['needed'] > 0]
    from_list = sum(e['kind'] != 'random' for e in nd) / len(nd)
    check('bot run: >= 70% of bubbles (while something is needed) come from the needed list', from_list >= 0.7, round(from_list, 2))
    check('bot run: intervals always within 0.8-2 s', all(0.8 <= e['interval'] <= 2 for e in bub), (min(e['interval'] for e in bub), max(e['interval'] for e in bub)))
    check('bot run: interval drops below 2 s as customers speed up', min(e['interval'] for e in bub) < 1.6, min(e['interval'] for e in bub))
    check('bot run: never more than 8 bubbles on screen', 0 < g.ev('window.__maxB') <= 8, g.ev('window.__maxB'))

    # customer arrivals and the ramp are unchanged: patience and spacing follow 45*0.97^n / 15*0.95^n with floors
    M = g.ev(f'{P}.CFG.marathon')
    served_t = [e['t'] for e in ev if e['e'] == 'dish_served']
    arr = [e for e in ev if e['e'] == 'customer_arrived']
    bad = []
    for a in arr:
        n = sum(1 for t in served_t if t <= a['t'] - 1e-9)
        exp = max(M['patienceFloor'], (M['angryPatienceStart'] if a['type'] == 'angry' else M['patienceStart']) * M['patienceMult'] ** n)
        if abs(a['patience'] - exp) > 0.02: bad.append((a['t'], n, a['patience'], round(exp, 2)))
    check('ramp unchanged: every arrival has patience = start x 0.97^dishes (floor 12)', not bad and len(arr) > 10, bad[:3])
    gaps = []
    for a, b2 in zip(arr, arr[1:]):
        n = sum(1 for t in served_t if t <= a['t'] + 1e-9)
        exp = max(M['spacingFloor'], M['spacingStart'] * M['spacingMult'] ** n)
        if abs((b2['t'] - a['t']) - exp) > 0.05: gaps.append((a['t'], round(b2['t'] - a['t'], 2), round(exp, 2)))
    check('ramp unchanged: time between customers = 15 x 0.95^dishes (floor 3)', not gaps, gaps[:3])
    seat = {e['cid']: e['t'] for e in ev if e['e'] == 'customer_seated'}
    check('counter spots unchanged: 2, then 3 from 8 dishes', max(sum(1 for c, t in seat.items() if t <= x) - sum(1 for e in ev if e['e'] in ('dish_served', 'customer_lost') and e['t'] <= x) for x in seat.values()) <= 3)
    check('the run still ends after 3 lost', rec['ended'] == 'lost 3' and rec['customersLost'] == 3)

    # logging
    srv = [e for e in ev if e['e'] == 'dish_served']
    check('each dish logs its ingredient wait', srv and all(isinstance(e.get('ingredientWaitSec'), (int, float)) and e['ingredientWaitSec'] >= 0 for e in srv))
    check('row: ingredient waits per dish, avg, max', len(rec['ingredientWaitPerDish'].split('; ')) == rec['dishesServed'] and rec['ingredientWaitAvgSec'] is not None
          and rec['ingredientWaitMaxSec'] >= rec['ingredientWaitAvgSec'], {k: rec[k] for k in ('ingredientWaitAvgSec', 'ingredientWaitMaxSec')})
    check('row: lost while waiting for an ingredient = lost events flagged', rec['lostWaitingIngredient'] == sum(1 for e in ev if e['e'] == 'customer_lost' and e.get('waitingForIngredient')))
    check('row: bubbles spawned, useful share, missed', rec['bubblesSpawned'] == sum(1 for e in ev if e['e'] == 'bubble_spawned')
          and abs(rec['usefulBubbleShare'] - sum(e['useful'] for e in ev if e['e'] == 'bubble_spawned') / rec['bubblesSpawned']) < 0.01
          and rec['bubblesMissed'] == sum(1 for e in ev if e['e'] == 'bubble_missed'))
    names = [c[0] for c in g.ev(f'{P}.COLS')]
    check('export columns in place (followed only by the Planet 1 columns)', names[-4:] == ['level_id', 'items_stored', 'dishes_from_storage', 'first_serve_s'] and names[-10:-4] == ['ingredient_wait_per_dish', 'ingredient_wait_avg_s', 'ingredient_wait_max_s', 'lost_waiting_ingredient', 'bubbles_spawned', 'useful_bubble_share'])
    print('bot run', {k: rec[k] for k in ('dishesServed', 'runTimeSec', 'ingredientWaitAvgSec', 'ingredientWaitMaxSec', 'lostWaitingIngredient', 'bubblesSpawned', 'usefulBubbleShare', 'bubblesMissed')},
          'from list', round(from_list, 2), 'min interval', min(e['interval'] for e in bub))
    g.page.close()

    # story days keep the old bubble rule (fixed interval, no demand fields)
    g = Game(ctx, port, errors, speed=8); g.start('1-6')
    g.page.wait_for_function(f'{P}.S.t > 30', timeout=20000)
    ev = g.ev(f'{P}.S.events')
    sb = [e for e in ev if e['e'] == 'bubble_spawned']
    check('story days: bubbles unchanged (no demand interval, old kinds)', sb and not any('interval' in e for e in sb) and {e['kind'] for e in sb} <= {'starter', 'random', 'useful', 'forced-useful'})
    g.page.close()
    finish(check, b, errors)
