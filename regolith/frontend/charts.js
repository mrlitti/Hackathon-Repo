// SVG charts for Regolith. Mark specs follow the dataviz guide: 2px lines, 8px markers with a
// 2px surface ring, solid hairline grid, text in ink tokens (never series colours), hover + focus tooltips.
const NS = 'http://www.w3.org/2000/svg';
const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export const ORDER = ['SiO2', 'TiO2', 'Al2O3', 'Cr2O3', 'FeO', 'MnO', 'MgO', 'CaO', 'Na2O', 'K2O', 'P2O5', 'SO3', 'Cl', 'Ni', 'Zn', 'Br'];
export const SYMBOL = { SiO2: 'Si', TiO2: 'Ti', Al2O3: 'Al', Cr2O3: 'Cr', FeO: 'Fe', MnO: 'Mn', MgO: 'Mg', CaO: 'Ca', Na2O: 'Na',
  K2O: 'K', P2O5: 'P', SO3: 'S', Cl: 'Cl', Ni: 'Ni', Zn: 'Zn', Br: 'Br' };
export const TRACE = new Set(['Ni', 'Zn', 'Br']);
export const unit = (el) => (TRACE.has(el) ? 'ppm' : 'wt%');
export function fmtValue(el, v) {
  if (v == null || !Number.isFinite(v)) return '—';
  if (TRACE.has(el)) return Math.round(v).toLocaleString();
  return v >= 10 ? v.toFixed(1) : v.toFixed(2);
}

function svgEl(tag, attrs = {}, parent) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}
function svgText(parent, x, y, text, anchor = 'middle') {
  const t = svgEl('text', { x, y, 'text-anchor': anchor }, parent);
  t.textContent = text;
  return t;
}

/* ------------------------------------------------------------------ tooltip */
const tipEl = () => document.getElementById('tooltip');
export function showTip(fill, x, y) {
  const t = tipEl();
  t.replaceChildren();
  fill(t);
  t.style.display = 'block';
  const w = t.offsetWidth, h = t.offsetHeight;
  t.style.left = `${Math.min(x + 14, innerWidth - w - 8)}px`;
  t.style.top = `${Math.max(8, Math.min(y + 14, innerHeight - h - 8))}px`;
}
export function hideTip() { tipEl().style.display = 'none'; }
export function tipRow(parent, { color, value, label }) {
  const row = document.createElement('div');
  if (color) { const k = document.createElement('i'); k.className = 'tk'; k.style.background = color; row.append(k); }
  const b = document.createElement('b'); b.textContent = value; row.append(b);
  if (label) { const s = document.createElement('span'); s.className = 'dim'; s.textContent = ` ${label}`; row.append(s); }
  parent.append(row);
  return row;
}
const anchorOf = (node) => { const r = node.getBoundingClientRect(); return [r.left + r.width / 2, r.top]; };

/* ------------------------------------------------------------------ spider (composition vs typical Mars) */
const ratioLabel = (p) => (p >= 0 ? `${10 ** p}×` : `${(10 ** p).toFixed(-p)}×`).replace('.0×', '×');

export function spiderChart(box, { series, reference }) {
  box.replaceChildren();
  const W = Math.max(300, box.clientWidth || 380), H = 220, m = { l: 44, r: 10, t: 12, b: 24 };
  const els = ORDER.filter((e) => reference[e] > 0 && series.some((s) => s.chemistry[e] != null));
  if (!els.length) return;
  const ratio = (s, e) => { const v = s.chemistry[e]; return v != null && v > 0 ? Math.log10(v / reference[e]) : null; };
  let lo = -1, hi = 1;
  for (const s of series) for (const e of els) {
    const r = ratio(s, e);
    if (r != null) { lo = Math.min(lo, Math.floor(r)); hi = Math.max(hi, Math.ceil(r)); }
  }
  lo = Math.max(lo, -3); hi = Math.min(hi, 3);
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const x = (i) => m.l + (i / (els.length - 1)) * pw;
  const y = (r) => m.t + ((hi - Math.max(lo, Math.min(hi, r))) / (hi - lo)) * ph;
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `Element abundances relative to typical Mars for ${series.map((s) => s.label).join(' and ')}` });

  for (let p = lo; p <= hi; p++) {
    svgEl('line', { x1: m.l, x2: W - m.r, y1: y(p), y2: y(p), stroke: p === 0 ? token('--axis') : token('--grid'), 'stroke-width': 1 }, svg);
    svgText(svg, m.l - 6, y(p) + 3, ratioLabel(p), 'end');
  }
  svgText(svg, W - m.r, y(0) - 5, 'typical Mars', 'end');
  els.forEach((e, i) => svgText(svg, x(i), H - 7, SYMBOL[e]));

  for (const s of series) {
    let d = '', pen = false;
    els.forEach((e, i) => {
      const r = ratio(s, e);
      if (r == null) { pen = false; return; }
      d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(r).toFixed(1)}`;
      pen = true;
    });
    svgEl('path', { d, fill: 'none', stroke: s.color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
  }
  for (const s of series) els.forEach((e, i) => {
    const r = ratio(s, e);
    if (r != null) svgEl('circle', { cx: x(i), cy: y(r), r: 4, fill: s.color, stroke: token('--surface'), 'stroke-width': 2 }, svg);
  });

  // hover / focus: one column per element (hit area wider than the mark)
  const guide = svgEl('line', { y1: m.t, y2: H - m.b, stroke: token('--text-2'), 'stroke-width': 1, opacity: 0 }, svg);
  const colW = pw / (els.length - 1);
  els.forEach((e, i) => {
    const hit = svgEl('rect', { x: x(i) - colW / 2, y: 0, width: colW, height: H, fill: 'transparent', tabindex: 0,
      'aria-label': `${e}: ${series.map((s) => `${s.label} ${fmtValue(e, s.chemistry[e])} ${unit(e)}`).join(', ')}` }, svg);
    const show = (cx, cy) => {
      guide.setAttribute('x1', x(i)); guide.setAttribute('x2', x(i)); guide.setAttribute('opacity', 0.45);
      showTip((t) => {
        const h = document.createElement('div'); h.className = 'dim'; h.textContent = `${e} (${unit(e)})`; t.append(h);
        for (const s of series) tipRow(t, { color: s.color, value: fmtValue(e, s.chemistry[e]), label: s.label });
        tipRow(t, { value: fmtValue(e, reference[e]), label: 'typical Mars' });
      }, cx, cy);
    };
    const hide = () => { guide.setAttribute('opacity', 0); hideTip(); };
    hit.addEventListener('pointermove', (ev) => show(ev.clientX, ev.clientY));
    hit.addEventListener('pointerleave', hide);
    hit.addEventListener('focus', () => show(...anchorOf(hit)));
    hit.addEventListener('blur', hide);
  });
  box.append(svg);
}

/* ------------------------------------------------------------------ APXS spectrum */
const countLabel = (p) => (p === 0 ? '0' : p >= 6 ? `${10 ** (p - 6)}M` : p >= 3 ? `${10 ** (p - 3)}K` : `${10 ** p}`);

export function spectrumChart(box, spec, color) {
  box.replaceChildren();
  const W = Math.max(300, box.clientWidth || 380), H = 214, m = { l: 44, r: 10, t: 42, b: 24 };
  const E = spec.energy_kev, C = spec.counts;
  const xmin = 0.7, xmax = Math.min(14, E[E.length - 1]);
  const idx = [];
  for (let i = 0; i < E.length; i++) if (E[i] >= xmin && E[i] <= xmax) idx.push(i);
  if (idx.length < 10) return;
  const ymax = Math.max(1, Math.ceil(Math.log10(Math.max(...idx.map((i) => C[i])) + 1)));
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const x = (e) => m.l + ((e - xmin) / (xmax - xmin)) * pw;
  const y = (c) => m.t + (1 - Math.log10(Math.max(c, 0) + 1) / ymax) * ph;
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'APXS X-ray spectrum, counts by energy (log scale)' });

  for (let p = 0; p <= ymax; p++) {
    svgEl('line', { x1: m.l, x2: W - m.r, y1: y(10 ** p - 1), y2: y(10 ** p - 1), stroke: p === 0 ? token('--axis') : token('--grid'), 'stroke-width': 1 }, svg);
    svgText(svg, m.l - 6, y(10 ** p - 1) + 3, countLabel(p), 'end');
  }
  for (let k = 2; k <= xmax; k += 2) svgText(svg, x(k), H - 7, `${k} keV`);

  // element emission lines; labels take the first of three rows where they fit (else the tooltip names them)
  const rowEnd = [-1e9, -1e9, -1e9];
  Object.entries(spec.lines || {}).sort((a, b) => a[1] - b[1]).forEach(([el, e]) => {
    if (e < xmin || e > xmax) return;
    const px = x(e), wHalf = el.length * 3.4 + 2;
    svgEl('line', { x1: px, x2: px, y1: m.t - 2, y2: H - m.b, stroke: token('--axis'), 'stroke-width': 1 }, svg);
    const r = rowEnd.findIndex((end) => px - wHalf >= end + 3);
    if (r < 0) return;
    rowEnd[r] = px + wHalf;
    svgText(svg, px, m.t - 6 - r * 11, el);
  });

  let line = '';
  idx.forEach((i, k) => { line += `${k ? 'L' : 'M'}${x(E[i]).toFixed(1)},${y(C[i]).toFixed(1)}`; });
  const base = y(0).toFixed(1);
  svgEl('path', { d: `${line}L${x(E[idx[idx.length - 1]]).toFixed(1)},${base}L${x(E[idx[0]]).toFixed(1)},${base}Z`, fill: color, opacity: 0.1 }, svg);
  svgEl('path', { d: line, fill: 'none', stroke: color, 'stroke-width': 2, 'stroke-linejoin': 'round' }, svg);

  // crosshair snapping to the nearest channel
  const guide = svgEl('line', { y1: m.t, y2: H - m.b, stroke: token('--text-2'), 'stroke-width': 1, opacity: 0 }, svg);
  const dot = svgEl('circle', { r: 4, fill: color, stroke: token('--surface'), 'stroke-width': 2, opacity: 0 }, svg);
  const hit = svgEl('rect', { x: m.l, y: 0, width: pw, height: H, fill: 'transparent' }, svg);
  const lines = Object.entries(spec.lines || {});
  hit.addEventListener('pointermove', (ev) => {
    const r = svg.getBoundingClientRect();
    const e = xmin + (((ev.clientX - r.left) * (W / r.width) - m.l) / pw) * (xmax - xmin);
    let best = idx[0];
    for (const i of idx) if (Math.abs(E[i] - e) < Math.abs(E[best] - e)) best = i;
    const px = x(E[best]);
    guide.setAttribute('x1', px); guide.setAttribute('x2', px); guide.setAttribute('opacity', 0.45);
    dot.setAttribute('cx', px); dot.setAttribute('cy', y(C[best])); dot.setAttribute('opacity', 1);
    const near = lines.filter(([, le]) => Math.abs(le - E[best]) < 0.09).map(([el, le]) => `${el} Kα ${le.toFixed(2)} keV`);
    showTip((t) => {
      tipRow(t, { color, value: `${Math.round(C[best]).toLocaleString()} counts`, label: `at ${E[best].toFixed(2)} keV` });
      if (near.length) { const d = document.createElement('div'); d.className = 'dim'; d.textContent = `near ${near.join(', ')}`; t.append(d); }
    }, ev.clientX, ev.clientY);
  });
  hit.addEventListener('pointerleave', () => { guide.setAttribute('opacity', 0); dot.setAttribute('opacity', 0); hideTip(); });
  box.append(svg);
}
