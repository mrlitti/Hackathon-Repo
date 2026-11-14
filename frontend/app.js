import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

const $ = (id) => document.getElementById(id);
const ELEMENTS = ['SiO2', 'FeO', 'MgO', 'CaO', 'Al2O3', 'SO3', 'Na2O', 'K2O', 'TiO2', 'P2O5', 'Cl', 'MnO', 'Cr2O3'];

/* ---------------- backend status ---------------- */
fetch('/api/health').then(r => r.json())
  .then(d => $('status').textContent = `backend ok · ${d.rocks_loaded} APXS rocks loaded`)
  .catch(() => $('status').textContent = 'backend offline');

/* ---------------- 3D viewer ---------------- */
const container = $('viewer');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
container.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);
const camera = new THREE.PerspectiveCamera(50, 1, 0.01, 10000);
camera.position.set(3, 2, 3);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.HemisphereLight(0xffffff, 0x332211, 1.2));
const sun = new THREE.DirectionalLight(0xffeedd, 2);
sun.position.set(5, 10, 5);
scene.add(sun);
scene.add(new THREE.GridHelper(10, 20, 0x333333, 0x151515));

let current = null;

function resize() {
  const { clientWidth: w, clientHeight: h } = container;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(container);

renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });

function showObject(obj) {
  if (current) scene.remove(current);
  current = obj;
  // center + fit camera
  const box = new THREE.Box3().setFromObject(obj);
  const size = box.getSize(new THREE.Vector3()).length() || 1;
  obj.position.sub(box.getCenter(new THREE.Vector3()));
  scene.add(obj);
  camera.position.set(size, size * 0.7, size);
  camera.near = size / 1000; camera.far = size * 100;
  camera.updateProjectionMatrix();
  controls.target.set(0, 0, 0);
  $('viewer-hint').style.display = 'none';
}

function loadModel(url, ext) {
  ext = ext.toLowerCase();
  const onErr = (e) => alert('Could not load model: ' + (e.message || e));
  if (ext === 'glb' || ext === 'gltf') new GLTFLoader().load(url, g => showObject(g.scene), undefined, onErr);
  else if (ext === 'obj') new OBJLoader().load(url, showObject, undefined, onErr);
  else if (ext === 'stl') new STLLoader().load(url, geo => {
    showObject(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0xb5651d })));
  }, undefined, onErr);
  else alert('Unsupported format: ' + ext);
}

async function uploadModel(file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/models', { method: 'POST', body: fd });
  if (!res.ok) return alert((await res.json()).detail);
  const saved = await res.json();
  loadModel(saved.url, saved.name.split('.').pop());
  refreshModelList();
}

async function refreshModelList() {
  const { models } = await fetch('/api/models').then(r => r.json());
  $('model-list').innerHTML = '<option value="">Saved models…</option>' +
    models.map(m => `<option value="${m.url}">${m.name}</option>`).join('');
}

$('model-input').onchange = (e) => e.target.files[0] && uploadModel(e.target.files[0]);
$('model-list').onchange = (e) => e.target.value && loadModel(e.target.value, e.target.value.split('.').pop());
container.ondragover = (e) => { e.preventDefault(); container.classList.add('drag'); };
container.ondragleave = () => container.classList.remove('drag');
container.ondrop = (e) => {
  e.preventDefault(); container.classList.remove('drag');
  if (e.dataTransfer.files[0]) uploadModel(e.dataTransfer.files[0]);
};
refreshModelList();

/* ---------------- photo input ---------------- */
$('photo-input').onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  $('photo-preview').src = URL.createObjectURL(file);
  const fd = new FormData();
  fd.append('file', file);
  await fetch('/api/photos', { method: 'POST', body: fd });
  // TODO: image-based matching
};

/* ---------------- chemistry inputs ---------------- */
$('chem-inputs').innerHTML = ELEMENTS.map(el =>
  `<label><span>${el}</span><input type="number" step="any" data-el="${el}"></label>`).join('');

/* ---------------- match ---------------- */
$('match-btn').onclick = async () => {
  const chemistry = {};
  document.querySelectorAll('#chem-inputs input').forEach(i => { if (i.value !== '') chemistry[i.dataset.el] = +i.value; });
  const lat = $('lat').value, lon = $('lon').value;
  const body = { chemistry, lat: lat === '' ? null : +lat, lon: lon === '' ? null : +lon };

  const data = await fetch('/api/match', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).then(r => r.json());

  const v = $('verdict');
  v.className = 'verdict ' + (data.verdict?.label || '');
  v.textContent = data.verdict ? `${data.verdict.label} — ${data.verdict.reason}` : '—';

  if (!data.matches?.length) {
    $('results').innerHTML = `<p class="hint">${data.note || 'No matches.'}</p>`;
    return;
  }
  $('results').innerHTML = '';
  data.matches.forEach(m => {
    const div = document.createElement('div');
    div.className = 'match';
    const dist = m.distance_m != null ? `, ${m.distance_m} m from here` : '';
    div.textContent = `${m.rock.name} (${m.rock.rover}, sol ${m.rock.sol}${dist}) · score ${m.chem_distance}`;
    div.onclick = () => showDetail(m.rock);
    $('results').appendChild(div);
  });
};

/* ---------------- rock detail ---------------- */
function showDetail(rock) {
  const d = $('detail');
  d.innerHTML = '';
  if (rock.photo_url) {
    const img = document.createElement('img');
    img.src = rock.photo_url; img.style.maxWidth = '100%';
    d.appendChild(img);
  }
  const h = document.createElement('h3'); h.textContent = rock.name; d.appendChild(h);
  const chem = document.createElement('pre'); chem.textContent = JSON.stringify(rock.chemistry, null, 1); d.appendChild(chem);
  const n = document.createElement('p'); n.textContent = rock.notes || ''; d.appendChild(n);
  const s = document.createElement('p'); s.className = 'hint'; s.textContent = rock.source || ''; d.appendChild(s);
}
