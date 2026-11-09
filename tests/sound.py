"""Checks that every sound ID fires at the right game event (via the [sfx] debug log). Usage: sound.py OUTDIR"""
import sys, time, json
from collections import Counter
from playwright.sync_api import sync_playwright
from harness import server, Checks, new_context, Game

OUT = sys.argv[1] if len(sys.argv) > 1 else '.'
check, errors = Checks(), []
LOG = 'window.__pf.soundLog'
EV = 'window.__pf.S.events'


def near(a, b, tol=0.05):
    return a is not None and b is not None and abs(a - b) <= tol


with server() as port, sync_playwright() as p:
    b, ctx = new_context(p, port=port)

    # A) Day 1 played by the bot
    g = Game(ctx, port, errors, speed=3)
    g.page.wait_for_timeout(300)
    g.start('1-1')
    actions = g.bot_play(extras=True)
    g.page.wait_for_selector('#summary:not(.hidden)')
    g.page.wait_for_timeout(2600)  # stars play after the summary appears
    snd, ev, rec = g.ev(LOG), g.ev(EV), g.ev('window.__pf.S.record')
    ids = Counter(s['id'] for s in snd)
    first_kitchen = next(i for i, s in enumerate(snd) if s['id'] == 'music_kitchen')
    check('A music_title on the panel, then music_kitchen at start', any(s['id'] == 'music_title' for s in snd[:first_kitchen]))
    check('A sfx_button on Start', ids['sfx_button'] >= 1)
    seat = [e['t'] for e in ev if e['e'] == 'customer_seated']
    arr = [s['t'] for s in snd if s['id'] == 'sfx_customer_arrive']
    check('A sfx_customer_arrive once per customer, same moment', len(arr) == len(seat) and all(near(x, y) for x, y in zip(arr, seat)), (arr, seat))
    srv = [e['t'] for e in ev if e['e'] == 'dish_served']
    ok = [s['t'] for s in snd if s['id'] == 'sfx_serve_ok']
    check('A sfx_serve_ok once per dish served, same moment', len(ok) == len(srv) and all(near(x, y) for x, y in zip(ok, srv)), (ok, srv))
    popped = sum(1 for e in ev if e['e'] == 'bubble_popped')
    check('A sfx_bubble_pop once per grabbed bubble', ids['sfx_bubble_pop'] == popped, (ids['sfx_bubble_pop'], popped))
    check('A sfx_grab on station / mid-air pickups', ids['sfx_grab'] >= 4, ids['sfx_grab'])
    places = sum(1 for e in ev if e['e'] in ('item_placed', 'dish_assembled', 'item_stored')) + sum(1 for e in ev if e['e'] == 'item_replaced' and not e['on'].startswith('storage'))
    check('A sfx_place once per placement', ids['sfx_place'] == places, (ids['sfx_place'], places))
    check('A sfx_trash once per item thrown away', ids['sfx_trash'] == sum(1 for e in ev if e['e'] == 'item_thrown_away'), ids['sfx_trash'])
    grill_t = [e['t'] for e in ev if e['e'] == 'item_placed' and e['on'] == 'grill']
    loops = [s for s in snd if s['id'] == 'sfx_bake_loop']
    starts = [s['t'] for s in loops if s['note'] == 'loop start']
    check('A sfx_bake_loop starts when a flatbread goes on the grill', len(starts) >= 1 and all(any(abs(t - x) < 0.1 for x in grill_t) for t in starts), (starts, grill_t))
    check('A sfx_bake_loop stops (starts == stops)', sum(1 for s in loops if s['note'] == 'loop start') == sum(1 for s in loops if s['note'] == 'loop stop'))
    ready = [s['t'] for s in snd if s['id'] == 'sfx_bake_ready']
    check('A sfx_bake_ready 6 s after each flatbread goes on the grill', len(ready) >= len(srv) and all(any(abs(r - (x + 6)) < 0.1 for x in grill_t) for r in ready), (ready, grill_t))
    end_t = rec['runTimeSec']
    de = [s for s in snd if s['id'] == 'sfx_day_end']
    check('A sfx_day_end once at the end of the day', len(de) == 1 and near(de[0]['t'], end_t, 0.1), (de, end_t))
    stars = [s['id'] for s in snd if s['id'].startswith('sfx_star_')]
    check('A one star sound per star, in order', stars == [f'sfx_star_{k}' for k in range(1, rec['stars'] + 1)], (stars, rec['stars']))
    check('A no wrong/leave/run-over sounds in a clean day', ids['sfx_wrong_dish'] == 0 and ids['sfx_customer_leaves'] == rec['customersLost'] and ids['sfx_run_over'] == 0)
    check('A no sound when a bubble spawns', not any(s['id'] == 'sfx_bubble_spawn' for s in snd) and ids['sfx_bubble_pop'] < sum(1 for e in ev if e['e'] == 'bubble_spawned'))
    json.dump({'actions': actions, 'sounds': dict(ids)}, open(f'{OUT}/sound-day1.json', 'w'), indent=1)
    g.page.close()

    # B) burn warning ticks speed up, burnt fzzt, wrong dish bonk
    g = Game(ctx, port, errors, speed=4)
    g.start('1-1')
    for _ in range(300):
        bub = g.ev("(() => { const b = window.__pf.S.bubbles.find(b => b.ing === 'flatbread' && b.y > 70); return b ? {x:b.x,y:b.y} : null })()")
        if bub: break
        g.page.wait_for_timeout(20)
    g.drag(bub, g.ev('window.__pf.grillSlotPos(0)'))
    g.page.wait_for_function("window.__pf.S.events.some(e => e.e === 'flatbread_burnt')", timeout=20000)
    g.page.wait_for_timeout(300)
    snd, ev = g.ev(LOG), g.ev(EV)
    placed = next(e['t'] for e in ev if e['e'] == 'item_placed' and e['on'] == 'grill')
    ticks = [s['t'] for s in snd if s['id'] == 'sfx_bake_warning']
    gaps = [round(b2 - a, 2) for a, b2 in zip(ticks, ticks[1:])]
    check('B sfx_bake_ready at placed + 6 s', any(near(s['t'], placed + 6, 0.1) for s in snd if s['id'] == 'sfx_bake_ready'))
    check('B sfx_bake_warning ticks only between glow (+14 s) and burn (+18 s)', ticks and near(ticks[0], placed + 14, 0.1) and ticks[-1] < placed + 18, (placed, ticks))
    check('B warning ticks get faster', len(gaps) >= 5 and gaps[-1] < gaps[0] and all(x >= y - 0.02 for x, y in zip(gaps, gaps[1:])), gaps)
    burnt = [s['t'] for s in snd if s['id'] == 'sfx_bake_burnt']
    check('B sfx_bake_burnt at placed + 18 s', len(burnt) == 1 and near(burnt[0], placed + 18, 0.1), (burnt, placed))
    loops = [s for s in snd if s['id'] == 'sfx_bake_loop']
    check('B bake loop stops when the flatbread burns', loops and loops[-1]['note'] == 'loop stop' and near(loops[-1]['t'], burnt[0], 0.1), loops)
    g.ev("(() => { window.__pf.S.storage[0] = {id: 9999, t: 'dish', dish: 'mushroom'}; return 1 })()")
    K = g.ev('window.__pf.centers()')
    g.drag(K['storage'][0], K['slots'][0])
    check('B sfx_wrong_dish on a refused dish', any(s['id'] == 'sfx_wrong_dish' for s in g.ev(LOG)))
    g.tap(K['pause'])
    g.page.wait_for_timeout(150)
    check('B pause tap plays sfx_button', g.ev(LOG)[-1]['id'] == 'sfx_button')
    g.page.close()

    # C) idle Day 4: angry arrivals, customers leaving (-10), last-10-seconds ticks, day end, no stars
    g = Game(ctx, port, errors, speed=12)
    g.start('1-4')
    g.page.wait_for_selector('#summary:not(.hidden)', timeout=60000)
    g.page.wait_for_timeout(2600)
    snd, ev = g.ev(LOG), g.ev(EV)
    ang_seat = [e['t'] for e in ev if e['e'] == 'customer_seated' and any(a['e'] == 'customer_arrived' and a['cid'] == e['cid'] and a['type'] == 'angry' for a in ev)]
    ang = [s['t'] for s in snd if s['id'] == 'sfx_angry_arrive']
    check('C sfx_angry_arrive once per angry alien, when seated', len(ang) == 2 and all(near(x, y) for x, y in zip(ang, ang_seat)), (ang, ang_seat))
    reg = [s['t'] for s in snd if s['id'] == 'sfx_customer_arrive']
    check('C regular arrivals use sfx_customer_arrive (6)', len(reg) == 6, reg)
    lost = [e['t'] for e in ev if e['e'] == 'customer_lost']
    lv = [s['t'] for s in snd if s['id'] == 'sfx_customer_leaves']
    check('C sfx_customer_leaves at every -10', len(lv) == len(lost) == 8 and all(near(x, y) for x, y in zip(lv, lost)), (lv, lost))
    tw = [s['t'] for s in snd if s['id'] == 'sfx_time_warning']
    check('C sfx_time_warning once per second for the last 10 s', len(tw) == 10 and all(near(t, 80 + k, 0.05) for k, t in enumerate(tw)), tw)
    check('C sfx_day_end after overtime, no stars', sum(1 for s in snd if s['id'] == 'sfx_day_end') == 1 and not any(s['id'].startswith('sfx_star') for s in snd))
    g.page.close()

    # D) marathon start + run over
    g = Game(ctx, port, errors, speed=20)
    g.start('marathon')
    g.page.wait_for_timeout(300)
    s0 = g.ev(LOG)
    check('D marathon: music_kitchen + first customer arrive at t~0', any(s['id'] == 'music_kitchen' for s in s0) and any(s['id'] == 'sfx_customer_arrive' and s['t'] < 0.1 for s in s0), [x for x in s0 if x['t'] is not None][:3])
    g.page.wait_for_selector('#summary:not(.hidden)', timeout=60000)
    g.page.wait_for_timeout(300)
    snd = g.ev(LOG)
    check('D sfx_customer_leaves x3 then sfx_run_over once', sum(1 for s in snd if s['id'] == 'sfx_customer_leaves') == 3 and sum(1 for s in snd if s['id'] == 'sfx_run_over') == 1 and not any(s['id'] == 'sfx_day_end' for s in snd))
    g.page.close()

    # E) muted: the game plays the same, sounds are still logged, master gain is 0
    g = Game(ctx, port, errors, speed=3)
    g.page.tap('#muteBtn')
    g.page.reload()
    g.start('1-1')
    g.bot_play()
    g.page.wait_for_selector('#summary:not(.hidden)')
    rec = g.ev('window.__pf.S.record')
    check('E muted Day 1 completes like normal', rec['ended'] == 'completed' and rec['dishesServed'] == 4 and rec['customersLost'] == 0, {k: rec[k] for k in ('ended', 'dishesServed', 'total', 'stars')})
    check('E muted setting saved and applied', g.ev('window.__pf.SND.settings.muted') is True)
    g.page.tap('#backBtn'); g.page.tap('#muteBtn')
    g.page.close()
    b.close()

check('no console errors or warnings', not errors, errors)
sys.exit(check.report())
