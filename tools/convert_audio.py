"""Convert downloaded sounds to trimmed mono AAC .m4a (plays on iPad Safari).
Uses only macOS `afconvert` + the Python standard library (no ffmpeg needed).

Usage: python3 tools/convert_audio.py DOWNLOAD_DIR
Writes into playfeat-prototype/audio/ and audio/manifest.json.

DOWNLOAD_DIR must contain:
  kenney_interface-sounds/, kenney_digital-audio/, kenney_sci-fi-sounds/   (unzipped Kenney packs)
  mixkit_bowl_placed.wav, mixkit_oven_ding.wav, mixkit_frying_eggs.wav
  shake_and_bake.mp3, outer_space.mp3   (music is converted separately by tools/music.py)
"""
import os, sys, wave, subprocess, json, tempfile, array

DL = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'audio')
TMP = tempfile.mkdtemp()


def to_wav(src, dst):
    subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16', src, dst], check=True, capture_output=True)


def read_mono(path):
    # Minimal RIFF parser: afconvert writes WAVE_FORMAT_EXTENSIBLE, which Python 3.9's wave module rejects.
    import struct
    b = open(path, 'rb').read()
    assert b[:4] == b'RIFF' and b[8:12] == b'WAVE', path
    i, ch, sr, bits, data = 12, None, None, None, None
    while i + 8 <= len(b):
        cid, size = b[i:i + 4], struct.unpack('<I', b[i + 4:i + 8])[0]
        if cid == b'fmt ':
            _, ch, sr, _, _, bits = struct.unpack('<HHIIHH', b[i + 8:i + 24])
        elif cid == b'data':
            data = b[i + 8:i + 8 + size]
        i += 8 + size + (size & 1)
    assert bits == 16 and data is not None, path
    a = array.array('h', data[:len(data) // 2 * 2])
    if ch > 1:
        a = array.array('h', [int(sum(a[i:i + ch]) / ch) for i in range(0, len(a), ch)])
    return a, sr


def write_wav(path, a, sr):
    w = wave.open(path, 'wb')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(a.tobytes()); w.close()


def trim(a, sr, thr=0.004, pad=0.006):
    """Cut leading/trailing silence (below thr of full scale) and add a 4 ms fade-out."""
    t = int(32767 * thr)
    n = len(a)
    s = next((i for i in range(n) if abs(a[i]) > t), 0)
    e = next((i for i in range(n - 1, -1, -1) if abs(a[i]) > t), n - 1)
    p = int(pad * sr)
    out = a[max(0, s - p):min(n, e + 4 * p)]
    f = min(len(out), int(0.004 * sr))
    for i in range(f):
        out[len(out) - f + i] = int(out[len(out) - f + i] * (1 - i / f))
    return out


def loop_cut(start_s, length_s, xf_s):
    """Cut a segment and crossfade its tail into its head so it loops without a click."""
    def p(a, sr):
        s, n, f = int(start_s * sr), int(length_s * sr), int(xf_s * sr)
        seg = a[s:s + n]
        out = array.array('h', seg[:n - f])
        for i in range(f):
            k = i / f
            out[i] = int(seg[i] * k + seg[n - f + i] * (1 - k))
        return out
    return p


def to_m4a(wav, dst, kbps=64):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', str(kbps * 1000), wav, dst], check=True, capture_output=True)


def duration(path):
    out = subprocess.run(['afinfo', path], capture_output=True, text=True).stdout
    return float([l for l in out.splitlines() if 'estimated duration' in l][0].split()[2])


manifest = []


def add(src, rel, meta, kbps=64, process=None):
    w = os.path.join(TMP, 'a.wav'); to_wav(src, w)
    a, sr = read_mono(w)
    a = process(a, sr) if process else trim(a, sr)
    t = os.path.join(TMP, 'b.wav'); write_wav(t, a, sr)
    dst = os.path.join(OUT, rel)
    to_m4a(t, dst, kbps)
    manifest.append(dict(file='audio/' + rel, dur=round(duration(dst), 3), kb=round(os.path.getsize(dst) / 1024, 1), **meta))


KENNEY = {
    'interface-sounds': ('Interface Sounds', 'https://kenney.nl/assets/interface-sounds'),
    'digital-audio': ('Digital Audio', 'https://kenney.nl/assets/digital-audio'),
    'sci-fi-sounds': ('Sci-fi Sounds', 'https://kenney.nl/assets/sci-fi-sounds'),
}
for pack, (title, url) in KENNEY.items():
    root = os.path.join(DL, 'kenney_' + pack)
    for dp, _, fs in os.walk(root):
        for f in sorted(fs):
            if not f.endswith('.ogg') or f == 'Preview.ogg':
                continue
            name = f[:-4]
            # 5-second engine/noise beds are long; keep them but at a lower bitrate
            kb = 40 if duration(os.path.join(dp, f)) > 3 else 64
            add(os.path.join(dp, f), f'kenney/{pack}/{name}.m4a',
                dict(group='Kenney ' + title, name=name, title=f'{title}: {name}', author='Kenney (www.kenney.nl)', license='CC0 1.0', url=url), kbps=kb)

MIX = 'https://mixkit.co/free-sound-effects/kitchen/'
MIXLIC = 'Mixkit Sound Effects Free License (https://mixkit.co/license/#sfxFree)'
add(os.path.join(DL, 'mixkit_bowl_placed.wav'), 'mixkit/bowl_placed.m4a',
    dict(group='Mixkit kitchen', name='bowl_placed', title='Bowl placed on table (Mixkit #1799)', author='Mixkit', license=MIXLIC, url=MIX))
add(os.path.join(DL, 'mixkit_oven_ding.wav'), 'mixkit/oven_ding.m4a',
    dict(group='Mixkit kitchen', name='oven_ding', title='Kitchen oven ding (Mixkit #1838)', author='Mixkit', license=MIXLIC, url=MIX))
add(os.path.join(DL, 'mixkit_frying_eggs.wav'), 'mixkit/frying_eggs_loop.m4a',
    dict(group='Mixkit kitchen', name='frying_eggs_loop', title='Frying eggs on hot pan (Mixkit #121), 6 s loop cut', author='Mixkit', license=MIXLIC, url=MIX),
    kbps=48, process=loop_cut(8.0, 6.5, 0.5))

old = os.path.join(OUT, 'manifest.json')
keep = [m for m in (json.load(open(old)) if os.path.exists(old) else []) if m.get('group') == 'Music']
json.dump(keep + manifest, open(old, 'w'), indent=1)
big = [(m['name'], m['kb']) for m in manifest if m['kb'] > 100]
print('effects:', len(manifest), 'files,', round(sum(m['kb'] for m in manifest)), 'KB total; over 100 KB:', big)
