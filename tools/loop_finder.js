// Finds a seamless loop (loopStart, loopEnd) in a decoded track by searching for an exact repeat.
// Runs in a browser page (used by tools/loops.py through Playwright). Returns seconds in decoded-buffer time.
async function findLoop(url, opts) {
  const o = Object.assign({ minLag: 20, maxLag: null, aMin: 1.5, endGuard: 4 }, opts || {});
  const buf = await new OfflineAudioContext(1, 1, 44100).decodeAudioData(await (await fetch(url)).arrayBuffer());
  const sr = buf.sampleRate, n = buf.length;
  const x = new Float32Array(n);
  for (let c = 0; c < buf.numberOfChannels; c++) { const d = buf.getChannelData(c); for (let i = 0; i < n; i++) x[i] += d[i] / buf.numberOfChannels; }
  const dur = n / sr;
  // 1) onset envelope at 100 fps (high-passed energy difference)
  const hop = Math.round(sr / 100), m = Math.floor(n / hop);
  const env = new Float32Array(m);
  let prev = 0;
  for (let k = 0; k < m; k++) {
    let e = 0; for (let i = k * hop + 1; i < (k + 1) * hop; i++) { const h = x[i] - x[i - 1]; e += h * h; }
    e = Math.sqrt(e / hop); env[k] = Math.max(0, e - prev); prev = e;
  }
  // 2) best repeat lag over the whole track
  const maxLag = Math.min(o.maxLag || dur, dur - o.aMin - o.endGuard);
  let bestL = 0, bestR = -1;
  for (let L = Math.round(o.minLag * 100); L <= Math.round(maxLag * 100); L++) {
    let s = 0, sa = 0, sb = 0;
    for (let k = 0; k + L < m; k++) { s += env[k] * env[k + L]; sa += env[k] * env[k]; sb += env[k + L] * env[k + L]; }
    const r = s / Math.sqrt(sa * sb + 1e-12);
    if (r > bestR) { bestR = r; bestL = L; }
  }
  // 3) refine the lag to the sample using raw-signal correlation over several 0.5 s windows
  const ncc = (a0, b0, len) => {
    let sxy = 0, sxx = 0, syy = 0;
    for (let i = 0; i < len; i++) { const p = x[a0 + i], q = x[b0 + i]; sxy += p * q; sxx += p * p; syy += q * q; }
    return sxy / Math.sqrt(sxx * syy + 1e-12);
  };
  const Lc = bestL * hop, win = Math.round(0.5 * sr);
  const probes = [];
  for (let t = o.aMin * sr; t + Lc + win < n - o.endGuard * sr; t += 3 * sr) probes.push(Math.round(t));
  let bestLag = Lc, bestC = -2;
  for (let d = -hop * 2; d <= hop * 2; d++) {
    let c = 0; for (const p of probes) c += ncc(p, p + Lc + d, win);
    c /= probes.length;
    if (c > bestC) { bestC = c; bestLag = Lc + d; }
  }
  // 4) choose the loop start where the two copies match best locally (0.25 s window), at a rising zero crossing
  let bestA = Math.round(o.aMin * sr), bestLoc = -2;
  const lw = Math.round(0.25 * sr), step = Math.round(0.01 * sr);
  for (let a = Math.round(o.aMin * sr); a + bestLag + lw < n - o.endGuard * sr; a += step) {
    const c = ncc(a - (lw >> 1), a + bestLag - (lw >> 1), lw);
    if (c > bestLoc) { bestLoc = c; bestA = a; }
  }
  let A = bestA;
  for (let k = 0; k < sr * 0.003; k++) { if (x[A + k - 1] <= 0 && x[A + k] > 0) { A += k; break; } }
  return { dur, sampleRate: sr, lagSec: bestLag / sr, envR: bestR, lagCorr: bestC, loopStart: A / sr, loopEnd: (A + bestLag) / sr, localCorr: ncc(A - (lw >> 1), A + bestLag - (lw >> 1), lw) };
}
