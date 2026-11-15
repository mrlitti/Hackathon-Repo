import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { ORDER, TRACE, fmtValue, hideTip, spectrumChart, spiderChart, unit } from './charts.js';

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
    else if (k === 'style') Object.assign(n.style, v);
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
    showDetail(m.id, { fromMap: true });
  } else if (m.type === 'rm:position') {
    setPosition(m.lat, m.lon, false);
    setPicking(false);
  } else if (m.type === 'rm:element') {
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
    const opt = (e) => h('option', { value: e.key }, `${e.label} (${e.key}) — ${e.grs && e.apxs_count ? 'orbit + rocks' : e.grs ? 'orbit only' : 'rocks only'}`);
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
$('m-pct').addEventListener('input', syncElementTools);
$('m-pct').addEventListener('change', sendElement);

/* ====================================================================== tabs */
const tabs = [...document.querySelectorAll('[role="tab"]')];
function selectTab(name) {
  for (const t of tabs) {
    const on = t.dataset.tab === name;
    t.setAttribute('aria-selected', on);
    t.tabIndex = on ? 0 : -1;
    $(`tab-${t.dataset.tab}`).hidden = !on;
  }
  if (name === 'deposits') openDeposits();
  if (name === 'model') initViewer();
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
    S.slots = meta.slot_colors || S.slots;
    S.other = meta.other_color || S.other;
    (meta.classes || []).forEach((c) => S.classes.set(c.id, c));
    S.summary = list.rocks;
    $('status').className = 'status ok';
    $('status').lastElementChild.textContent = `backend online · data built ${String(health.generated_utc || '').slice(0, 10)}`;
    renderStats(meta);
    buildSimulator();
    buildElementTools();
    onChemInput();
    const rid = new URLSearchParams(location.search).get('rock');
    if (rid) showDetail(rid);
  } catch (e) {
    $('status').className = 'status bad';
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
const inputs = ORDER.map((el) => {
  const input = h('input', { type: 'number', step: 'any', min: '0', inputmode: 'decimal', 'data-el': el, 'aria-label': `${el} in ${unit(el)}` });
  grid.append(h('label', {}, h('span', {}, h('b', {}, el), h('small', {}, unit(el))), input));
  return input;
});
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
  }
  onChemInput();
}

const liveClassify = debounce(async () => {
  const chem = readChem();
  const box = $('live-class');
  if (Object.keys(chem).length < 3) {
    box.replaceChildren(h('span', { class: 'note', style: { margin: 0 } }, 'Enter at least 3 elements to classify.'));
    return;
  }
  try {
    const c = await postJson('/classify', { chemistry: chem });
    box.replaceChildren(h('span', {}, 'Looks like'), h('span', { class: 'chip' }, dot(classColor(c.class)), c.class_info.label),
      h('span', { class: 'reason' }, c.reason));
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
  if (S.simulated) { S.simulated = null; $('sim-note').replaceChildren(); }
  onChemInput();
}));

/* position */
function getPos() {
  const lat = parseFloat($('lat').value), lon = parseFloat($('lon').value);
  return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 360 ? { lat, lon } : null;
}
function setPosition(lat, lon, tellGlobe = true) {
  $('lat').value = lat.toFixed(5);
  $('lon').value = (((lon + 180) % 360 + 360) % 360 - 180).toFixed(5);
  if (tellGlobe) toGlobe({ type: 'rm:set-position', lat, lon });
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
  sel.replaceChildren(h('option', { value: '' }, 'Simulate a reading from… any rock'));
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
      'Simulated from a real measurement — ', h('b', {}, rock.name), ` (${rock.rover}, sol ${rock.sol}) — with its instrument error bars added, `,
      `and you are standing ${Math.round(d)} m away. Rock Match should recognise it.`));
  } catch (e) {
    $('sim-note').replaceChildren(h('div', { class: 'sim-note' }, `Could not simulate: ${e.message}`));
  }
});

$('clear-btn').addEventListener('click', () => {
  writeChem({}, false);
  S.simulated = null;
  $('sim-note').replaceChildren();
  $('card-result').hidden = true;
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
      ' — identification uses the APXS chemistry above.');
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

const VERDICT = {
  SAMPLE: { cls: 'v-sample', icon: '✓', title: 'Collect a sample' },
  MAYBE: { cls: 'v-maybe', icon: '?', title: 'Worth a closer look' },
  DUPLICATE: { cls: 'v-duplicate', icon: '=', title: 'Already well sampled' },
};
function renderResult(res) {
  $('card-result').hidden = false;
  const v = VERDICT[res.verdict.label] || VERDICT.MAYBE;
  $('verdict').replaceChildren(h('div', { class: `verdict ${v.cls}` },
    h('span', { class: 'v-icon', 'aria-hidden': 'true' }, v.icon),
    h('div', {}, h('b', {}, `${res.verdict.label} · ${v.title}`), h('p', {}, res.verdict.reason))));

  const q = res.query;
  const fact = (label, ...value) => h('div', { class: 'fact' }, h('span', {}, label), h('span', {}, ...value));
  const facts = [
    fact('Deposit type', h('span', { class: 'chip' }, dot(classColor(q.class)), q.class_info.label), ' ', h('span', { class: 'reason' }, q.reason)),
    fact('How rare', `${res.stats.class_count.toLocaleString()} of ${res.stats.total.toLocaleString()} measurements share this type`),
  ];
  if (res.earth_ref) {
    const e = res.earth_ref;
    const src = 'CSA lab standard measured by the flight APXS';
    facts.push(fact('Earth analogue', e.similarity >= 50 ? `${e.name} — ${e.kind} (${e.similarity}% similar; ${src})`
      : e.similarity >= 20 ? `Loosely resembles ${e.name} — ${e.kind} (${e.similarity}%; ${src})`
        : `None close among the ${S.meta.earth_refs} CSA lab standards (closest: ${e.name}, ${e.similarity}%) — unlike common Earth rocks`));
  }
  if (res.nearest_same_class) {
    const n = res.nearest_same_class;
    facts.push(fact('Nearest same type', h('a', { href: '#', onclick: (e) => { e.preventDefault(); showDetail(n.id); } }, n.name),
      ` — ${fmtDist(n.distance_m)} away (${n.rover}, sol ${n.sol})`));
  }
  $('facts').replaceChildren(...facts);
  if (q.context?.why || q.context?.drivers?.length) {
    $('facts').append(h('div', { class: 'query-why why' }, h('h3', { style: { marginTop: 0 } }, 'Why your reading looks like this'), ...whyBlock(q.context, false)));
  }

  $('matches').replaceChildren(...res.matches.map((m, i) => {
    const li = h('li', { class: 'match', tabindex: 0, 'data-id': m.id, 'aria-label': `${m.name}, ${m.similarity}% similar` },
      h('div', { class: 'm-top' }, h('span', { class: 'rank' }, String(i + 1)), h('span', { class: 'm-name' }, m.name), h('span', { class: 'm-sim' }, `${m.similarity}%`)),
      h('div', { class: 'meter', 'aria-hidden': 'true' }, h('i', { style: { width: `${m.similarity}%` } })),
      h('div', { class: 'm-sub' }, dot(classColor(m.deposit)), `${classLabel(m.deposit)} · ${m.rover} · sol ${m.sol}${m.distance_m != null ? ` · ${fmtDist(m.distance_m)} away` : ''}`));
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
  if (!fromMap) toGlobe({ type: 'rm:select', id, fly: true });
  $('card-detail').hidden = false;
  $('d-title').textContent = d.name;
  const bits = [`${d.rover} · sol ${d.sol}`, `${d.sample_type}${d.preparation ? ` (${d.preparation})` : ''}`, fmtLL(d.lat, d.lon)];
  if (d.elev_m != null) bits.push(`${d.elev_m.toLocaleString()} m elevation`);
  if (d.traverse_km != null) bits.push(`${d.traverse_km} km into the traverse`);
  $('d-meta').textContent = bits.join(' · ');
  renderClassChip(d);
  renderComposition(d.chemistry);
  $('d-why').replaceChildren(...whyBlock(d.context || {}));
  markActive();
  renderSpider();
  renderValues();
  renderProvenance(d);
  loadPhotos(d);
  loadSpectrum(d);
  if (matchMedia('(max-width: 1000px)').matches) $('card-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderClassChip(d) {
  const kids = [h('span', { class: 'rover-badge' }, h('i', { style: { background: ROVER_COLOR[d.rover] } }), d.rover),
    h('span', { class: 'chip' }, dot(classColor(d.deposit)), d.class.label),
    h('span', { class: 'chip' }, `data quality: ${d.quality.tier}`)];
  if (d.site) kids.push(h('span', { class: 'chip' }, `deposit site · ${d.site.count} measurement${d.site.count === 1 ? '' : 's'}`));
  if (d.note) {
    const sulfur = /S assumed as SO3/i.test(d.note);
    kids.push(h('span', { class: 'chip note-chip', title: 'Note from the NASA PDS concentration table' },
      `NASA note: ${d.note}${sulfur ? ' — APXS reports all sulfur as SO3; values this high with almost no Ca or Mg to form sulfate point to elemental sulfur' : ''}`));
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
        h('span', { class: 'open' }, im.page ? 'Open on NASA ↗' : 'Full size ↗'));
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
function whyBlock(ctx, region = true) {
  const kids = [];
  if (ctx.why) kids.push(h('p', {}, ctx.why));
  if (ctx.drivers?.length) {
    kids.push(h('div', { class: 'drivers' }, ...ctx.drivers.map((d) => h('div', { class: 'driver' },
      h('b', {}, d.element),
      h('span', { class: `ratio ${d.direction}`, title: `${fmtValue(d.element, d.value)} ${d.unit} vs typical Mars` }, `${d.ratio}×`),
      h('span', {}, d.why)))));
  }
  if (region && ctx.region) kids.push(h('div', { class: 'region' }, h('b', {}, `📍 ${ctx.region.name}`), h('span', {}, ctx.region.note)));
  if (ctx.links?.length) kids.push(h('ul', { class: 'nasa-links' }, ...ctx.links.map((l) => h('li', {}, h('a', { href: l.url, target: '_blank', rel: 'noopener' }, l.title)))));
  if (ctx.caveat) kids.push(h('div', { class: 'caveat' }, ctx.caveat));
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
      onclick: () => { S.depView = v.id; renderDeposits(); } }, v.label)));
    $('dep-rover').addEventListener('change', renderDeposits);
  }
  renderDeposits();
}
function renderDeposits() {
  const view = S.views.find((v) => v.id === S.depView);
  document.querySelectorAll('#dep-views button').forEach((b) => b.setAttribute('aria-pressed', b.dataset.view === S.depView));
  const rover = $('dep-rover').value;
  const classIds = view.groups.flatMap((g) => g.classes);
  $('dep-classes').replaceChildren(...classIds.map((cid) => S.classes.get(cid)).filter((c) => c?.count).map((c) => {
    const counts = Object.entries(c.by_rover || {}).map(([r, n]) => h('span', {}, h('b', {}, String(n)), ` ${r}`));
    return h('div', { class: 'dep-card' },
      h('h4', {}, dot(classColor(c.id, view.id)), c.label),
      h('p', {}, c.description),
      h('div', { class: 'rule' }, `Rule: ${c.rule}`),
      h('div', { class: 'counts' }, ...counts, h('span', {}, `· ${c.sites} site${c.sites === 1 ? '' : 's'}`)),
      h('button', { class: 'btn small', onclick: () => showClassOnMap(c.id, view.id) }, 'Show on map'));
  }));
  const deps = S.deposits.filter((d) => classIds.includes(d.class) && (!rover || d.rover === rover))
    .sort((a, b) => b.count - a.count).slice(0, 250);
  $('dep-count').textContent = `(${deps.length.toLocaleString()})`;
  $('dep-rows').replaceChildren(...deps.map((d) => h('tr', {},
    h('td', {}, dot(classColor(d.class, view.id)), classLabel(d.class)),
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

/* ====================================================================== 3D model viewer (lazy) */
let viewer = null;
function initViewer() {
  if (viewer) return;
  const box = $('viewer');
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  box.append(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 10000);
  camera.position.set(3, 2, 3);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x2a1a10, 1.4));
  const sun = new THREE.DirectionalLight(0xffeedd, 2.2);
  sun.position.set(5, 10, 6);
  scene.add(sun);
  scene.add(new THREE.GridHelper(10, 20, 0x333333, 0x161616));
  viewer = { renderer, scene, camera, controls, current: null };
  const resize = () => {
    const w = box.clientWidth, hgt = box.clientHeight;
    if (!w || !hgt) return;
    renderer.setSize(w, hgt);
    camera.aspect = w / hgt;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(box);
  resize();
  renderer.setAnimationLoop(() => {
    if ($('tab-model').hidden) return;
    controls.update();
    renderer.render(scene, camera);
  });
  refreshModelList();
}
function showObject(obj) {
  const v = viewer;
  if (v.current) v.scene.remove(v.current);
  v.current = obj;
  const box = new THREE.Box3().setFromObject(obj);
  const size = box.getSize(new THREE.Vector3()).length() || 1;
  obj.position.sub(box.getCenter(new THREE.Vector3()));
  v.scene.add(obj);
  v.camera.position.set(size, size * 0.7, size);
  v.camera.near = size / 1000;
  v.camera.far = size * 100;
  v.camera.updateProjectionMatrix();
  v.controls.target.set(0, 0, 0);
  $('viewer-hint').hidden = true;
}
function loadModel(url, ext) {
  initViewer();
  const onErr = (e) => { $('viewer-hint').hidden = false; $('viewer-hint').textContent = `Could not load model: ${e.message || e}`; };
  ext = ext.toLowerCase();
  if (ext === 'glb' || ext === 'gltf') new GLTFLoader().load(url, (g) => showObject(g.scene), undefined, onErr);
  else if (ext === 'obj') new OBJLoader().load(url, showObject, undefined, onErr);
  else if (ext === 'stl') new STLLoader().load(url, (geo) => showObject(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0xb5651d, roughness: 0.9 }))), undefined, onErr);
}
async function uploadModel(file) {
  const fd = new FormData();
  fd.append('file', file);
  try {
    const saved = await api('/models', { method: 'POST', body: fd });
    loadModel(saved.url, saved.name.split('.').pop());
    refreshModelList();
  } catch (e) {
    $('viewer-hint').hidden = false;
    $('viewer-hint').textContent = `Upload failed: ${e.message}`;
  }
}
async function refreshModelList() {
  try {
    const { models } = await api('/models');
    $('model-list').replaceChildren(h('option', { value: '' }, 'Saved models…'), ...models.map((m) => h('option', { value: m.url }, m.name)));
  } catch { /* backend offline: keep the list empty */ }
}
$('model-input').addEventListener('change', (e) => e.target.files[0] && uploadModel(e.target.files[0]));
$('model-list').addEventListener('change', (e) => e.target.value && loadModel(e.target.value, e.target.value.split('.').pop()));
const vbox = $('viewer');
vbox.addEventListener('dragover', (e) => { e.preventDefault(); vbox.classList.add('drag'); });
vbox.addEventListener('dragleave', () => vbox.classList.remove('drag'));
vbox.addEventListener('drop', (e) => {
  e.preventDefault();
  vbox.classList.remove('drag');
  if (e.dataTransfer.files[0]) uploadModel(e.dataTransfer.files[0]);
});

onChemInput();
boot();
