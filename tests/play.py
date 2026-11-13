"""Bot plays a level by touch, then checks the summary, copy row, CSV/JSON downloads and saved runs.
Usage: play.py LEVEL SPEED OUTDIR [--extras] [--flow=refill|schedule]"""
import sys, csv, io, json
from playwright.sync_api import sync_playwright
from harness import server, Checks, new_context, Game

level, speed, OUT = sys.argv[1], float(sys.argv[2]), sys.argv[3]
extras = '--extras' in sys.argv
flow = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--flow=')), None)
check, errors = Checks(), []
with server() as port, sync_playwright() as p:
    b, ctx = new_context(p, dpr=2, perms=True, port=port)
    g = Game(ctx, port, errors, speed=speed)
    page = g.page
    g.start(level, f'bot-{level}', flow=flow)
    shots = {'mid': False}
    def tick(st):
        if not shots['mid'] and st['t'] > (60 if level == 'rounds' else 9):
            page.screenshot(path=f'{OUT}/{level}-1-midgame.png'); shots['mid'] = True
    actions = g.bot_play(timeout=450, extras=extras, on_tick=tick)
    page.wait_for_selector('#summary:not(.hidden)', timeout=15000)
    page.screenshot(path=f'{OUT}/{level}-2-summary.png')
    rec = page.evaluate('window.__pf.S.record'); ev = rec['events']
    served = [e for e in ev if e['e'] == 'dish_served']
    table = page.inner_text('#summary .cols')
    check('summary shows dishes served', f"Dishes served\t{rec['dishesServed']}" in table)
    check('total = score + tips', rec['total'] == rec['score'] + rec['tips'])
    check('served count matches events', len(served) == rec['dishesServed'])
    check('tips match events', rec['tips'] == sum(e['tip'] for e in served))
    if rec['stars'] is not None:
        check('stars match targets', rec['stars'] == sum(1 for x in rec['starTargets'] if rec['total'] >= x))
    page.fill('#notes', 'bot note, with comma')
    page.tap('#copyRow'); page.wait_for_timeout(300)
    cols = page.evaluate('navigator.clipboard.readText()').split('\t'); ncol = page.evaluate('window.__pf.COLS.length')
    names = [c[0] for c in page.evaluate('window.__pf.COLS')]
    check('copied TSV row has all columns', len(cols) == ncol and cols[names.index('notes')] == 'bot note, with comma', len(cols))
    page.tap('#copyHead'); page.wait_for_timeout(200)
    head = page.evaluate('navigator.clipboard.readText()').split('\t')
    check('copy column headers', len(head) == ncol and head[0] == 'run_id')
    with page.expect_download() as d1:
        page.click('#summary .dlCsv')
    d1.value.save_as(f'{OUT}/{level}-runs.csv')
    with page.expect_download() as d2:
        page.click('#summary .dlJson')
    d2.value.save_as(f'{OUT}/{level}-runs.json')
    rows = list(csv.reader(io.open(f'{OUT}/{level}-runs.csv', newline=''))); nruns = page.evaluate('window.__pf.runs.length')
    check('CSV has header + one row per run', len(rows) == nruns + 1 and rows[-1][rows[0].index('notes')] == 'bot note, with comma')
    js = json.load(open(f'{OUT}/{level}-runs.json'))
    check('JSON has runs with events', len(js['runs']) == nruns and len(js['runs'][-1]['events']) > 10)
    page.tap('#backBtn')
    check('panel lists recent runs', page.locator('#recent tr').count() >= 1)
    page.reload(); page.wait_for_timeout(300)
    check('runs survive reload', 'saved on this device' in page.inner_text('#runsInfo'))
    check('no page scroll', page.evaluate('document.scrollingElement.scrollTop === 0 && document.scrollingElement.scrollHeight <= innerHeight + 1'))
    b.close()
check('no console errors', not errors, errors[:5])
print(json.dumps({'record': {k: rec.get(k) for k in ('ended', 'customerFlow', 'runTimeSec', 'dishesServed', 'customersLost', 'score', 'tips', 'total', 'stars', 'stageReached', 'counterIdleSec', 'avgSecBetweenServes')}, 'actions': actions}))
sys.exit(check.report())
