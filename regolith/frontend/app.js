import { ORDER, TRACE, fmtValue, hideTip, labChart, profileChart, spectrumChart, spiderChart, unit } from './charts.js';

const $ = (id) => document.getElementById(id);
const API = '/api';
const R_M_PER_DEG = 59158;   // metres per degree on Mars
const S = {
  meta: null, classes: new Map(), views: [], slots: ['#3987e5', '#d95926', '#199e70'], other: '#898781',
  view: 'unusual', summary: [], query: null, result: null, detail: null, spectrum: null,
  simulated: null, globeReady: false, outbox: [], deposits: null, depView: 'unusual',
};
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/* ====================================================================== helpers */
async function api(path, opts) {
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : msg; } catch { /* keep status text */ }
    throw new Error(msg);
  }
  return res.json();
}
const postJson = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const h = (tag, props = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') n.className = v;
    else if (k === 'style') for (const [sk, sv] of Object.entries(v)) n.style.setProperty(sk.startsWith('--') ? sk : sk.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`), sv);
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) n.setAttribute(k, v === true ? '' : v);
  }
  n.append(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false));
  return n;
};
const dot = (color) => h('i', { class: 'dot', style: { background: color } });
const fmtDist = (m) => (m == null ? '' : m < 1000 ? `${Math.round(m)} m` : m < 100000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m / 1000).toLocaleString()} km`);
const fmtLL = (lat, lon) => { const L = ((lon + 180) % 360 + 360) % 360 - 180; return `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? 'N' : 'S'}, ${Math.abs(L).toFixed(4)}°${L >= 0 ? 'E' : 'W'}`; };
const gauss = () => { let u = 0, v = 0; while (!u) u = Math.random(); while (!v) v = Math.random(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
const classLabel = (cid) => S.classes.get(cid)?.label || cid;
/* Deposits tab overview: one colour per deposit family (dataviz slots 1-5, dark mode; validated adjacent:
   CVD ΔE ≥ 8.4, normal-vision ≥ 19.3, all ≥ 3:1 contrast). Always shown with the family name. */
const FAMILY_COLORS = {};   // family id -> colour, from the backend's overview view (the same colours as the map)
const familyOf = (cid) => S.classes.get(cid)?.family || null;
const familyLabel = (fam) => S.views.find((v) => v.id === fam)?.label || 'Typical';
const familyColor = (cid) => FAMILY_COLORS[familyOf(cid)] || S.other;
function classColor(cid, viewId = S.view) {
  const v = S.views.find((x) => x.id === viewId);
  const g = v ? v.groups.findIndex((grp) => grp.classes.includes(cid)) : -1;
  return g >= 0 ? S.slots[g] : S.other;
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

/* ====================================================================== globe messaging */
const globe = $('globe');
function toGlobe(msg) {
  if (S.globeReady) globe.contentWindow.postMessage(msg, location.origin);
  else S.outbox.push(msg);
}
window.addEventListener('message', (e) => {
  if (e.origin !== location.origin || e.source !== globe.contentWindow || !e.data) return;
  const m = e.data;
  if (m.type === 'rm:ready') {
    S.globeReady = true;
    S.outbox.splice(0).forEach(toGlobe);
  } else if (m.type === 'rm:rock') {
    if (m.id) showDetail(m.id, { fromMap: true });
  } else if (m.type === 'rm:prospects') {
    $('m-prosp').setAttribute('aria-pressed', String(!!m.on));
  } else if (m.type === 'rm:position') {
    setPosition(m.lat, m.lon, false);
    setPicking(false);
  } else if (m.type === 'rm:element') {
    if (m.key) $('m-prosp').setAttribute('aria-pressed', 'false');
    $('m-elem').value = m.key || '';
    $('m-pct').value = 100 - (m.pct || 75);
    syncElementTools();
  } else if (m.type === 'rm:view') {
    S.view = m.view;
    if (S.result) renderResult(S.result);
    if (S.detail) renderClassChip(S.detail);
  }
});
globe.addEventListener('load', () => {
  // the globe announces itself when its APXS layer is ready; ask again in case we missed it
  setTimeout(() => { if (!S.globeReady) globe.contentWindow.postMessage({ type: 'rm:ping' }, location.origin); }, 3000);
});

/* ====================================================================== element map tools */
async function buildElementTools() {
  try {
    const { elements } = await api('/elements');
    const opt = (e) => h('option', { value: e.key }, `${e.label} (${e.key})`);
    $('m-elem').replaceChildren(h('option', { value: '' }, 'Off'),
      h('optgroup', { label: 'Orbit (Mars Odyssey GRS) + rocks' }, ...elements.filter((e) => e.grs).map(opt)),
      h('optgroup', { label: 'Rocks (APXS) only' }, ...elements.filter((e) => !e.grs).map(opt)));
  } catch { /* element maps unavailable */ }
}
function syncElementTools() {
  $('m-pct-wrap').hidden = !$('m-elem').value;
  $('m-pct-val').textContent = `${$('m-pct').value}%`;
}
function sendElement() {
  syncElementTools();
  toGlobe({ type: 'rm:element', key: $('m-elem').value || null, pct: 100 - +$('m-pct').value });
}
$('m-elem').addEventListener('change', sendElement);
$('m-prosp').addEventListener('click', () => {
  const on = $('m-prosp').getAttribute('aria-pressed') !== 'true';
  $('m-prosp').setAttribute('aria-pressed', String(on));
  if (on) { $('m-elem').value = ''; syncElementTools(); }
  toGlobe({ type: 'rm:prospects', on });
});
$('m-pct').addEventListener('input', syncElementTools);
$('m-pct').addEventListener('change', sendElement);

/* ====================================================================== tabs */
const tabs = [...document.querySelectorAll('.tabs [role="tab"]')];
function selectTab(name) {
  for (const t of tabs) {
    const on = t.dataset.tab === name;
    t.setAttribute('aria-selected', on);
    t.tabIndex = on ? 0 : -1;
    $(`tab-${t.dataset.tab}`).hidden = !on;
  }
  toGlobe({ type: 'rm:visible', on: name === 'map' });         // the globe stops rendering while hidden
  if (name === 'deposits') openDeposits();
  if (name === 'data') openData();
  if (name === 'spectrum') openLab();
}
tabs.forEach((t, i) => {
  t.addEventListener('click', () => selectTab(t.dataset.tab));
  t.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    next.focus();
    selectTab(next.dataset.tab);
  });
});

/* ====================================================================== startup */
async function boot() {
  try {
    const [health, meta, list] = await Promise.all([api('/health'), api('/meta'), api('/rocks')]);
    S.meta = meta;
    S.views = meta.views || [];
    applyRanges(meta.ranges);
    S.slots = meta.slot_colors || S.slots;
    S.views.slice(1).forEach((v, i) => { FAMILY_COLORS[v.id] = S.slots[i]; });
    S.other = meta.other_color || S.other;
    (meta.classes || []).forEach((c) => S.classes.set(c.id, c));
    S.summary = list.rocks;
    renderStats(meta);
    buildSimulator();
    buildElementTools();
    onChemInput();
    const rid = new URLSearchParams(location.search).get('rock');
    if (rid) showDetail(rid);
  } catch (e) {
    $('status').className = 'status bad';
    $('status').hidden = false;
    $('status').lastElementChild.textContent = `backend offline (${e.message})`;
  }
}

function renderStats(meta) {
  const sites = meta.sites || {};
  const stat = (value, label) => h('div', { class: 'stat' }, h('b', {}, value), h('span', {}, label));
  $('stats').replaceChildren(
    stat(meta.count.toLocaleString(), 'APXS measurements'),
    stat(String(Object.keys(sites).length), 'rovers'),
    stat(meta.deposit_sites.toLocaleString(), 'deposit sites'),
    stat(String(meta.earth_refs), 'CSA Earth references'),
  );
}

/* ====================================================================== field reading form */
const grid = $('chem-grid');
/* Each element: a slider over the range actually measured by APXS (square-root scale, so the common low values
   get fine control and rare extremes still fit), a tick at typical Mars (the median), and an exact-value box.
   An empty box means "not measured"; a reading needs only 3 elements. */
const SL_STEPS = 1000;
const sliders = new Map();
const niceMax = (v) => { const m = 10 ** Math.floor(Math.log10(v)), f = v / m; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * m; };
const fmtChem = (el, v) => (TRACE.has(el) ? String(Math.round(v)) : v < 10 ? v.toFixed(2) : v.toFixed(1));
const posOf = (el, v) => Math.round(Math.sqrt(Math.min(1, Math.max(0, v / sliders.get(el).max))) * SL_STEPS);
const valOf = (el, p) => { const v = sliders.get(el).max * (p / SL_STEPS) ** 2; return TRACE.has(el) ? Math.round(v) : Math.round(v * 100) / 100; };
const inputs = ORDER.map((el) => {
  const input = h('input', { type: 'number', step: 'any', min: '0', inputmode: 'decimal', 'data-el': el, placeholder: '–',
    'aria-label': `${el} in ${unit(el)}` });
  const range = h('input', { type: 'range', min: '0', max: String(SL_STEPS), step: '1', value: '0', 'aria-label': `${el} slider` });
  const tick = h('i', { class: 'sl-tick', title: 'Typical Mars (median of every APXS measurement)' });
  const row = h('div', { class: 'sl unset' },
    h('div', { class: 'sl-h' }, h('b', {}, el), h('span', { class: 'sl-v' }, input, h('small', {}, unit(el)))),
    h('div', { class: 'sl-track' }, range, tick));
  sliders.set(el, { input, range, tick, row, max: TRACE.has(el) ? 10000 : 100 });
  let dragging = false;
  range.addEventListener('input', () => {
    const v = valOf(el, +range.value);
    input.value = v > 0 ? fmtChem(el, v) : '0';
    dragging = true;                                          // keep the thumb where the finger is, not where rounding puts it
    input.dispatchEvent(new Event('input'));
    dragging = false;
  });
  input.addEventListener('input', () => syncSlider(el, !dragging));
  grid.append(row);
  return input;
});
function syncSlider(el, fromBox = false) {
  const s = sliders.get(el), raw = s.input.value.trim(), set = raw !== '' && Number.isFinite(+raw) && +raw >= 0;
  s.row.classList.toggle('unset', !set);
  if (fromBox || !set) s.range.value = set ? posOf(el, +raw) : 0;
  s.range.style.setProperty('--fill', `${(+s.range.value / SL_STEPS) * 100}%`);
  s.range.setAttribute('aria-valuetext', set ? `${raw} ${unit(el)}` : 'not measured');
}
function applyRanges(ranges) {
  for (const [el, s] of sliders) {
    const r = ranges?.[el];
    if (!r) continue;
    s.max = niceMax(r.max * 1.02);
    s.tick.style.left = `${Math.sqrt(r.median / s.max) * 100}%`;
    s.tick.title = `Typical Mars: ${fmtChem(el, r.median)} ${unit(el)} (median of ${r.n.toLocaleString()} APXS measurements; highest ${fmtChem(el, r.max)})`;
    syncSlider(el, true);
  }
}
function readChem() {
  const chem = {};
  for (const i of inputs) {
    const v = i.value.trim();
    if (v !== '' && Number.isFinite(+v) && +v >= 0) chem[i.dataset.el] = +v;
  }
  return chem;
}
function writeChem(chem, simulated) {
  for (const i of inputs) {
    const v = chem[i.dataset.el];
    i.value = v == null ? '' : TRACE.has(i.dataset.el) ? String(Math.round(v)) : v.toFixed(2);
    i.classList.toggle('sim', !!simulated && v != null);
    sliders.get(i.dataset.el).row.classList.toggle('sim', !!simulated && v != null);
    syncSlider(i.dataset.el, true);
  }
  onChemInput();
}

const liveClassify = debounce(async () => {
  const chem = readChem();
  const box = $('live-class');
  if (Object.keys(chem).length < 3) {
    box.replaceChildren(h('span', { class: 'note', style: { margin: 0 } }, 'Set at least 3 elements.'));
    return;
  }
  // APXS oxide totals are normalised to about 100 wt% (ppm traces are tiny), so a much larger sum is a typo
  const total = Object.entries(chem).reduce((a, [el, v]) => a + (TRACE.has(el) ? v / 1e4 : v), 0);
  const warn = total > 105 ? h('span', { class: 'sum-warn' }, `Oxides add up to ${Math.round(total)} wt%: APXS readings total about 100 wt%, so check the values.`) : '';
  try {
    const c = await postJson('/classify', { chemistry: chem });
    box.replaceChildren(h('span', {}, 'Looks like'), h('span', { class: 'chip' }, dot(classColor(c.class)), c.class_info.label),
      h('span', { class: 'reason' }, c.reason), warn);
  } catch (e) {
    box.replaceChildren(h('span', { class: 'note', style: { margin: 0 } }, e.message));
  }
}, 250);
function onChemInput() {
  const n = Object.keys(readChem()).length;
  $('match-btn').disabled = n < 3 || !S.meta;
  liveClassify();
}
inputs.forEach((i) => i.addEventListener('input', () => {
  i.classList.remove('sim');
  sliders.get(i.dataset.el).row.classList.remove('sim');
  if (S.simulated) { S.simulated = null; $('sim-note').replaceChildren(); }
  onChemInput();
}));

/* position */
function getPos() {
  const lat = parseFloat($('lat').value), lon = parseFloat($('lon').value);
  return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 360 ? { lat, lon } : null;
}
function setPosition(lat, lon, tellGlobe = true) {
  $('lat').value = lat.toFixed(4);                             // 0.0001 deg = 6 m on Mars, finer than any rover fix
  $('lon').value = (((lon + 180) % 360 + 360) % 360 - 180).toFixed(4);
  if (tellGlobe) toGlobe({ type: 'rm:set-position', lat, lon });
  evaStartNote();
}
['lat', 'lon'].forEach((id) => $(id).addEventListener('change', () => { const p = getPos(); if (p) toGlobe({ type: 'rm:set-position', ...p }); }));
function setPicking(on) {
  $('pick-btn').classList.toggle('on', on);
  $('map-hint').hidden = !on;
  if (on) { selectTab('map'); toGlobe({ type: 'rm:pick-position' }); }
}
$('pick-btn').addEventListener('click', () => setPicking(!$('pick-btn').classList.contains('on')));

/* simulate a field reading from a real measurement + its instrument error bars */
function buildSimulator() {
  const sel = $('sim-class');
  sel.replaceChildren(h('option', { value: '' }, 'Any rock type'));
  for (const v of S.views.filter((x) => x.id !== 'unusual')) {
    const og = h('optgroup', { label: v.label });
    v.groups.flatMap((g) => g.classes).forEach((cid) => {
      const c = S.classes.get(cid);
      if (c?.count) og.append(h('option', { value: cid }, `${c.label} (${c.count})`));
    });
    sel.append(og);
  }
  const og = h('optgroup', { label: 'Typical Mars' });
  ['basaltic', 'basaltic_soil'].forEach((cid) => { const c = S.classes.get(cid); if (c) og.append(h('option', { value: cid }, `${c.label} (${c.count})`)); });
  sel.append(og);
}
$('sim-btn').addEventListener('click', async () => {
  const cls = $('sim-class').value;
  const pool = S.summary.filter((r) => !cls || r.deposit === cls);
  if (!pool.length) return;
  const pick = pool[Math.floor(Math.random() * pool.length)];
  try {
    const rock = await api(`/rocks/${encodeURIComponent(pick.id)}`);
    const chem = {};
    for (const [el, v] of Object.entries(rock.chemistry)) {
      const err = rock.errors?.[el] ?? Math.max(0.03 * v, TRACE.has(el) ? 10 : 0.02);
      chem[el] = Math.max(0, v + gauss() * err);
    }
    writeChem(chem, true);
    const d = 100 + Math.random() * 300, a = Math.random() * 2 * Math.PI;
    const lat = rock.lat + (d * Math.cos(a)) / R_M_PER_DEG;
    const lon = rock.lon + (d * Math.sin(a)) / (R_M_PER_DEG * Math.cos((rock.lat * Math.PI) / 180));
    setPosition(lat, lon);
    toGlobe({ type: 'rm:fly', lat, lon, alt_km: 5 });
    S.simulated = rock;
    $('sim-note').replaceChildren(h('div', { class: 'sim-note' },
      'Simulated from ', h('b', {}, rock.name), ` (${rock.rover}, sol ${rock.sol}) with instrument noise. You are ${Math.round(d)} m away.`));
  } catch (e) {
    $('sim-note').replaceChildren(h('div', { class: 'sim-note' }, `Could not simulate: ${e.message}`));
  }
});

$('clear-btn').addEventListener('click', () => {
  writeChem({}, false);
  S.simulated = null;
  $('sim-note').replaceChildren();
  $('card-result').hidden = true;
  clearRoute();
  S.result = null;
  S.query = null;
  toGlobe({ type: 'rm:clear' });
});

/* field photo: stored with the notes (identification itself uses chemistry) */
$('photo-input').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await api('/photos', { method: 'POST', body: fd });
    $('photo-note').replaceChildren(h('a', { href: res.url, target: '_blank', rel: 'noopener' }, 'Field photo saved'),
      '. Identification uses the APXS chemistry.');
  } catch (err) {
    $('photo-note').textContent = `Photo upload failed: ${err.message}`;
  }
});

/* ====================================================================== match */
$('match-btn').addEventListener('click', runMatch);
async function runMatch() {
  const chem = readChem();
  const btn = $('match-btn');
  btn.disabled = true;
  btn.textContent = 'Matching…';
  try {
    const res = await postJson('/match', { chemistry: chem, top_k: 6, ...(getPos() || {}) });
    S.query = chem;
    S.result = res;
    renderResult(res);
    const ids = res.matches.map((m) => m.id);
    toGlobe({ type: 'rm:highlight', ids, select: ids[0] || null });
    if (ids[0]) {
      toGlobe({ type: 'rm:select', id: ids[0], fly: true });
      showDetail(ids[0], { fromMap: true });
    }
    selectTab('map');
  } catch (e) {
    $('card-result').hidden = false;
    $('verdict').replaceChildren(h('div', { class: 'note' }, `Match failed: ${e.message}`));
  } finally {
    btn.textContent = 'Find match';
    btn.disabled = Object.keys(readChem()).length < 3;
  }
}

// Line icons (Lucide, ISC licence) - stroke uses currentColor
const ICON = {
  check: '<path d="M20 6 9 17l-5-5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M4 16V5a1 1 0 0 1 1-1h11"/>',
  pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  ext: '<path d="M7 7h10v10"/><path d="M7 17 17 7"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 7.5h.01"/>',
  chev: '<path d="m9 6 6 6-6 6"/>',
  flask: '<path d="M9 3h6"/><path d="M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3"/>',
  route: '<circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M8 19h7.5a3.5 3.5 0 0 0 0-7h-7a3.5 3.5 0 0 1 0-7H16"/>',
};
function icon(name, cls = 'ic') {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('class', cls); s.setAttribute('aria-hidden', 'true');
  s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '2');
  s.setAttribute('stroke-linecap', 'round'); s.setAttribute('stroke-linejoin', 'round');
  s.innerHTML = ICON[name];
  return s;
}
const VERDICT = {
  SAMPLE: { cls: 'v-sample', icon: 'check', title: 'Collect a sample' },
  MAYBE: { cls: 'v-maybe', icon: 'search', title: 'Worth a closer look' },
  DUPLICATE: { cls: 'v-duplicate', icon: 'copy', title: 'Already well sampled' },
};
function renderResult(res) {
  $('card-result').hidden = false;
  const v = VERDICT[res.verdict.label] || VERDICT.MAYBE;
  $('verdict').replaceChildren(h('div', { class: `verdict ${v.cls}` },
    h('span', { class: 'v-icon', 'aria-hidden': 'true' }, icon(v.icon)),
    h('div', {}, h('b', {}, `${res.verdict.label} · ${v.title}`), h('p', {}, res.verdict.reason))));

  const q = res.query;
  const fact = (label, ...value) => h('div', { class: 'fact' }, h('span', {}, label), h('span', {}, ...value));
  const facts = [
    fact('Deposit type', h('span', { class: 'chip' }, dot(classColor(q.class)), q.class_info.label), info(`Classified by ${q.reason}.`)),
    fact('Rarity', `${res.stats.class_count.toLocaleString()} of ${res.stats.total.toLocaleString()} measurements`),
  ];
  if (res.earth_ref) {
    const e = res.earth_ref;
    const src = 'CSA lab standard measured by the flight APXS';
    facts.push(fact('Earth analogue', e.similarity >= 20 ? `${e.name}, ${e.kind.split(' (')[0].toLowerCase()} (${e.similarity}%)` : 'None close', info(
      `Closest of the ${S.meta.earth_refs} Earth reference rocks measured by the flight APXS before launch (CSA): ${e.name}, ${e.similarity}% similar.`)));
  }
  if (res.nearest_same_class) {
    const n = res.nearest_same_class;
    facts.push(fact('Nearest same type', h('a', { href: '#', onclick: (e) => { e.preventDefault(); showDetail(n.id); } }, n.name),
      `, ${fmtDist(n.distance_m)} away`));
  }
  $('facts').replaceChildren(...facts);
  const insights = [];
  if (q.context?.why || q.context?.drivers?.length) {
    insights.push(section('Why it looks like this', '', { open: true, help: q.context.caveat }, h('div', { class: 'why' }, ...whyBlock(q.context, false))));
  }
  insights.push(predictionsBlock(q));
  $('insights').replaceChildren(...insights);

  $('matches').replaceChildren(...res.matches.map((m, i) => {
    const li = h('li', { class: 'match', tabindex: 0, 'data-id': m.id, 'aria-label': `${m.name}, ${m.similarity}% similar` },
      h('div', { class: 'm-top' }, h('span', { class: 'rank' }, String(i + 1)), h('span', { class: 'm-name' }, m.name), h('span', { class: 'm-sim' }, `${m.similarity}%`)),
      h('div', { class: 'meter', 'aria-hidden': 'true' }, h('i', { style: { width: `${m.similarity}%` } })),
      h('div', { class: 'm-sub' }, dot(classColor(m.deposit)), `${classLabel(m.deposit)} · ${m.rover}, sol ${m.sol}${m.distance_m != null ? ` · ${fmtDist(m.distance_m)}` : ''}`));
    const open = () => { showDetail(m.id); };
    li.addEventListener('click', open);
    li.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    return li;
  }));
  markActive();
}
function markActive() {
  document.querySelectorAll('.match').forEach((li) => li.classList.toggle('active', li.dataset.id === S.detail?.id));
}

/* ====================================================================== rock detail */
async function showDetail(id, { fromMap = false } = {}) {
  let d;
  try {
    d = await api(`/rocks/${encodeURIComponent(id)}`);
  } catch (e) {
    $('card-detail').hidden = false;
    $('d-title').textContent = 'Rock detail';
    $('d-meta').textContent = `Could not load ${id}: ${e.message}`;
    return;
  }
  S.detail = d;
  S.spectrum = null;
  if (!$('card-eva').hidden && !fromMap) setMode('identify');
  if (!fromMap) toGlobe({ type: 'rm:select', id, fly: true });
  $('card-detail').hidden = false;
  $('d-title').textContent = d.name;
  const bits = [`${d.rover} · sol ${d.sol}`, `${d.sample_type}${d.preparation ? ` (${d.preparation})` : ''}`, fmtLL(d.lat, d.lon)];
  if (d.elev_m != null) bits.push(`${d.elev_m.toLocaleString()} m elevation`);
  if (d.traverse_km != null) bits.push(`${d.traverse_km} km into the traverse`);
  $('d-meta').textContent = bits.join(' · ');
  renderClassChip(d);
  renderComposition(d.chemistry);
  $('d-why').replaceChildren(...whyBlock(d.context || {}), d.minerals ? mineralsBlock(d.minerals, true) : '');
  markActive();
  renderSpider();
  renderValues();
  renderProvenance(d);
  loadPhotos(d);
  loadSpectrum(d);
  $('d-back').hidden = $('card-result').hidden;
  $('card-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });   // the card opens below the fold otherwise
}
$('d-back').addEventListener('click', () => $('card-result').scrollIntoView({ behavior: 'smooth', block: 'start' }));

function renderClassChip(d) {
  const kids = [h('span', { class: 'rover-badge' }, h('i', { style: { background: ROVER_COLOR[d.rover] } }), d.rover),
    h('span', { class: 'chip' }, dot(classColor(d.deposit)), d.class.label),
    h('span', { class: 'chip' }, `data quality: ${d.quality.tier}`)];
  if (d.site) kids.push(h('span', { class: 'chip' }, `deposit site · ${d.site.count} measurement${d.site.count === 1 ? '' : 's'}`));
  if (d.note) {
    const sulfur = /S assumed as SO3/i.test(d.note);
    kids.push(h('span', { class: 'chip note-chip', title: 'Note from the NASA PDS concentration table' },
      `NASA note: ${d.note}${sulfur ? '. APXS reports all sulfur as SO3; with so little Ca or Mg this points to elemental sulfur' : ''}`));
  }
  kids.push(h('div', { class: 'reason', style: { width: '100%' } }, `Classified by: ${d.deposit_reason}.`));
  $('d-class').replaceChildren(...kids);
}

function chartSeries() {
  const d = S.detail;
  const series = [];
  if (S.query) series.push({ label: 'Your reading', color: css('--series-1'), chemistry: S.query });
  series.push({ label: d.name, color: S.query ? css('--series-2') : css('--series-1'), chemistry: d.chemistry });
  return series;
}
function renderSpider() {
  if (!S.detail) return;
  const series = chartSeries();
  $('spider-title').textContent = S.query ? 'Your reading vs this rock (relative to typical Mars)' : 'Chemistry vs typical Mars';
  $('spider-legend').replaceChildren(...(series.length > 1
    ? series.map((s) => h('span', {}, h('i', { class: 'key', style: { background: s.color } }), s.label)) : []));
  spiderChart($('spider'), { series, reference: S.meta.reference.chemistry });
}
function renderValues() {
  const series = chartSeries(), ref = S.meta.reference.chemistry;
  const head = h('tr', {}, h('th', {}, 'Element'), ...series.map((s) => h('th', {}, s.label)), h('th', {}, 'Typical Mars'), h('th', {}, 'Unit'));
  const rows = ORDER.filter((el) => series.some((s) => s.chemistry[el] != null)).map((el) => {
    const err = S.detail.errors?.[el];
    return h('tr', {}, h('td', {}, el),
      ...series.map((s, i) => h('td', {}, fmtValue(el, s.chemistry[el]) + (i === series.length - 1 && err != null ? ` ± ${fmtValue(el, err)}` : ''))),
      h('td', {}, fmtValue(el, ref[el])), h('td', {}, unit(el)));
  });
  $('chem-table').replaceChildren(h('thead', {}, head), h('tbody', {}, ...rows));
}

const ROVER_COLOR = { Curiosity: '#ff6a3d', Spirit: '#4fc3f7', Opportunity: '#9ccc65' };
async function loadPhotos(d) {
  const box = $('d-photos');
  box.replaceChildren(h('div', { class: 'hero-main' }, h('span', { class: 'tag' }, 'Loading rover close-ups…')));
  try {
    const p = await api(`/rocks/${encodeURIComponent(d.id)}/photos`);
    if (S.detail?.id !== d.id) return;
    if (!p.images?.length) {
      box.replaceChildren(h('p', { class: 'note' }, p.error ? 'Photo service unavailable right now. ' : `No close-up photos found around sol ${d.sol}. `,
        p.source_page ? h('a', { href: p.source_page, target: '_blank', rel: 'noopener' }, 'Browse NASA images') : null));
      return;
    }
    const imgs = p.images.slice(0, 8);
    const main = h('a', { class: 'hero-main', target: '_blank', rel: 'noopener' });
    const show = (im, btn) => {
      main.replaceChildren(h('img', { src: im.url, alt: `${im.title} (sol ${im.sol})` }),
        h('span', { class: 'tag' }, `${d.rover} · sol ${im.sol} · ${p.credit}`),
        h('span', { class: 'open' }, im.page ? 'Open on NASA' : 'Full size', icon('ext', 'ic sm')));
      main.href = im.page || im.url;
      thumbs.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', b === btn));
    };
    const thumbs = h('div', { class: 'thumbs' });
    imgs.forEach((im, i) => {
      const b = h('button', { type: 'button', 'aria-label': `Photo ${i + 1}`, 'aria-pressed': i === 0 }, h('img', { src: im.thumb, alt: '', loading: 'lazy' }));
      b.addEventListener('click', () => show(im, b));
      thumbs.append(b);
    });
    box.replaceChildren(main, imgs.length > 1 ? thumbs : '');
    show(imgs[0], thumbs.firstElementChild);
  } catch (e) {
    box.replaceChildren(h('p', { class: 'note' }, `Photos unavailable: ${e.message}`));
  }
}

/* composition: one whole split into the major oxides (tall segmented bar, <= 6 parts) */
const SEG_PARTS = [['SiO2', '#3987e5'], ['FeO', '#d95926'], ['SO3', '#199e70'], ['CaO', '#c98500'], ['MgO', '#d55181']];
function renderComposition(chem) {
  const total = ORDER.filter((e) => !TRACE.has(e)).reduce((a, e) => a + (chem[e] || 0), 0) || 1;
  const parts = SEG_PARTS.map(([el, color]) => ({ el, color, v: chem[el] || 0 }));
  parts.push({ el: 'Other', color: css('--muted'), v: Math.max(0, total - parts.reduce((a, p) => a + p.v, 0)) });
  const bar = $('d-segbar');
  bar.setAttribute('aria-label', parts.map((p) => `${p.el} ${(100 * p.v / total).toFixed(0)}%`).join(', '));
  bar.replaceChildren(...parts.filter((p) => p.v > 0).map((p) => {
    const pct = 100 * p.v / total;
    const label = `${p.el} ${pct.toFixed(0)}%`;
    return h('span', { class: pct * 3.6 < label.length * 7 + 12 ? 'dim' : '', style: { flex: `${p.v} 1 0`, background: p.color }, title: `${p.el}: ${fmtValue(p.el, p.v)} wt% (${pct.toFixed(1)}%)` }, label);
  }));
  $('d-seglegend').replaceChildren(...parts.map((p) => h('span', {}, h('i', { style: { background: p.color } }), `${p.el} ${p.el === 'Other' ? p.v.toFixed(1) : fmtValue(p.el, p.v)} wt%`)));
}

/* why: likely formation + element drivers + region + NASA links */
/* ====================================================================== data & methods tab */
const KIND_TITLE = {
  dataset: ['Datasets the results are computed from', 'Downloaded by fetch_data.py and built into the app\'s data files.'],
  imagery: ['Live imagery', 'Streamed from NASA while you use the map; nothing is computed from it.'],
  reference: ['Published NASA results', 'Used as constants or as the "why" links.'],
};
async function openData() {
  if (S.dataLoaded) return;
  const box = $('data-body');
  let src, val;
  try { [src, val] = await Promise.all([api('/sources'), api('/validation')]); }
  catch (e) { box.replaceChildren(h('p', { class: 'note' }, `Could not load: ${e.message}`)); return; }
  S.dataLoaded = true;
  const m = val.matching || {}, nb = val.nearby || {}, gr = val.ground || {};
  const n = (k) => src.sources.filter((s) => s.agency === k).length;
  const tile = (value, label, sub) => h('div', { class: 'tile' }, h('b', {}, value), h('span', {}, label), sub ? h('small', {}, sub) : '');
  const kids = [
    h('h2', { class: 'data-h' }, 'Only NASA and Canadian Space Agency data'),
    h('p', { class: 'lead' }, `Regolith is built from ${n('NASA')} NASA sources and the Canadian Space Agency's APXS open data. `,
      'Curiosity\'s APXS, the source of 1,768 of the 2,475 measurements, is Canada\'s contribution to that mission.'),
  ];
  for (const kind of ['dataset', 'imagery', 'reference']) {
    kids.push(h('h3', {}, KIND_TITLE[kind][0]), h('p', { class: 'hint' }, KIND_TITLE[kind][1]),
      h('div', { class: 'src-list' }, ...src.sources.filter((s) => s.kind === kind).map((s) => h('div', { class: 'src-row' },
        h('span', { class: `agency ${s.agency.toLowerCase()}` }, s.agency),
        h('div', {},
          h('a', { class: 'src-name', href: s.url, target: '_blank', rel: 'noopener' }, s.name, icon('ext', 'ic sm')),
          h('div', { class: 'src-prod' }, s.product),
          h('div', { class: 'src-use' }, h('b', {}, 'Used for: '), s.used_for),
          s.loaded ? h('div', { class: 'src-use' }, h('b', {}, 'Loaded: '), s.loaded) : '',
          h('div', { class: 'src-prov' }, `${s.provider} · ${s.licence}`))))));
  }
  kids.push(h('h2', { class: 'data-h' }, 'How well it works'),
    h('p', { class: 'lead' }, 'Every figure below is measured on data the method was not allowed to see. The tests run each time the dataset is built.'),
    h('div', { class: 'tiles' },
      tile(`${m.remeasure_top1_pct}%`, 'known rock found first', `in the top five ${m.remeasure_top5_pct}% of the time`),
      val.spectra ? tile(`${val.spectra.quarter_counts_found_pct}%`, 'spectrum matched to its rock', 'from a quarter of the counts') : '',
      tile(`${m.remeasure_same_type_pct}%`, 'deposit type right', 'for the closest match of a re-measured rock'),
      tile(`${nb.top1_pct}%`, 'new-stop forecast right', `always guessing basalt: ${nb.baseline_pct}%`),
      tile(`${nb.top3_pct}%`, 'right type in the top three', `${(nb.n || 0).toLocaleString()} held-out measurements`)),
    h('h3', {}, 'Matching and classification'),
    h('ul', { class: 'method' },
      h('li', {}, h('b', {}, 'Re-measurement test. '), `${m.n} measurements were "measured again" by adding noise the size of their own instrument error bars. `,
        `The original rock came back as the closest match ${m.remeasure_top1_pct}% of the time and within the top five ${m.remeasure_top5_pct}% of the time.`),
      h('li', {}, h('b', {}, 'Stable classes. '), `The noisy copy was given the same deposit type as the original ${m.classification_stable_pct}% of the time.`),
      h('li', {}, h('b', {}, 'Nearest other rock. '), `With a rock removed from the library, the closest remaining rock had the same deposit type ${m.nearest_other_same_type_pct}% of the time.`)),
    h('h3', {}, 'Forecast: what you will find within 1 km'),
    h('p', { class: 'hint' }, `Each measurement was hidden together with everything within ${nb.hold_m} m of it (the whole rover stop) and predicted from the rest. `,
      'The table checks the percentages themselves: when the forecast says a type has a given chance, how often does it turn up?'),
    h('table', { class: 'dep-table cal' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Forecast said'), h('th', { class: 'num' }, 'Average forecast'), h('th', { class: 'num' }, 'Actually happened'), h('th', { class: 'num' }, 'Predictions'))),
      h('tbody', {}, ...(nb.calibration || []).map((c) => h('tr', {},
        h('td', {}, `${c.range_pct[0]}–${c.range_pct[1]}%`), h('td', { class: 'num' }, `${c.predicted_pct}%`),
        h('td', { class: 'num' }, `${c.observed_pct}%`), h('td', { class: 'num' }, c.n.toLocaleString()))))));
  if (gr.sites?.length) {
    const ox = Object.keys(gr.sites[0].predicted);
    kids.push(h('h3', {}, 'Forecast: soil composition from orbit'),
      h('p', { class: 'hint' }, 'Odyssey element maps converted to oxides, against the median of each rover\'s own soil measurements (wt%).'),
      h('table', { class: 'dep-table cal' },
        h('thead', {}, h('tr', {}, h('th', {}, 'Site'), ...ox.flatMap((o) => [h('th', { class: 'num' }, `${o} orbit`), h('th', { class: 'num' }, 'rover')]))),
        h('tbody', {}, ...gr.sites.map((s) => h('tr', {}, h('td', {}, `${s.rover} (${s.n_soils} soils)`),
          ...ox.flatMap((o) => [h('td', { class: 'num' }, s.predicted[o].toFixed(2)), h('td', { class: 'num' }, s.measured[o].toFixed(2))]))),
          h('tr', { class: 'worst' }, h('td', {}, 'Largest difference'), ...ox.flatMap((o) => [h('td', { class: 'num', colspan: 2 }, `±${gr.error_pct[o]}%`)])))));
  }
  const sp = val.spectra, tr = val.terrain;
  if (sp) kids.push(h('h3', {}, 'Spectrum lab'),
    h('ul', { class: 'method' },
      h('li', {}, h('b', {}, 'Quick-look reading. '), `${sp.n} Curiosity spectra were re-counted with only a quarter of their counts (real Poisson noise). `,
        `The original rock was the closest spectrum ${sp.quarter_counts_found_pct}% of the time.`),
      h('li', {}, h('b', {}, 'New target. '), `With every spectrum from the same sol hidden, the closest remaining spectrum had the same deposit type ${sp.other_sol_same_type_pct}% of the time.`)));
  if (tr) kids.push(h('h3', {}, 'EVA planner terrain'),
    h('ul', { class: 'method' },
      h('li', {}, h('b', {}, 'Height scale. '), `NASA's HiRISE Gale DEM is served as 8-bit grey levels. Fitted to ${tr.n_waypoints.toLocaleString()} Curiosity waypoint elevations, `,
        `one grey level is ${tr.grey_step_m} m and the fit's typical error is ${tr.residual_sd_m} m (median ${tr.median_abs_m} m), about what rounding to whole grey levels alone gives.`),
      tr.curiosity_route ? h('li', {}, h('b', {}, 'Real route check. '), `Along the route Curiosity actually drove, this terrain model gives a median slope of ${tr.curiosity_route.median_slope_deg}°, `,
        `and ${tr.curiosity_route.under_15_pct}% of the route is under the planner's default 15° limit.`) : ''));
  kids.push(h('h3', {}, 'What Regolith does not claim'),
    h('ul', { class: 'method' },
      h('li', {}, 'APXS measures elements, not minerals. Deposit types and mineral amounts are readings of bulk chemistry, not identifications.'),
      h('li', {}, 'Orbital values are 600 km averages of roughly the top few tens of centimetres. A prospect zone marks where to look, not a confirmed deposit.'),
      h('li', {}, 'Rovers visited three sites and chose unusual targets, so local forecasts describe what was sampled, not a random sample of the ground.'),
      h('li', {}, 'Measurement positions are the rover\'s position for that sol, typically within about 100 m of the rock.')));
  box.replaceChildren(...kids);
}

/* ====================================================================== spectrum lab (CSA's APXS spectra) */
const LAB = { list: null, ids: new Map(), src: null, busy: false };
const labLabel = (s) => (s.kind === 'ref' ? `${s.name} · CSA lab standard` : `${s.name} · ${s.rover}, sol ${s.sol}`);
async function openLab() {
  if (LAB.list) return;
  try { LAB.list = (await api('/spectra')).spectra; }
  catch (e) { $('lab-body').replaceChildren(h('p', { class: 'note' }, `Could not load spectra: ${e.message}`)); return; }
  $('lab-list').replaceChildren(...LAB.list.map((s) => { LAB.ids.set(labLabel(s), s.id); return h('option', { value: labLabel(s) }); }));
  const first = LAB.list.find((s) => s.id === 'MSL-3907-Kythira') || LAB.list[0];
  $('lab-search').value = labLabel(first);
  runLab({ source_id: first.id });
}
async function runLab(src) {
  LAB.src = src;
  const keep = +$('lab-keep').value / 100;
  const body = src.csv ? { csv: src.csv } : { source_id: src.source_id, keep, exclude_self: $('lab-hide').checked };
  $('lab-body').classList.add('loading');
  let d;
  try { d = await postJson('/spectrum/match', body); }
  catch (e) { $('lab-body').classList.remove('loading'); $('lab-body').replaceChildren(h('p', { class: 'note' }, e.message)); return; }
  $('lab-body').classList.remove('loading');
  if (LAB.src !== src) return;
  const q = d.query, c1 = css('--series-1'), c2 = css('--series-2');
  const title = q ? (q.kind === 'ref' ? `${q.name}: ${q.description}` : `${q.name} · ${q.rover}, sol ${q.sol}`) : 'Your uploaded spectrum';
  const sub = `${d.total_counts.toLocaleString()} counts${q && d.keep < 1 ? ` · ${Math.round(d.keep * 100)}% counting time` : ''}`;
  const chart = h('div', { class: 'lab-chart' });
  const legend = h('div', { class: 'legend' }, h('span', {}, h('i', { class: 'key', style: { background: c1 } }), q ? 'This spectrum' : 'Uploaded spectrum'),
    d.best_counts ? h('span', {}, h('i', { class: 'key', style: { background: c2 } }), `Closest other: ${d.best_name}`) : '');
  const detected = d.peaks.filter((p) => p.detected);
  const matchRow = (m, i) => h('li', { class: 'lab-m', tabindex: 0, title: `Shape similarity ${m.cosine.toFixed(4)} (cosine of square-root counts)`,
    onclick: () => showDetail(m.id), onkeydown: (e) => { if (e.key === 'Enter') showDetail(m.id); } },
    h('span', { class: 'rank' }, String(i + 1)),
    h('span', { class: 'lab-mn' }, m.name, h('small', {}, `${m.rover}, sol ${m.sol}`)),
    h('span', { class: 'lab-mc' }, dot(familyColor(m.deposit)), classLabel(m.deposit)),
    h('span', { class: 'pval' }, `${m.similarity}%`));
  const sk = d.skill;
  $('lab-body').replaceChildren(
    h('div', { class: 'lab-title' }, h('b', {}, title), h('span', { class: 'note' }, sub)),
    legend, chart,
    h('div', { class: 'lab-detected' }, h('span', { class: 'note', style: { margin: 0 } }, 'Detected'), info('Element lines at least 5σ above the local continuum. Argon (italic) is from the Martian air.'),
      ...detected.map((p) => h('span', { class: `chip${p.air ? ' air' : ''}`, title: p.air ? 'Argon in the Martian air between the instrument and the rock' : `${p.sigma}σ above the continuum` }, p.el))),
    h('div', { class: 'lab-cols' },
      h('div', {}, h('h3', {}, 'Closest spectra on Mars', info('Compares spectrum shape (square-root counts), so it works whatever the counting time. Click a rock to open it.',
        sk ? ` In a hold-out test a quarter-count spectrum found its own rock ${sk.quarter_counts_found_pct}% of the time.` : '')),
        h('ol', { class: 'lab-list' }, ...d.matches.map(matchRow))),
      h('div', {},
        h('h3', {}, 'Likely deposit type', info('Weighted vote of the eight closest Curiosity spectra.',
          sk ? ` With the whole sol hidden it matched the right type ${sk.other_sol_same_type_pct}% of the time.` : '')),
        ...d.votes.slice(0, 4).map((v) => h('div', { class: 'prow' }, h('span', { class: 'pname' }, dot(familyColor(v.class)), v.label),
          h('span', { class: 'pbar' }, h('i', { style: { width: `${v.pct}%`, background: familyColor(v.class) } })), h('span', { class: 'pval' }, `${v.pct}%`))),
        h('h3', {}, 'Closest Earth standards', info('Earth reference rocks measured by the flight APXS before launch (CSA Open Data). They have no Martian air or dust, so they score lower than Mars rocks; the order is what matters.')),
        h('ol', { class: 'lab-std' }, ...d.standards.slice(0, 4).map((s) => h('li', {}, h('b', {}, s.name), h('small', {}, ` ${(s.description || '').split(' (')[0]}`)))))));
  requestAnimationFrame(() => labChart(chart, { energy: d.energy_kev, counts: d.counts, overlay: d.best_counts, overlayLabel: d.best_name, peaks: d.peaks, color: c1, overlayColor: c2 }));
}
$('lab-search').addEventListener('change', () => { const id = LAB.ids.get($('lab-search').value); if (id) runLab({ source_id: id }); });
$('lab-random').addEventListener('click', () => {
  const rocks = (LAB.list || []).filter((s) => s.kind === 'rock');
  if (!rocks.length) return;
  const s = rocks[Math.floor(Math.random() * rocks.length)];
  $('lab-search').value = labLabel(s);
  runLab({ source_id: s.id });
});
$('lab-keep').addEventListener('input', () => { $('lab-keep-val').textContent = `${$('lab-keep').value}%`; });
$('lab-keep').addEventListener('change', () => { if (LAB.src?.source_id) runLab({ source_id: LAB.src.source_id }); });
$('lab-hide').addEventListener('change', () => { if (LAB.src?.source_id) runLab({ source_id: LAB.src.source_id }); });
$('lab-file').addEventListener('change', async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  $('lab-search').value = '';
  runLab({ csv: await f.text() });
  e.target.value = '';
});

/* ====================================================================== EVA planner */
const GALE_BOX = [137.1224711, -4.9254743, 137.7298129, -4.2489631];   // MRO HiRISE Gale DEM (NASA Mars Trek)
const inGale = (p) => p && p.lon >= GALE_BOX[0] && p.lon <= GALE_BOX[2] && p.lat >= GALE_BOX[1] && p.lat <= GALE_BOX[3];
const fmtHM = (min) => `${Math.floor(min / 60)}:${String(Math.round(min % 60)).padStart(2, '0')}`;
const LETTERS = 'ABCDEFGHIJKLMNOP';
function evaStartNote() {
  const p = getPos();
  $('eva-start').textContent = !p ? 'Pick a start on the map, inside Gale crater.'
    : inGale(p) ? `Start ${fmtLL(p.lat, p.lon)}` : 'Start must be inside Gale crater.';
  $('eva-btn').disabled = !inGale(p);
}
[['eva-hours', (v) => `${v} h`], ['eva-slope', (v) => `${v}°`], ['eva-stop', (v) => `${v} min`], ['eva-speed', (v) => `${v} km/h`]].forEach(([id, f]) => {
  $(id).addEventListener('input', () => { $(`${id}-v`).textContent = f($(id).value); });
});
['lat', 'lon'].forEach((id) => $(id).addEventListener('input', evaStartNote));
$('eva-example').addEventListener('click', () => { setPosition(-4.725, 137.385); evaStartNote(); toGlobe({ type: 'rm:fly', lat: -4.725, lon: 137.385, alt_km: 6 }); });
$('eva-btn').addEventListener('click', planEva);
async function planEva() {
  const p = getPos();
  if (!inGale(p)) return evaStartNote();
  const btn = $('eva-btn');
  btn.disabled = true; btn.textContent = 'Planning…';
  let r;
  try {
    r = await postJson('/plan', { lat: p.lat, lon: p.lon, hours: +$('eva-hours').value, max_slope_deg: +$('eva-slope').value,
      stop_min: +$('eva-stop').value, speed_kmh: +$('eva-speed').value });
  } catch (e) {
    $('eva-body').replaceChildren(h('p', { class: 'note' }, e.message));
    return;
  } finally { btn.disabled = false; btn.textContent = 'Plan route'; }
  S.route = r;
  const s = r.summary, color = '#e8b72f';
  r.stops.forEach((st, i) => {
    st.letter = LETTERS[i];
    let best = 0;
    r.path.forEach((q, k) => { if ((q[0] - st.lat) ** 2 + (q[1] - st.lon) ** 2 < (r.path[best][0] - st.lat) ** 2 + (r.path[best][1] - st.lon) ** 2) best = k; });
    st.pathIndex = best;
  });
  toGlobe({ type: 'rm:route', line: r.line, start: r.start, stops: r.stops.map((st) => ({ lat: st.lat, lon: st.lon, letter: st.letter, label: st.label, eta: fmtHM(st.arrive_min) })) });
  if (!r.stops.length) {
    $('eva-body').replaceChildren(h('p', { class: 'note' }, 'Nothing reachable in that time. Try a longer EVA or another start.'));
    return;
  }
  const tile = (v, l) => h('div', { class: 'etile' }, h('b', {}, v), h('span', {}, l));
  const prof = h('div', { class: 'chart eva-prof' });
  $('eva-body').replaceChildren(
    h('div', { class: 'etiles' }, tile(String(s.new_types), `rock type${s.new_types === 1 ? '' : 's'}`), tile(`${s.distance_km} km`, 'distance'),
      tile(`${s.gain_m} m`, 'climb'), tile(fmtHM(s.total_h * 60), 'total time')),
    h('p', { class: 'note' }, `${fmtHM(s.walk_h * 60)} walking · ${fmtHM(s.stops_h * 60)} sampling · ${fmtHM(s.reserve_h * 60)} spare · steepest ${s.steepest_deg}°`,
      info(`Terrain: ${r.terrain.product}, height scale fitted to ${r.terrain.n_waypoints.toLocaleString()} Curiosity waypoints (±${r.terrain.residual_sd_m} m), in ${r.settings.cell_m} m cells. `,
        'Walking speed falls with slope (Tobler\'s hiking curve). Rarer deposit types are worth more; a second site of a type adds less. ',
        `${r.settings.reserve_pct}% of the time is kept in reserve. Features under about 100 m are not resolved.`)),
    prof,
    h('ol', { class: 'eva-stops' },
      h('li', { class: 'start' }, h('span', { class: 'eletter start' }, 'S'), h('span', {}, 'Start', h('small', {}, `${r.start.elev_m != null ? `${Math.round(r.start.elev_m).toLocaleString()} m` : ''}`)), h('span', { class: 'pval' }, '0:00')),
      ...r.stops.map((st) => h('li', { tabindex: 0, title: 'Open the rock measured here', onclick: () => st.members?.[0] && showDetail(st.members[0]),
        onkeydown: (e) => { if (e.key === 'Enter' && st.members?.[0]) showDetail(st.members[0]); } },
        h('span', { class: 'eletter' }, st.letter),
        h('span', {}, dot(familyColor(st.class)), st.label, h('small', {}, st.names.join(', '))),
        h('span', { class: 'pval' }, fmtHM(st.arrive_min)))),
      h('li', { class: 'start' }, h('span', { class: 'eletter start' }, 'S'), h('span', {}, 'Back at start'), h('span', { class: 'pval' }, fmtHM(s.total_h * 60)))),
    r.missed.length ? h('p', { class: 'note' }, `Also nearby: ${r.missed.slice(0, 3).map((m) => m.label).join(', ')}. Add time to include them.`) : '',
    h('div', { class: 'row' }, h('button', { class: 'btn ghost small', type: 'button', onclick: clearRoute }, 'Clear route')));
  requestAnimationFrame(() => profileChart(prof, { path: r.path, stops: r.stops, color }));
  selectTab('map');
}
function clearRoute() { S.route = null; $('eva-body').replaceChildren(); toGlobe({ type: 'rm:route', clear: true }); }
evaStartNote();
// side panel: two tools, one visible at a time
function setMode(mode) {
  document.querySelectorAll('.modes [data-mode]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.mode === mode)));
  $('card-eva').hidden = mode !== 'eva';
  ['card-identify', 'card-result', 'card-detail'].forEach((id) => { $(id).classList.toggle('mode-hidden', mode !== 'identify'); });
  document.querySelector('.side').scrollTop = 0;
}
document.querySelectorAll('.modes [data-mode]').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));

/* ---------------------------------------------------------------- shared UI pieces */
const pbar = (pct, color) => h('span', { class: 'pbar' }, h('i', { style: { width: `${Math.max(1, Math.min(100, pct))}%`, background: color || 'var(--series-1)' } }));
// "i" button: the method behind a number, shown on hover or tap instead of a paragraph under every block
function info(...text) {
  const tip = h('span', { class: 'info-tip', role: 'tooltip' }, ...text);
  return h('span', { class: 'info', tabindex: 0, 'aria-label': 'How this is worked out' }, icon('info', 'ic info-ic'), tip);
}
// collapsible section: a title, a one-line answer, and the details underneath
function section(title, answer, { open = false, help } = {}, ...body) {
  return h('details', { class: 'sec', open },
    h('summary', {}, h('span', { class: 'sec-t' }, title), help ? info(...[].concat(help)) : '', h('span', { class: 'sec-a' }, answer || ''), icon('chev', 'ic chev')),
    h('div', { class: 'sec-b' }, ...body));
}

/* ---------------------------------------------------------------- predictions */
function mineralsBlock(m, open = false) {
  const top = m.minerals.slice().sort((a, b) => b.wt - a.wt)[0];
  const rows = m.minerals.map((x) => h('div', { class: 'prow minerals', title: x.note },
    h('span', { class: 'pname' }, x.name, h('small', {}, x.formula)), pbar(x.wt), h('span', { class: 'pval' }, `≤ ${x.wt}%`)));
  return section('Likely minerals', top ? `${top.name} ≤ ${top.wt}%` : 'Mostly silicate', { open, help: [m.basis, ' Values are upper limits in wt%.'] },
    ...(rows.length ? rows : [h('p', { class: 'note' }, 'No salt, sulfate or phosphate above 0.5 wt%.')]),
    ...m.unassigned.map((t) => h('p', { class: 'note' }, t)));
}
function predictionsBlock(q) {
  const box = h('div', { class: 'preds' });
  if (q.minerals) box.append(mineralsBlock(q.minerals));
  const f = q.forecast;
  if (!f) {
    box.append(h('p', { class: 'note' }, 'Add your position to see what is nearby and how much water the soil holds.'));
    return box;
  }
  if (f.nearby) {
    const k = f.nearby.skill, top = f.nearby.odds[0];
    box.append(section('Within 1 km', `${top.label} ${top.pct}%`, {
      help: [`From ${f.nearby.n.toLocaleString()} ${f.nearby.rovers.join(' and ')} measurements within 1 km; closer ones count more. `,
        k ? `In a hold-out test the top type was right ${Math.round(k.top1_pct)}% of the time (always guessing basalt: ${Math.round(k.baseline_pct)}%). ` : '',
        f.nearby.caveat] },
    ...f.nearby.odds.map((o) => h('div', { class: 'prow' },
      h('span', { class: 'pname' }, dot(classColor(o.class)), o.label), pbar(o.pct, classColor(o.class)), h('span', { class: 'pval' }, `${o.pct}%`))),
    h('p', { class: 'note' }, `Nearest measured rock: ${f.nearby.nearest.name}, ${fmtDist(f.nearby.nearest.distance_m)} away.`)));
  }
  if (f.water) {
    const w = f.water;
    box.append(section('Water in the soil', `~${w.practical_l_t ?? w.upper_l_t} L per tonne`, {
      help: [`Odyssey measured ${w.h2o_wt.toFixed(1)} wt% water-equivalent hydrogen here (1 wt% = 10 L per tonne). `,
        w.share ? `Heating Gale soil to 835 °C, Curiosity's SAM released about 2 wt%, ${Math.round(w.share * 100)}% of Odyssey's value there; the estimate assumes the same share.` : ''] },
    h('div', { class: 'wbig' }, h('b', {}, `${w.practical_l_t ?? w.upper_l_t} L`), ' per tonne of soil',
      w.practical_l_t != null ? h('span', { class: 'note' }, ` (up to ${w.upper_l_t} L)`) : ''),
    h('a', { class: 'src-link', href: f.sources.sam.url, target: '_blank', rel: 'noopener' }, 'NASA: SAM finds water in soil', icon('ext', 'ic sm'))));
  }
  if (f.ground?.predicted && Object.keys(f.ground.predicted).length) {
    const err = f.ground.check?.error_pct || {};
    box.append(section('Soil from orbit', `FeO ${f.ground.predicted.FeO} · SiO2 ${f.ground.predicted.SiO2} wt%`, {
      help: 'Odyssey iron, silicon, potassium and chlorine converted to the oxides an APXS reports. ± is the largest miss against the rovers\' own soils at Gale, Gusev and Meridiani.' },
    h('div', { class: 'soil' }, ...Object.entries(f.ground.predicted).map(([ox, v]) =>
      h('span', {}, h('b', {}, ox), ` ${v}%`, err[ox] != null ? h('small', {}, ` ±${err[ox]}%`) : ''))),
    f.zones.length ? h('p', { class: 'note' }, `Prospect zones here: ${f.zones.map((z) => z.label).join(', ')}`) : ''));
  } else if (f.masked) box.append(h('p', { class: 'note' }, 'No orbital soil data this close to the pole.'));
  return box;
}

function whyBlock(ctx, region = true) {
  const kids = [];
  if (ctx.why) kids.push(h('p', {}, ctx.why));
  if (ctx.drivers?.length) {
    kids.push(h('div', { class: 'drivers' }, ...ctx.drivers.map((d) => h('div', { class: 'driver' },
      h('b', {}, d.element),
      h('span', { class: `ratio ${d.direction}`, title: `${fmtValue(d.element, d.value)} ${d.unit} vs typical Mars` }, `${d.ratio}×`),
      h('span', {}, d.why)))));
  }
  if (region && ctx.region) kids.push(h('div', { class: 'region' }, h('b', {}, icon('pin', 'ic sm'), ctx.region.name), h('span', {}, ctx.region.note)));
  if (ctx.links?.length) kids.push(h('ul', { class: 'nasa-links' }, ...ctx.links.map((l) => h('li', {}, h('a', { href: l.url, target: '_blank', rel: 'noopener' }, l.title, icon('ext', 'ic sm'))))));
  return kids;
}

async function loadSpectrum(d) {
  const block = $('spectrum-block');
  if (!d.has_spectrum) { block.hidden = true; return; }
  block.hidden = false;
  $('spectrum').replaceChildren(h('p', { class: 'note' }, 'Loading spectrum…'));
  $('spectrum-note').textContent = '';
  try {
    const s = await api(`/rocks/${encodeURIComponent(d.id)}/spectrum`);
    if (S.detail?.id !== d.id) return;
    S.spectrum = s;
    spectrumChart($('spectrum'), s, css('--series-1'));
    const hrs = s.live_time_s ? `${(s.live_time_s / 3600).toFixed(1)} h integration` : '';
    $('spectrum-note').replaceChildren(`${hrs}${hrs ? ' · ' : ''}peaks mark each element's K-alpha X-ray line · source: `,
      h('a', { href: s.source_url, target: '_blank', rel: 'noopener' }, s.source === 'CSA' ? 'Canadian Space Agency Open Data' : 'NASA PDS'));
  } catch (e) {
    $('spectrum').replaceChildren(h('p', { class: 'note' }, `Spectrum unavailable: ${e.message}`));
  }
}

function renderProvenance(d) {
  const src = d.source || {};
  const lines = [];
  const badge = (from) => h('span', { class: `badge-src ${from === 'CSA' ? 'csa' : ''}` }, from === 'CSA' ? 'CSA' : 'NASA PDS');
  if (src.rwp) lines.push(h('div', {}, badge(src.rwp.from), ' oxide file ', h('a', { href: src.rwp.url, target: '_blank', rel: 'noopener' }, src.rwp.url.split('/').pop())));
  if (src.rsp) lines.push(h('div', {}, badge(src.rsp.from), ' spectrum file ', h('a', { href: src.rsp.url, target: '_blank', rel: 'noopener' }, src.rsp.url.split('/').pop())));
  if (src.url) lines.push(h('div', {}, badge('PDS'), ' table ', h('a', { href: src.url, target: '_blank', rel: 'noopener' }, src.table), src.spectrum_id ? ` · spectrum ${src.spectrum_id}` : ''));
  else if (src.table) lines.push(h('div', {}, badge('PDS'), ` concentration table ${src.table}`));
  lines.push(h('div', {}, `Location: ${d.location?.method || 'rover traverse'}`));
  $('d-prov').replaceChildren(h('b', {}, 'Data provenance'), ...lines);
}

// keep charts sharp when the side panel changes width (height changes don't need a redraw)
let chartWidth = 0;
new ResizeObserver(debounce((entries) => {
  const w = Math.round(entries[entries.length - 1].contentRect.width);
  if (w === chartWidth) return;
  chartWidth = w;
  if (!S.detail || $('card-detail').hidden) return;
  renderSpider();
  if (S.spectrum) spectrumChart($('spectrum'), S.spectrum, css('--series-1'));
}, 150)).observe($('spider'));
window.addEventListener('scroll', hideTip, true);

/* ====================================================================== deposits tab */
async function openDeposits() {
  if (!S.meta) return;
  if (!S.deposits) {
    $('dep-rows').replaceChildren(h('tr', {}, h('td', { colspan: 6, class: 'note' }, 'Loading deposit sites…')));
    try {
      S.deposits = (await api('/deposits')).deposits;
    } catch (e) {
      $('dep-rows').replaceChildren(h('tr', {}, h('td', { colspan: 6, class: 'note' }, `Could not load deposits: ${e.message}`)));
      return;
    }
    $('dep-views').replaceChildren(...S.views.map((v) => h('button', { 'aria-pressed': v.id === S.depView, 'data-view': v.id,
      onclick: () => { S.depView = v.id; renderDeposits(); } }, FAMILY_COLORS[v.id] ? dot(FAMILY_COLORS[v.id]) : null, v.label)));
    $('dep-rover').addEventListener('change', renderDeposits);
  }
  renderDeposits();
}
function renderDeposits() {
  const view = S.views.find((v) => v.id === S.depView);
  document.querySelectorAll('#dep-views button').forEach((b) => b.setAttribute('aria-pressed', b.dataset.view === S.depView));
  const rover = $('dep-rover').value;
  const overview = view.id === 'unusual';
  const famOrder = Object.keys(FAMILY_COLORS);
  // overview: colour by family and keep each family together; family views: the same colours as the map
  const colorFor = (cid) => (overview ? familyColor(cid) : classColor(cid, view.id));
  const classIds = view.groups.flatMap((g) => g.classes);
  if (overview) classIds.sort((a, b) => famOrder.indexOf(familyOf(a)) - famOrder.indexOf(familyOf(b)));
  $('dep-legend').replaceChildren(...(overview
    ? famOrder.map((f) => h('button', { class: 'fam', style: { '--c': FAMILY_COLORS[f] }, title: `Show only ${familyLabel(f)}`,
        onclick: () => { S.depView = f; renderDeposits(); } }, dot(FAMILY_COLORS[f]), familyLabel(f)))
    : view.groups.map((g, i) => h('span', { class: 'fam', style: { '--c': S.slots[i] } }, dot(S.slots[i]), g.label))));
  $('dep-classes').replaceChildren(...classIds.map((cid) => S.classes.get(cid)).filter((c) => c?.count).map((c) => {
    const counts = Object.entries(c.by_rover || {}).map(([r, n]) => h('span', {}, h('b', {}, String(n)), ` ${r}`));
    return h('div', { class: 'dep-card', style: { '--c': colorFor(c.id) } },
      overview ? h('div', { class: 'fam-chip' }, familyLabel(c.family)) : null,
      h('h4', {}, dot(colorFor(c.id)), c.label),
      h('p', {}, c.description),
      h('div', { class: 'rule' }, `Rule: ${c.rule}`),
      h('div', { class: 'counts' }, ...counts, h('span', {}, `· ${c.sites} site${c.sites === 1 ? '' : 's'}`)),
      h('button', { class: 'btn small', onclick: () => showClassOnMap(c.id, view.id) }, 'Show on map'));
  }));
  const deps = S.deposits.filter((d) => classIds.includes(d.class) && (!rover || d.rover === rover))
    .sort((a, b) => b.count - a.count).slice(0, 250);
  $('dep-count').textContent = `(${deps.length.toLocaleString()})`;
  $('dep-rows').replaceChildren(...deps.map((d) => h('tr', { style: { '--c': colorFor(d.class) } },
    h('td', { class: 'type' }, dot(colorFor(d.class)), classLabel(d.class), overview ? h('span', { class: 'fam-sub' }, familyLabel(familyOf(d.class))) : null),
    h('td', {}, d.rover),
    h('td', { class: 'num' }, String(d.count)),
    h('td', { class: 'num' }, d.sol_first === d.sol_last ? String(d.sol_first) : `${d.sol_first}–${d.sol_last}`),
    h('td', { class: 'names' }, d.names.slice(0, 3).join(', ') + (d.names.length > 3 ? '…' : '')),
    h('td', {}, h('button', { class: 'btn small', onclick: () => showDepositOnMap(d, view.id) }, 'Show on map')))));
}
function showDepositOnMap(d, viewId) {
  toGlobe({ type: 'rm:filter', view: viewId });
  toGlobe({ type: 'rm:highlight', ids: d.members, fit: true, select: null });
  selectTab('map');
  showDetail(d.members[0], { fromMap: true });
}
function showClassOnMap(cid, viewId) {
  const ids = S.summary.filter((r) => r.deposit === cid).map((r) => r.id);
  toGlobe({ type: 'rm:filter', view: viewId });
  toGlobe({ type: 'rm:highlight', ids, fit: true, select: null });
  selectTab('map');
}

onChemInput();
boot();
