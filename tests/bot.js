// Decides the next drag for the automated player. Returns {from,to,label} in logical coords, or {wait}/{ended}.
(() => {
  const pf = window.__pf, S = pf.S, K = pf.centers();
  if (!S) return { wait: true };
  if (S.ended) return { ended: true };
  if (S.held || S.paused) return { wait: true };
  const vis = b => b.y > 70 && b.y < 520;
  const plate = S.plates[0], g = S.grill[0];
  const orders = S.seated.map(c => c.order);
  const dishSpots = [];
  if (plate && plate.t === 'dish') dishSpots.push({ it: plate, p: K.plate });
  if (S.bowl && S.bowl.t === 'dish') dishSpots.push({ it: S.bowl, p: K.bowl });
  S.storage.forEach((it, i) => { if (it && it.t === 'dish') dishSpots.push({ it, p: K.storage[i] }); });
  for (const d of dishSpots) {
    const ci = S.seated.findIndex(c => c.order === d.it.dish);
    if (ci >= 0) return { from: d.p, to: K.slots[ci], label: 'serve ' + d.it.dish };
  }
  if (g && g.st === 'burnt') return { from: K.grill, to: K.trash, label: 'trash burnt' };
  const freeSt = S.storage.findIndex(x => !x);
  for (const [it, p] of [[plate, K.plate], [S.bowl, K.bowl]]) {
    if (it && it.t === 'dish' && !orders.includes(it.dish)) return { from: p, to: freeSt >= 0 ? K.storage[freeSt] : K.trash, label: 'park unwanted dish' };
  }
  const need = orders.slice();
  dishSpots.forEach(d => { const k = need.indexOf(d.it.dish); if (k >= 0) need.splice(k, 1); });
  const flatNeeds = need.filter(o => o !== 'sorbet'), sorbNeeds = need.filter(o => o === 'sorbet');
  const wantedTop = new Set(flatNeeds.map(o => o === 'pepper' ? 'pepper' : 'mushroom'));
  const bub = pred => S.bubbles.filter(b => vis(b) && pred(b.ing)).sort((a, b) => b.y - a.y)[0];
  const stIdx = pred => S.storage.findIndex(x => x && pred(x));
  if (g && g.st === 'baked' && !plate) return { from: K.grill, to: K.plate, label: 'grill->plate' };
  if (g && g.st === 'baked' && freeSt >= 0 && plate) return { from: K.grill, to: K.storage[freeSt], label: 'grill->storage' };
  if (plate && plate.t === 'flatbread' && plate.st === 'baked' && wantedTop.size) {
    const si = stIdx(x => wantedTop.has(x.t)); if (si >= 0) return { from: K.storage[si], to: K.plate, label: 'storage topping->plate' };
    const b = bub(k => wantedTop.has(k)); if (b) return { from: b, to: K.plate, label: 'bubble ' + b.ing + '->plate' };
  }
  if (!plate) { const si = stIdx(x => x.t === 'flatbread' && x.st === 'baked'); if (si >= 0) return { from: K.storage[si], to: K.plate, label: 'storage flatbread->plate' }; }
  if (sorbNeeds.length) {
    if (S.bowl && S.bowl.t === 'sorbet') {
      const want = 'drizzle';
      const si = stIdx(x => x.t === want); if (si >= 0) return { from: K.storage[si], to: K.bowl, label: 'storage ' + want + '->bowl' };
      const b = bub(k => k === want); if (b) return { from: b, to: K.bowl, label: 'bubble ' + want + '->bowl (dish)' };
    }
    if (!S.bowl) {
      const si = stIdx(x => x.t === 'sorbet'); if (si >= 0) return { from: K.storage[si], to: K.bowl, label: 'storage sorbet->bowl' };
      const b = bub(k => k === 'sorbet'); if (b) return { from: b, to: K.bowl, label: 'bubble sorbet->bowl' };
    }
  }
  const flatInPlay = (g && g.st !== 'burnt' ? 1 : 0) + (plate && plate.t === 'flatbread' ? 1 : 0) + S.storage.filter(x => x && x.t === 'flatbread' && x.st !== 'burnt').length;
  if (!g && flatNeeds.length > flatInPlay) {
    const si = stIdx(x => x.t === 'flatbread' && x.st === 'raw'); if (si >= 0) return { from: K.storage[si], to: K.grill, label: 'storage flatbread->grill' };
    const b = bub(k => k === 'flatbread'); if (b) return { from: b, to: K.grill, label: 'bubble flatbread->grill' };
  }
  if (freeSt >= 0 && S.storage.filter(Boolean).length === 0) {
    const want = [...wantedTop]; if (sorbNeeds.length) want.push('drizzle', 'sorbet');
    const have = new Set([plate && plate.t, S.bowl && S.bowl.t].filter(Boolean));
    const b = bub(k => want.includes(k) && !have.has(k));
    if (b) return { from: b, to: K.storage[freeSt], label: 'store ' + b.ing };
  }
  return { wait: true };
})()
