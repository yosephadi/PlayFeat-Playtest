"""Encode the music tracks to AAC .m4a and find seamless loop points (stdlib + macOS afconvert only).

Usage: python3 tools/music.py DOWNLOAD_DIR
Loop points are measured on the ENCODED .m4a (decoded again), so they match what the browser plays.
Prints loopStart/loopEnd (seconds) for SOUND_CONFIG and updates audio/manifest.json.
"""
import os, sys, json, struct, array, subprocess, tempfile, math

DL = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'audio')
TMP = tempfile.mkdtemp()


def read_wav_mono(path):
    b = open(path, 'rb').read()
    i, ch, sr, data = 12, 1, 44100, b''
    while i + 8 <= len(b):
        cid, size = b[i:i + 4], struct.unpack('<I', b[i + 4:i + 8])[0]
        if cid == b'fmt ':
            _, ch, sr, _, _, _ = struct.unpack('<HHIIHH', b[i + 8:i + 24])
        elif cid == b'data':
            data = b[i + 8:i + 8 + size]
        i += 8 + size + (size & 1)
    a = array.array('h', data[:len(data) // 2 * 2])
    if ch == 2:
        a = array.array('f', [(a[k] + a[k + 1]) * 0.5 for k in range(0, len(a) - 1, 2)])
    else:
        a = array.array('f', a)
    return a, sr


def envelope(a, sr, hop):
    env = array.array('f')
    for s in range(0, len(a) - hop, hop):
        seg = a[s:s + hop]
        env.append(math.sqrt(sum(x * x for x in seg) / hop))
    return env


def ncc(x, y):
    n = min(len(x), len(y))
    if n == 0:
        return 0.0
    mx, my = sum(x[:n]) / n, sum(y[:n]) / n
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    sxx = sum((x[i] - mx) ** 2 for i in range(n)); syy = sum((y[i] - my) ** 2 for i in range(n))
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.0


def tempo(env, fps):
    nov = array.array('f', [max(0.0, env[i] - env[i - 1]) for i in range(1, len(env))])
    best, bl = -1, 0
    for lag in range(int(fps * 60 / 180), int(fps * 60 / 70) + 1):  # 70..180 bpm
        c = sum(nov[i] * nov[i + lag] for i in range(len(nov) - lag)) / (len(nov) - lag)
        if c > best:
            best, bl = c, lag
    return bl / fps  # seconds per beat (coarse)


def find_loop(a, sr, a_range, b_range, period=None, win_s=3.0):
    fps = 100; hop = sr // fps
    env = envelope(a, sr, hop)
    w = int(win_s * fps)
    best = (-2, 0, 0)
    for ai in range(int(a_range[0] * fps), int(a_range[1] * fps)):
        ea = env[ai - w // 2: ai + w // 2]
        if len(ea) < w:
            continue
        if period:
            ks = range(1, 200)
            cands = [ai + round(k * period * fps) for k in ks]
            cands = [c for c in cands if b_range[0] * fps <= c <= b_range[1] * fps]
            # allow +-30 ms slack around each bar multiple
            cands = [c + d for c in cands for d in range(-3, 4)]
        else:
            cands = range(int(b_range[0] * fps), int(b_range[1] * fps))
        for bi in cands:
            eb = env[bi - w // 2: bi + w // 2]
            if len(eb) < w:
                continue
            s = ncc(ea, eb) - 0.5 * abs(sum(ea) - sum(eb)) / max(1e-9, sum(ea))
            if s > best[0]:
                best = (s, ai, bi)
    _, ai, bi = best
    # fine alignment on raw samples: keep start fixed, slide the end +-15 ms
    A, B = ai * hop, bi * hop
    win = int(0.08 * sr); half = win // 2
    xa = a[A - half:A + half]
    bestd, bestc = 0, -2
    for d in range(-int(0.015 * sr), int(0.015 * sr) + 1, 2):
        c = ncc(xa, a[B + d - half:B + d + half])
        if c > bestc:
            bestc, bestd = c, d
    B += bestd
    # nudge both to the nearest rising zero crossing (within 2 ms) to avoid a click
    def zc(p):
        for k in range(int(0.002 * sr)):
            for q in (p + k, p - k):
                if a[q - 1] <= 0 < a[q]:
                    return q
        return p
    A2, B2 = zc(A), zc(B)
    return A2 / sr, B2 / sr, best[0], bestc


def encode(src, dst, kbps):
    subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', str(kbps * 1000), src, dst], check=True, capture_output=True)


def decode(src):
    w = os.path.join(TMP, os.path.basename(src) + '.wav')
    subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16', src, w], check=True, capture_output=True)
    return read_wav_mono(w)


os.makedirs(os.path.join(OUT, 'music'), exist_ok=True)
results = {}

# Kitchen music: bar-quantised loop after the intro and before the ending
dst = os.path.join(OUT, 'music', 'shake_and_bake.m4a')
encode(os.path.join(DL, 'shake_and_bake.mp3'), dst, 96)
a, sr = decode(dst)
dur = len(a) / sr
beat = tempo(envelope(a, sr, sr // 100), 100)
bar = beat * 4
s, e, score, fine = find_loop(a, sr, (4.0, 16.0), (dur * 0.55, dur - 6.0), period=bar)
results['music_kitchen'] = dict(file='audio/music/shake_and_bake.m4a', dur=round(dur, 3), bpm=round(60 / beat, 1),
                                loopStart=round(s, 4), loopEnd=round(e, 4), envScore=round(score, 3), sampleCorr=round(fine, 3))

# Title music: designed as a loop; find the cleanest point near the very start and end
dst = os.path.join(OUT, 'music', 'outer_space_loop.m4a')
encode(os.path.join(DL, 'outer_space.mp3'), dst, 80)
a, sr = decode(dst)
dur = len(a) / sr
s, e, score, fine = find_loop(a, sr, (0.2, 2.5), (dur - 3.5, dur - 0.3), period=None, win_s=1.5)
results['music_title'] = dict(file='audio/music/outer_space_loop.m4a', dur=round(dur, 3),
                              loopStart=round(s, 4), loopEnd=round(e, 4), envScore=round(score, 3), sampleCorr=round(fine, 3))

man_path = os.path.join(OUT, 'manifest.json')
man = [m for m in (json.load(open(man_path)) if os.path.exists(man_path) else []) if m.get('group') != 'Music']
man = [
    dict(file='audio/music/shake_and_bake.m4a', group='Music', name='shake_and_bake', title='Shake and Bake', author='Matthew Pablo (www.matthewpablo.com)',
         license='CC-BY 3.0', url='https://opengameart.org/content/shake-and-bake', dur=results['music_kitchen']['dur'],
         kb=round(os.path.getsize(os.path.join(OUT, 'music', 'shake_and_bake.m4a')) / 1024, 1)),
    dict(file='audio/music/outer_space_loop.m4a', group='Music', name='outer_space_loop', title='Outer Space Loop', author='wipics',
         license='CC0 1.0', url='https://opengameart.org/content/outer-space-loop', dur=results['music_title']['dur'],
         kb=round(os.path.getsize(os.path.join(OUT, 'music', 'outer_space_loop.m4a')) / 1024, 1)),
] + man
json.dump(man, open(man_path, 'w'), indent=1)
print(json.dumps(results, indent=1))
