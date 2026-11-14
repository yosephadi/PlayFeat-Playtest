"""Refill customer flow (story days): step-up delay, counter spots, patience, angry by count, day end, toggle, logging.
Usage: refill.py"""
from playwright.sync_api import sync_playwright
from harness import server, Checks, new_context, Game, finish

check, errors = Checks(), []
DT = 1 / 60 + 0.005  # one frame of slack


def counter_max(ev):
    """Most customers at the counter at once, replayed from the event log."""
    n = top = 0
    for e in ev:
        if e['e'] == 'customer_seated': n += 1; top = max(top, n)
        elif e['e'] in ('dish_served', 'customer_lost'): n -= 1
    return top


def serve_first(g):
    """Put the dish the first customer wants into the front storage insert and drag it to them."""
    K = g.ev('window.__pf.centers()')
    g.ev("(() => { const S = window.__pf.S, c = S.seated[0]; S.storage[0] = {id: 99999 + S.served, t: 'dish', dish: c.order}; return 1 })()")
    g.drag(K['storage'][0], K['slots'][0])


with server() as port, sync_playwright() as p:
    b, ctx = new_context(p, port=port)

    # --- no flow toggle; story days always refill; no regular Marathon
    g = Game(ctx, port, errors)
    check('no customer flow toggle on the panel', g.page.locator('#flowRow').count() == 0 and g.page.locator('button.fl').count() == 0)
    check('regular Marathon is not on the panel (only Marathon Rounds)', g.page.locator('button.lv[data-level="marathon"]').count() == 0
          and [b for b in g.page.locator('#levelBtns button').all_inner_texts() if 'Marathon' in b] == ['Marathon Rounds'])
    g.page.close()

    # --- fixed first order on every level (1-5: sorbet, the rest: pepper)
    for lv in ('1-1', '1-2', '1-3', '1-4', '1-5', '1-6'):
        g = Game(ctx, port, errors, speed=1); g.start(lv)
        first = 'sorbet' if lv == '1-5' else 'pepper'
        check(f'{lv}: refill flow, first order {first}', g.ev('window.__pf.S.customerFlow') == 'refill' and g.ev('window.__pf.S.orderSequence[0]') == first)
        g.page.close()

    # --- Day 1 idle: 1 spot, patience only at the counter, 2 s after each loss, nobody new after 90 s, overtime serve
    g = Game(ctx, port, errors, speed=8); g.start('1-1')
    g.page.wait_for_function('window.__pf.S.t >= 80', timeout=60000)
    # customer 2 (stepped up at 47 s) would leave at 92 s: give them time so we can serve in overtime
    g.ev("(() => { const c = window.__pf.S.seated[0]; c.left = c.patienceMax = 40; return 1 })()")
    g.page.wait_for_function('window.__pf.S.t >= 91', timeout=60000)
    ev = g.ev('window.__pf.S.events')
    ups = [e for e in ev if e['e'] == 'customer_stepped_up']
    lost = [e for e in ev if e['e'] == 'customer_lost']
    seats = [e for e in ev if e['e'] == 'customer_seated']
    arr = [e for e in ev if e['e'] == 'customer_arrived']
    check('Day 1: never more than 1 customer at the counter', counter_max(ev) == 1, counter_max(ev))
    check('patience does not run before stepping up (seated the moment they appear, full patience)',
          all(s['waitedOutside'] == 0 for s in seats) and all(a['patience'] == 45 for a in arr) and len(seats) == len(ups))
    gaps = [u['t'] - l['t'] for l, u in zip(lost, ups[1:])]
    check('after a loss the next customer steps up 2 s later', gaps and all(abs(x - 2) <= DT for x in gaps), gaps)
    check('lost customers were all at the counter (45 s each)', all(any(s['cid'] == l['cid'] for s in seats) for l in lost) and len(lost) == 1)
    check('no new customer steps up after 90 s', all(u['t'] < 90 for u in ups) and g.ev('window.__pf.S.seated.length') == 1, [u['t'] for u in ups])
    serve_first(g)
    g.page.wait_for_selector('#summary:not(.hidden)', timeout=5000)
    rec = g.ev('window.__pf.S.record')
    srv = [e for e in rec['events'] if e['e'] == 'dish_served']
    check('a customer still at the counter can be served in overtime, then the day ends',
          srv and srv[-1]['t'] > 90 and rec['ended'] == 'completed' and not any(e['e'] == 'customer_stepped_up' and e['t'] > 90 for e in rec['events']), (srv, rec['ended'], rec['runTimeSec']))
    check('record: customer flow and counter idle time', rec['customerFlow'] == 'refill' and rec['counterIdleSec'] is not None and abs(rec['counterIdleSec'] - 2) <= 0.2, rec['counterIdleSec'])
    names = [c[0] for c in g.ev('window.__pf.COLS')]
    check('export columns: customer_flow and counter_idle_s', 'customer_flow' in names and 'counter_idle_s' in names)
    check('summary labels the stars as placeholders', 'placeholder targets' in g.page.inner_text('#summary'))
    g.page.close()

    # --- after a serve, the next customer appears ~2 s later
    g = Game(ctx, port, errors, speed=1); g.start('1-1')
    g.page.wait_for_timeout(300)
    serve_first(g)
    t_srv = g.ev('window.__pf.S.events.filter(e => e.e === "dish_served")[0].t')
    g.page.wait_for_timeout(1000)
    mid = g.ev('window.__pf.S.seated.length')
    g.page.wait_for_function('window.__pf.S.seated.length === 1', timeout=4000)
    t_up = g.ev('window.__pf.S.events.filter(e => e.e === "customer_stepped_up")[1].t')
    check('after a serve the spot stays empty, then the next customer steps up 2 s later', mid == 0 and abs(t_up - t_srv - 2) <= DT, (t_srv, t_up))
    g.page.close()

    # --- 1-6: angry by count, max 3 at the counter, start staggered 0/2/4 s
    for lv, angry in (('1-6', [4, 7]),):
        g = Game(ctx, port, errors, speed=4); g.start(lv, f'bot-{lv}')
        g.bot_play(timeout=200)
        g.page.wait_for_selector('#summary:not(.hidden)', timeout=15000)
        rec = g.ev('window.__pf.S.record'); ev = rec['events']
        ups = [e for e in ev if e['e'] == 'customer_stepped_up']
        got = [u['n'] for u in ups if u['type'] == 'angry']
        check(f'{lv}: angry customers are exactly #{angry} (sorbet)', got == [n for n in angry if n <= len(ups)] and all(u['order'] == 'sorbet' for u in ups if u['type'] == 'angry') and len(ups) >= max(angry), (got, len(ups)))
        check(f'{lv}: never more than 3 at the counter', counter_max(ev) <= 3, counter_max(ev))
        check(f'{lv}: first three step up at 0 / 2 / 4 s', [round(u['t']) for u in ups[:3]] == [0, 2, 4], [u['t'] for u in ups[:3]])
        check(f'{lv}: orders come only from the refill pool', all(u['order'] in ('pepper', 'mushroom', 'sorbet') for u in ups))
        check(f'{lv}: total = score + tips, stars from the same targets', rec['total'] == rec['score'] + rec['tips'] and rec['stars'] == sum(1 for x in rec['starTargets'] if rec['total'] >= x))
        print(lv, 'bot result', {k: rec[k] for k in ('dishesServed', 'customersLost', 'score', 'tips', 'total', 'stars', 'runTimeSec', 'counterIdleSec', 'avgSecBetweenServes')})
        g.page.close()

    # --- 1-3 at most 2 at the counter (idle day)
    g = Game(ctx, port, errors, speed=12); g.start('1-3')
    g.page.wait_for_selector('#summary:not(.hidden)', timeout=60000)
    ev = g.ev('window.__pf.S.record.events')
    check('1-3 idle: never more than 2 at the counter, everyone lost at the counter', counter_max(ev) == 2 and g.ev('window.__pf.S.record.customersLost') == len([e for e in ev if e['e'] == 'customer_stepped_up']))
    g.page.close()
    finish(check, b, errors)
