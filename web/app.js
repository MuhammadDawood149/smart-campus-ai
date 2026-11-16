/* ==========================================================================
   Smart Campus AI — app.js
   UI logic and animations. Every piece of data comes from API (api.js).
   ========================================================================== */
'use strict';

/* ---------------- helpers ---------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const SVGNS = 'http://www.w3.org/2000/svg';
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const sleep = (ms) => new Promise((r) => setTimeout(r, reducedMotion.matches ? Math.min(ms, 15) : ms));
const pretty = (s) => String(s ?? '').replace(/_/g, ' ');
const cap = (s) => String(s ?? '').charAt(0).toUpperCase() + String(s ?? '').slice(1);
const fmtNum = (n, d = 2) => (typeof n === 'number' ? n.toFixed(d) : n);

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else if (k === 'style' && typeof v === 'object') {
      for (const [sk, sv] of Object.entries(v)) {
        if (sk.startsWith('--')) e.style.setProperty(sk, sv); else e.style[sk] = sv;
      }
    }
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c instanceof Node ? c : document.createTextNode(c));
  return e;
}
function s(tag, attrs = {}, parent) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === 'text') e.textContent = v; else e.setAttribute(k, v);
  }
  if (parent) parent.appendChild(e);
  return e;
}

const ICONS = {
  console: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>',
  preprocessing: '<path d="M4 5h16l-6 7v6l-4 2v-8z"/>',
  router: '<path d="M3 12h5l4-6h7M8 12l4 6h7"/><path d="M17 3l3 3-3 3M17 15l3 3-3 3"/>',
  ann: '<circle cx="5" cy="6" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/><path d="M6.8 7.2l3.6 3.4M6.8 16.8l3.6-3.4M14 12h3"/>',
  logic: '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11"/><path d="M9 8h6"/>',
  eligible: '<path d="M8 12.5l3 3 5-6"/>',
  csp: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4M8 14h3v3H8z"/>',
  search: '<circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="6" r="2.2"/><path d="M8.2 18H14a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h5.8"/>',
  final: '<path d="M5 21V4h11l-2 4 2 4H5"/>',
  history: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  reset: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
  replay: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M10 9l5 3-5 3z"/>',
  play: '<path d="M7 5l12 7-12 7z"/>',
  swap: '<path d="M7 4L3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7"/>',
  compare: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  arrow: '<path d="M4 12h15M14 6l6 6-6 6"/>',
  link: '<path d="M7 17L17 7M9 7h8v8"/>',
};
function icon(name, cls = 'ico') {
  const span = h('span', { class: cls, 'aria-hidden': 'true' });
  span.innerHTML = `<svg viewBox="0 0 24 24">${ICONS[name] || ''}</svg>`;
  return span;
}
function fillIcons(root = document) {
  $$('[data-icon]', root).forEach((el) => {
    if (el.firstChild) return;
    el.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[el.dataset.icon] || ''}</svg>`;
  });
}

let toastTimer;
function toast(msg, isError = false) {
  const t = $('#toast');
  t.textContent = msg; t.className = `toast${isError ? ' error' : ''}`; t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, isError ? 5200 : 2600);
}
async function safe(fn, label) {
  try { return await fn(); } catch (err) { console.error(err); toast(`${label}: ${err.message}`, true); return null; }
}

/* ---------------- constants & state ---------------- */
const LOCATIONS = ['Main_Gate', 'Parking', 'Admin_Block', 'Student_Services', 'Exam_Hall', 'Seminar_Room', 'Library', 'AI_Lab', 'Bus_Stop', 'Medical_Center', 'Cafeteria', 'Science_Block', 'Hostel'];
const CATEGORIES = ['AI_Lab_Support', 'Viva_Scheduling', 'Access_Request', 'Maintenance', 'Emergency_Help'];
const ROOMS = ['AI_Lab', 'Exam_Hall', 'Seminar_Room', 'Admin_Block', 'Student_Services', 'Medical_Center'];
const SLOT_TIMES = { 1: '09:00', 2: '10:30', 3: '13:00', 4: '14:30' };
const DEADLINE = { urgent: 2, high: 3, normal: 4, low: 4 };
const ROLE_IDX = { student: 0, instructor: 1, staff: 2 };
const QUERY_EXAMPLES = ['UsesLab(DrKhan, Lab1)', 'Eligible(Sara, AI)', 'UsesLab(x, Lab1)', 'CanRequest(Ali, AI_Lab_Support)', 'CanScheduleViva(Ahmed, G4)'];
const MOD_VAR = { ANN: '--ann', Logic_KB: '--logic', CSP: '--csp', Search: '--search' };

const REQUEST_TYPES = [
  { value: 'Navigation_Only', name: 'Navigation', desc: 'Route between two campus places', mods: ['Search'] },
  { value: 'Eligibility_Check', name: 'Eligibility check', desc: 'Ask the knowledge base', mods: ['Logic_KB'] },
  { value: 'Booking_or_Scheduling', name: 'Booking / scheduling', desc: 'Reserve a room or viva slot', mods: ['Logic_KB', 'CSP', 'Search'] },
  { value: 'Urgent_Service_Request', name: 'Urgent service', desc: 'Prioritised help, now', mods: ['ANN', 'Logic_KB', 'CSP', 'Search'] },
  { value: 'Full_Service_Request', name: 'Full service', desc: 'Every module: priority, eligibility, slot and route', mods: ['ANN', 'Logic_KB', 'CSP', 'Search'] },
];
const TYPE_PIPE = Object.fromEntries(REQUEST_TYPES.map((t) => [t.value, t.mods]));

const STAGES = [
  { key: 'preprocessing', label: 'Preprocessing', mod: 'core' },
  { key: 'router', label: 'Router', mod: 'core' },
  { key: 'ann', label: 'ANN', mod: 'ann', pipe: 'ANN' },
  { key: 'logic', label: 'Logic / KB', mod: 'logic', pipe: 'Logic_KB' },
  { key: 'eligible', label: 'Eligible?', mod: 'logic', pipe: 'Logic_KB' },
  { key: 'csp', label: 'CSP', mod: 'csp', pipe: 'CSP' },
  { key: 'search', label: 'Search', mod: 'search', pipe: 'Search' },
  { key: 'final', label: 'Final response', mod: 'core' },
];

const S = {
  graph: null, pos: {}, adj: {},
  history: [], current: null,
  demos: [], kb: null, derived: [],
  mapRefs: null, mapSrc: 'Hostel', mapDst: 'AI_Lab', mapResult: null, pickNext: 'source',
  runs: { pipe: 0, map: 0, csp: 0, viva: 0, kb: 0, ann: 0 },
};

/* ==========================================================================
   NAVIGATION & THEME
   ========================================================================== */
function go(section, { focus = false } = {}) {
  $$('.section').forEach((sec) => {
    const on = sec.id === `sec-${section}`;
    sec.hidden = !on; sec.classList.toggle('active', on);
  });
  $$('.nav-item').forEach((b) => {
    const on = b.dataset.section === section;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  });
  window.scrollTo({ top: 0, behavior: reducedMotion.matches ? 'auto' : 'smooth' });
  if (focus) $('#content').focus({ preventScroll: true });
  if (section === 'console') requestAnimationFrame(layoutPipeline);
  if (section === 'csp' && !S.cspAnimating) refreshBookings();
}

function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  $('#theme-toggle').setAttribute('aria-label', t === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
  try { localStorage.setItem('sc-theme', t); } catch (_) { /* storage unavailable */ }
}
function loadTheme() {
  try { return localStorage.getItem('sc-theme') || 'dark'; } catch (_) { return 'dark'; }
}

/* ==========================================================================
   REQUEST CONSOLE — form
   ========================================================================== */
function buildForm() {
  $$('[data-locations]').forEach((sel) => {
    sel.innerHTML = '';
    if (sel.id === 'f-loc') sel.append(h('option', { value: '' }, 'Select a location…'));
    if (sel.id === 'f-dest') sel.append(h('option', { value: '' }, 'Select a destination…'));
    LOCATIONS.forEach((l) => sel.append(h('option', { value: l }, pretty(l))));
  });
  $$('[data-categories]').forEach((sel) => {
    sel.innerHTML = '';
    CATEGORIES.forEach((c) => sel.append(h('option', { value: c }, pretty(c))));
  });
  const tb = $('#tb-cat');
  CATEGORIES.filter((c) => c !== 'Viva_Scheduling').forEach((c) => tb.append(h('option', { value: c }, pretty(c))));

  const grid = $('#type-grid');
  REQUEST_TYPES.forEach((t, i) => {
    grid.append(h('label', { class: 'type-card' },
      h('input', { type: 'radio', name: 'request_type', value: t.value, checked: i === 0 }),
      h('span', { class: 'type-name' }, t.name),
      h('span', { class: 'type-desc' }, t.desc),
      h('span', { class: 'type-mods', title: `Modules: ${t.mods.map(pretty).join(', ')}` },
        t.mods.map((m) => h('i', { style: { '--c': `var(${MOD_VAR[m]})` } }))),
    ));
  });

  $$('[data-query-chips]').forEach((box) => {
    const input = document.getElementById(box.dataset.queryChips);
    QUERY_EXAMPLES.forEach((q) => box.append(h('button', {
      type: 'button', class: 'chip',
      onclick: () => {
        input.value = q; input.focus();
        if ('autorun' in box.dataset) $('#kb-form').requestSubmit();
      },
    }, q)));
  });

  $$('input[type="range"]').forEach(syncRange);
  document.addEventListener('input', (e) => { if (e.target.matches('input[type="range"]')) syncRange(e.target); });

  $('#req-form').addEventListener('change', (e) => {
    if (e.target.name === 'request_type' || e.target.name === 'category') updateFields();
  });
  $('#req-form').addEventListener('submit', (e) => { e.preventDefault(); submitForm(); });
  $('#clear-btn').addEventListener('click', clearForm);

  $('#demo-select').addEventListener('change', async (e) => {
    const d = S.demos[+e.target.value];
    if (!d) return;
    fillForm(d.request);
    await sleep(420);
    submitForm({ demo: true });
  });
  updateFields(true);
}

function syncRange(r) {
  const pct = ((r.value - r.min) / (r.max - r.min)) * 100;
  r.style.setProperty('--fill', `${pct}%`);
  const out = document.querySelector(`output[for="${r.id}"]`);
  if (out) out.textContent = r.value;
}

function currentType() { return ($('input[name="request_type"]:checked') || {}).value || 'Navigation_Only'; }

function updateFields(instant = false) {
  const type = currentType();
  const cat = $('#f-cat').value;
  $$('.dyn').forEach((d) => {
    let show = d.dataset.show.split(' ').includes(type);
    if ('vivaOnly' in d.dataset) show = show && cat === 'Viva_Scheduling';
    const optional = (d.dataset.optional || '').split(' ').includes(type);
    $$('.opt', d).forEach((o) => o.classList.toggle('is-on', optional || o.classList.contains('is-on') && !d.dataset.optional));
    const seg = $('.slot-seg', d);
    if (seg) {
      seg.classList.toggle('allow-none', optional);
      const none = $('input[value=""]', seg);
      if (!optional && none.checked) $('input[value="2"]', seg).checked = true;
    }
    setShown(d, show, instant);
  });
}
function setShown(el, show, instant) {
  clearTimeout(el._t);
  if (show) {
    el.hidden = false; el.inert = false;
    if (instant) el.classList.remove('is-hidden');
    else requestAnimationFrame(() => requestAnimationFrame(() => el.classList.remove('is-hidden')));
  } else {
    el.classList.add('is-hidden'); el.inert = true;
    if (instant) el.hidden = true;
    else el._t = setTimeout(() => { el.hidden = true; }, reducedMotion.matches ? 0 : 330);
  }
}

function collectForm() {
  const f = $('#req-form');
  const body = { name: f.name.value.trim(), role: f.role.value, request_type: currentType() };
  $$('.dyn', f).forEach((d) => {
    if (d.hidden || d.inert) return; // inert is set at once; the is-hidden class lags by two frames
    $$('input, select, textarea', d).forEach((inp) => {
      if (!inp.name) return;
      if (inp.type === 'radio') { if (inp.checked && inp.value !== '') body[inp.name] = +inp.value; return; }
      if (inp.type === 'checkbox') { body[inp.name] = inp.checked; return; }
      if (inp.type === 'range') { body[inp.name] = +inp.value; return; }
      if (inp.value !== '') body[inp.name] = inp.value;
    });
  });
  return body;
}

function fillForm(req) {
  const f = $('#req-form');
  clearForm(false);
  f.name.value = req.name || '';
  f.role.value = req.role || 'student';
  const radio = $(`input[name="request_type"][value="${req.request_type}"]`);
  if (radio) radio.checked = true;
  // No preferred slot in the scenario -> "None" (updateFields switches back to 2 where a slot is required)
  if (req.preferred_slot == null) $('input[name="preferred_slot"][value=""]').checked = true;
  for (const [k, v] of Object.entries(req)) {
    if (['name', 'role', 'request_type'].includes(k)) continue;
    const el = f.elements[k];
    if (!el) continue;
    if (el instanceof RadioNodeList) { const r = [...el].find((x) => x.value === String(v)); if (r) r.checked = true; continue; }
    if (el.type === 'checkbox') { el.checked = !!v; continue; }
    if (el.tagName === 'SELECT' && ![...el.options].some((o) => o.value === String(v))) {
      el.append(h('option', { value: v, 'data-temp': '' }, `${pretty(v)} (not on map)`));
    }
    el.value = v;
    if (el.type === 'range') syncRange(el);
  }
  updateFields();
}

function clearForm(resetType = true) {
  const f = $('#req-form');
  $$('option[data-temp]', f).forEach((o) => o.remove());
  f.name.value = '';
  f.current_location.value = ''; f.destination.value = ''; f.query.value = '';
  f.category.selectedIndex = 0; f.group_id.value = 'G4';
  $('input[name="preferred_slot"][value="2"]').checked = true;
  [['severity', 8], ['time_sensitivity', 9], ['crowd_level', 5]].forEach(([n, v]) => { f[n].value = v; syncRange(f[n]); });
  f.eligibility.checked = true; f.description_note.value = '';
  if (resetType) { $('input[name="request_type"]').checked = true; updateFields(); }
}

// A demo scenario first resets the bookings (request ids keep counting), like cli.py's
// demo mode, so it always gives its documented result. Manual requests use live bookings.
async function submitForm({ demo = false } = {}) {
  const body = collectForm();
  const btn = $('#submit-btn');
  btn.classList.add('is-busy');
  const ready = !demo || await safe(() => API.resetBookings(), 'Could not reset bookings');
  const res = ready ? await safe(() => API.submitRequest(body), 'Request failed') : null;
  btn.classList.remove('is-busy');
  $('#demo-select').value = '';
  if (!res) return;
  recordHistory(res, body);
  showResult(res, body);
}

/* ==========================================================================
   PIPELINE TRACKER
   ========================================================================== */
function buildPipeline() {
  const ol = $('#pipeline .pipe-nodes');
  ol.innerHTML = '';
  STAGES.forEach((st) => {
    ol.append(h('li', { class: `pnode mod-${st.mod}${st.key === 'eligible' ? ' diamond' : ''}`, 'data-key': st.key },
      h('div', { class: 'pnode-badge' }, icon(st.key, 'pnode-ico')),
      h('div', { class: 'pnode-label' }, st.label),
      h('div', { class: 'pnode-result' }),
      h('span', { class: 'pnode-tag' }, 'skipped'),
    ));
  });
  $$('.pnode-ico').forEach((i) => { i.replaceWith(i.firstChild); });
  window.addEventListener('resize', layoutPipeline);
  layoutPipeline();
}
const pnode = (key) => $(`.pnode[data-key="${key}"]`);
function badgeCenter(key) {
  const p = $('#pipeline').getBoundingClientRect();
  const r = $('.pnode-badge', pnode(key)).getBoundingClientRect();
  return { x: r.left + r.width / 2 - p.left, y: r.top + r.height / 2 - p.top };
}
function layoutPipeline() {
  if (!$('#pipeline').offsetParent) return;
  const a = badgeCenter('preprocessing'); const b = badgeCenter('final');
  const tr = $('.pipe-track');
  Object.assign(tr.style, { left: `${a.x}px`, width: `${b.x - a.x}px`, top: `${a.y - 1.5}px` });
  if (S.tokenAt) placeToken(S.tokenAt, true);
}
function placeToken(key, instant = false) {
  S.tokenAt = key;
  const tok = $('.pipe-token');
  const c = badgeCenter(key); const a = badgeCenter('preprocessing');
  if (instant) tok.style.transition = 'none';
  tok.style.transform = `translate(${c.x - 8}px, ${c.y - 8}px)`;
  $('.pipe-fill').style.width = `${Math.max(0, c.x - a.x)}px`;
  if (instant) { tok.getBoundingClientRect(); tok.style.transition = ''; }
}
function resetPipeline() {
  $$('.pnode').forEach((n) => {
    n.className = n.className.replace(/\b(current|done|rejected|skipped|unreached)\b/g, '').trim();
    $('.pnode-result', n).textContent = '';
  });
  const tok = $('.pipe-token');
  tok.className = 'pipe-token';
  $('.pipe-fill').classList.remove('is-rejected');
  $('#pipe-callout').hidden = true;
  S.tokenAt = null;
  $('.pipe-fill').style.width = '0px';
}

const normStage = (k) => {
  const x = String(k || '').toLowerCase();
  if (x.startsWith('logic') || x === 'kb' || x === 'eligibility') return 'logic';
  if (x.startsWith('pre')) return 'preprocessing';
  return x;
};

function stageSummary(key, res, info, body, pipe) {
  const i = info[key];
  const rejectedAt = res.decision === 'rejected' ? normStage(res.rejected_at) : null;
  switch (key) {
    case 'preprocessing':
      if (rejectedAt === 'preprocessing') return { text: i?.summary || (res.errors || [])[0] || 'invalid input', status: 'rejected' };
      return { text: i?.summary || 'validated' };
    case 'router': return { text: pipe.length ? `${pipe.length} module${pipe.length > 1 ? 's' : ''}` : 'none' };
    case 'ann': return { text: i?.summary || (res.priority ? `${res.priority.final_priority} (${fmtNum(res.priority.confidence)})` : 'done') };
    case 'logic': return { text: i?.summary || (res.eligibility ? (res.eligibility.allowed ? 'allowed' : 'not allowed') : 'done') };
    case 'eligible':
      if (body.request_type === 'Eligibility_Check') return { text: res.eligibility?.allowed ? 'yes · entailed' : 'no · not entailed' };
      return res.eligibility?.allowed === false ? { text: 'no', status: 'rejected' } : { text: 'yes' };
    case 'csp':
      if (rejectedAt === 'csp') return { text: i?.summary || 'no feasible slot', status: 'rejected' };
      return { text: i?.summary || (res.assignment ? `${pretty(res.assignment.room)} slot ${res.assignment.slot}` : 'done') };
    case 'search': return { text: i?.summary || (res.route ? `${res.route.algorithm} cost ${res.route.cost}` : 'done') };
    case 'final': return { text: res.decision, status: res.decision === 'rejected' ? 'rejected' : 'ok' };
    default: return { text: i?.summary || '' };
  }
}

async function runPipeline(res, body) {
  const run = ++S.runs.pipe;
  layoutPipeline();
  resetPipeline();
  const pipe = res.trace?.pipeline ?? (res.rejected_at === 'preprocessing' ? [] : TYPE_PIPE[body.request_type] || []);
  const info = {};
  (res.trace?.stages || []).forEach((st) => { info[normStage(st.stage)] = st; });
  const rejectedAt = res.decision === 'rejected' ? normStage(res.rejected_at) : null;
  const stopKey = rejectedAt === 'logic' ? 'eligible' : rejectedAt;
  const active = STAGES.filter((st) => !st.pipe || pipe.includes(st.pipe));
  STAGES.forEach((st) => { if (!active.includes(st)) pnode(st.key).classList.add('skipped'); });

  const modNames = pipe.map((p) => pretty(p).replace('Logic KB', 'Logic/KB'));
  $('#pipe-meta').innerHTML = '';
  $('#pipe-meta').append(h('b', {}, res.request_id), ` · ${pretty(body.request_type)} · router selected `,
    h('b', {}, modNames.length ? modNames.join(' → ') : 'nothing (stopped at validation)'));
  $('#pipe-replay').disabled = false;

  const tok = $('.pipe-token');
  placeToken('preprocessing', true);
  tok.classList.add('on');
  await sleep(200);

  for (const st of active) {
    if (run !== S.runs.pipe) return;
    const node = pnode(st.key);
    placeToken(st.key);
    node.classList.add('current');
    await sleep(560);
    if (run !== S.runs.pipe) return;
    const { text, status } = stageSummary(st.key, res, info, body, pipe);
    node.classList.remove('current');
    node.classList.add(status === 'rejected' ? 'rejected' : 'done');
    $('.pnode-result', node).textContent = text;
    if (info[st.key]?.notes && status !== 'rejected') showCallout('note', `${st.label} note`, info[st.key].notes);
    if (st.key === stopKey) {
      tok.classList.add('rejected');
      $('.pipe-fill').classList.add('is-rejected');
      active.slice(active.indexOf(st) + 1).forEach((r) => pnode(r.key).classList.add('unreached'));
      const reason = res.eligibility?.explanation && rejectedAt === 'logic' ? res.eligibility.explanation
        : info[st.key]?.notes || (res.errors || []).join('; ') || res.message;
      showCallout('bad', `Rejected at ${st.key === 'eligible' ? 'eligibility check' : st.label}`, reason);
      return;
    }
    await sleep(160);
  }
  if (run !== S.runs.pipe) return;
  tok.classList.add(res.decision === 'rejected' ? 'rejected' : 'arrived');
  if (res.decision === 'rejected' && $('#pipe-callout').hidden) showCallout('bad', 'Rejected', res.message);
}
function showCallout(kind, title, text) {
  const c = $('#pipe-callout');
  c.className = `pipe-callout ${kind}`;
  c.innerHTML = '';
  c.append(h('strong', {}, `${title}:`), h('span', {}, text));
  c.hidden = false;
}

/* ==========================================================================
   RESULT PANEL
   ========================================================================== */
const DEC_LABEL = { accepted: 'Accepted', completed: 'Completed', answered: 'Answered', rejected: 'Rejected' };

function showResult(res, body) {
  S.current = { res, body };
  renderResult(res, body);
  go('console');
  $('#pipeline').scrollIntoView({ behavior: reducedMotion.matches ? 'auto' : 'smooth', block: 'center' });
  runPipeline(res, body);
}

function rcard(mod, title, modName, content, link, emptyNote) {
  const card = h('article', { class: `card rcard${content ? '' : ' is-empty'}`, style: { '--mod': `var(--${mod})` } },
    h('div', { class: 'rcard-head' }, h('span', { class: 'dot' }), h('h4', {}, title), modName && h('span', { class: 'mod-tag' }, modName)));
  if (content) card.append(...[].concat(content).filter((c) => c != null && c !== false));
  else card.append(h('p', { class: 'empty-note' }, emptyNote));
  if (content && link) card.append(h('button', { type: 'button', class: 'link-btn', onclick: link.fn }, link.label, icon('link')));
  return card;
}

function renderResult(res, body) {
  const box = $('#result');
  box.innerHTML = '';
  const bad = res.decision === 'rejected';
  box.append(h('div', { class: `banner${bad ? ' bad' : ''}` },
    h('div', { class: 'banner-icon' }, icon(bad ? 'x' : 'check')),
    h('div', {},
      h('div', { class: 'banner-kicker' }, `${res.request_id} · ${pretty(body.request_type)} · ${body.name || 'anonymous'} (${body.role})`),
      h('div', { class: 'banner-title' }, DEC_LABEL[res.decision] || res.decision),
      h('p', { class: 'banner-msg' }, res.message)),
    bad && res.rejected_at ? h('span', { class: 'banner-stage' }, `Stopped at ${pretty(res.rejected_at)}`) : null,
  ));

  const pipe = res.trace?.pipeline ?? TYPE_PIPE[body.request_type] ?? [];
  const skipped = (m) => (pipe.includes(m) ? 'Not reached: the request stopped earlier in the pipeline.' : 'Skipped: the router did not select this module for this request type.');
  const grid = h('div', { class: 'result-grid' });

  // Priority
  const p = res.priority;
  grid.append(rcard('ann', 'Priority', 'ANN', p && [
    h('div', { class: 'kv' },
      h('span', {}, 'Final (MLP) ', h('span', { class: `pchip p-${p.final_priority}` }, p.final_priority)),
      h('span', {}, 'Binary (perceptron) ', h('span', { class: `pchip p-${p.binary_priority === 'urgent' ? 'urgent' : 'low'}` }, pretty(p.binary_priority)))),
    h('div', { class: 'sub-val' }, `Confidence ${fmtNum(p.confidence)}`),
    h('div', { class: 'meter' }, h('i', { 'data-w': `${Math.round((p.confidence || 0) * 100)}%` })),
    p.probabilities ? h('div', { class: 'mini-probs' }, ...['low', 'normal', 'high', 'urgent'].flatMap((k) => [
      h('span', {}, cap(k)),
      h('span', { class: `bar${k === p.final_priority ? ' top' : ''}` }, h('i', { 'data-w': `${(p.probabilities[k] || 0) * 100}%` })),
      h('span', { class: 'num' }, fmtNum(p.probabilities[k] || 0))])) : null,
  ], { label: 'View in ANN priority', fn: () => openANN(res, body) }, skipped('ANN')));

  // Eligibility
  const e = res.eligibility;
  grid.append(rcard('logic', 'Eligibility', 'Logic / KB', e && [
    h('div', { class: `big-val ${e.allowed ? 'yes' : 'no'}` }, body.request_type === 'Eligibility_Check' ? (e.allowed ? 'Entailed' : 'Not entailed') : (e.allowed ? 'Allowed' : 'Not allowed')),
    e.query ? h('div', { class: 'code-line' }, e.query) : null,
    e.explanation ? h('p', { class: 'sub-val' }, e.explanation) : null,
    e.missing && e.missing.length ? h('div', { class: 'kv' }, 'Missing premise: ', ...e.missing.map((m) => h('span', { class: 'missing-chip' }, m))) : null,
    e.answers && e.answers.length ? h('div', { class: 'kv' }, 'Answers: ', ...e.answers.map((a) => h('b', { class: 'mono' }, a))) : null,
  ], (e && (e.query || body.query)) ? { label: 'View proof in Knowledge base', fn: () => openKB(e.query || body.query) } : null, skipped('Logic_KB')));

  // Assignment
  const a = res.assignment;
  grid.append(rcard('csp', 'Assignment', 'CSP', a && [
    h('div', { class: 'big-val' }, pretty(a.room)),
    h('div', { class: 'kv' },
      h('span', {}, 'Slot ', h('b', {}, `${a.slot} · ${SLOT_TIMES[a.slot]}`)),
      a.preferred_slot && a.preferred_slot !== a.slot ? h('span', {}, 'Preferred ', h('b', { class: 'slot-struck' }, `slot ${a.preferred_slot}`)) : null,
      a.priority ? h('span', {}, 'Deadline ', h('b', {}, `≤ slot ${a.deadline ?? DEADLINE[a.priority]}`)) : null),
    a.notes ? h('p', { class: 'sub-val' }, a.notes) : null,
  ], { label: 'View in Scheduling / CSP', fn: () => openCSP(res) }, skipped('CSP')));

  // Route
  const r = res.route;
  let routeContent = null;
  if (r && r.path && r.path.length) {
    const svg = s('svg', { class: 'mini-map', role: 'img', 'aria-label': `Route ${r.path.join(' to ')}` });
    const refs = drawCampus(svg, { mini: true });
    markEnds(refs, r.path[0], r.path[r.path.length - 1]);
    drawPath(refs, r.path, null, true);
    routeContent = [
      svg,
      h('div', { class: 'kv' }, h('span', {}, 'Algorithm ', h('b', {}, r.algorithm)), h('span', {}, 'Cost ', h('b', {}, r.cost)), h('span', {}, 'Steps ', h('b', {}, r.steps ?? r.path.length - 1))),
      h('div', { class: 'sub-val mono' }, r.path.map(pretty).join(' → ')),
    ];
  }
  grid.append(rcard('search', 'Route', 'Search', routeContent,
    { label: 'View in Campus map', fn: () => openMap(r.path[0], r.path[r.path.length - 1]) }, skipped('Search')));

  // Message
  grid.append(rcard('core', 'Message', null, [
    h('p', {}, res.message),
    body.description_note ? h('p', { class: 'sub-val' }, `Note: ${body.description_note}`) : null,
  ]));

  // Raw JSON
  const pre = h('pre', {});
  pre.innerHTML = highlightJSON(res);
  grid.append(h('article', { class: 'card rcard wide' }, h('details', { class: 'raw-json' }, h('summary', {}, 'Raw JSON response'), pre)));

  box.append(grid);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    $$('[data-w]', box).forEach((i) => { i.style.width = i.dataset.w; });
  }));
}

function highlightJSON(obj) {
  const esc = JSON.stringify(obj, null, 2).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return esc.replace(/("(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g, (m) => {
    let c = 'json-num';
    if (/^"/.test(m)) c = /:$/.test(m) ? 'json-key' : 'json-str';
    else if (/true|false|null/.test(m)) c = 'json-bool';
    return `<span class="${c}">${m}</span>`;
  });
}

function flash(el) {
  if (!el) return;
  el.classList.remove('flash-hl'); void el.offsetWidth; el.classList.add('flash-hl');
  setTimeout(() => el.classList.remove('flash-hl'), 1700);
}

/* ---------- "View in <module>" ---------- */
function openMap(src, dst) {
  go('map');
  if (S.pos[src]) S.mapSrc = src;
  if (S.pos[dst]) S.mapDst = dst;
  $('input[name="graph-mode"][value="weighted-h"]').checked = true;
  syncMapControls();
  flash($('.map-card'));
  setTimeout(runMapSearch, 300);
}
function openKB(query) {
  go('kb');
  $('#kb-query').value = query;
  flash($('.query-card'));
  setTimeout(() => $('#kb-form').requestSubmit(), 250);
}
function openCSP(res) {
  S.cspAnimating = true;
  go('csp');
  S.cspAnimating = false;
  flash($('.booking-card'));
  setTimeout(() => animateBooking(res.assignment, res.request_id), 300);
}
function openANN(res, body) {
  go('ann');
  const feats = res.priority?.features || [
    ROLE_IDX[body.role] ?? 0, Math.max(0, CATEGORIES.indexOf(body.category)),
    body.severity ?? 5, body.time_sensitivity ?? 5, body.crowd_level ?? 5, res.route?.cost ?? 0, body.eligibility ? 1 : 0,
  ];
  setAnnInputs(feats);
  flash($('.ann-net-card'));
  setTimeout(() => $('#ann-form').requestSubmit(), 250);
}

/* ==========================================================================
   HISTORY
   ========================================================================== */
function recordHistory(res, body) {
  S.history.unshift({ res, body, time: new Date() });
  renderHistory();
  const c = $('#history-counter');
  c.classList.remove('bump'); void c.offsetWidth; c.classList.add('bump');
}
function renderHistory() {
  const n = S.history.length;
  $('#hist-count').textContent = n;
  $('#nav-count').textContent = n;
  const tl = $('#timeline');
  tl.innerHTML = '';
  $('#timeline-empty').hidden = n > 0;
  S.history.forEach((it) => {
    const bad = it.res.decision === 'rejected';
    const pipe = it.res.trace?.pipeline ?? TYPE_PIPE[it.body.request_type] ?? [];
    tl.append(h('li', {}, h('button', {
      type: 'button', class: `t-item${bad ? ' bad' : ''}`,
      onclick: () => showResult(it.res, it.body),
      'aria-label': `Open ${it.res.request_id}, ${pretty(it.body.request_type)}, ${it.res.decision}`,
    },
    h('span', { class: 't-dot' }),
    h('span', { class: 't-id' }, it.res.request_id),
    h('span', { class: 't-main' }, h('b', {}, `${pretty(it.body.request_type)} · ${it.body.name || 'anonymous'}`), h('span', {}, it.res.message)),
    h('span', { class: 't-mods', title: pipe.map(pretty).join(', ') }, pipe.map((m) => h('i', { style: { '--c': `var(${MOD_VAR[m]})` } }))),
    h('span', { style: { display: 'flex', gap: '12px', alignItems: 'center' } },
      h('span', { class: `dec-chip${bad ? ' bad' : ''}` }, it.res.decision),
      h('span', { class: 't-time' }, it.time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }))),
    )));
  });
}

/* ==========================================================================
   CAMPUS MAP & SEARCH
   ========================================================================== */
const MX = (x) => 60 + x * 82;
const MY = (y) => 46 + (5 - y) * 82;
const ekey = (a, b) => [a, b].sort().join('|');

function drawCampus(svg, { interactive = false, mini = false } = {}) {
  svg.innerHTML = '';
  svg.setAttribute('viewBox', '0 0 940 500');
  svg.classList.add('campus-map');
  if (interactive) svg.classList.add('interactive');
  const gE = s('g', { class: 'edges' }, svg);
  const gP = s('g', { class: 'path-layer' }, svg);
  const gN = s('g', { class: 'nodes' }, svg);
  const refs = { svg, gP, nodes: {}, edges: {} };
  for (const e of S.graph.edges) {
    const a = S.pos[e.a]; const b = S.pos[e.b];
    const g = s('g', { class: 'edge' }, gE);
    s('line', { x1: MX(a.x), y1: MY(a.y), x2: MX(b.x), y2: MY(b.y) }, g);
    if (!mini) s('text', { class: 'edge-cost', x: (MX(a.x) + MX(b.x)) / 2, y: (MY(a.y) + MY(b.y)) / 2 + 4.5, text: e.cost }, g);
    refs.edges[ekey(e.a, e.b)] = g;
  }
  for (const n of S.graph.nodes) {
    const g = s('g', { class: 'node', transform: `translate(${MX(n.x)},${MY(n.y)})`, 'data-name': n.name }, gN);
    s('circle', { class: 'node-ring', r: mini ? 15 : 21 }, g);
    s('circle', { class: 'node-dot', r: mini ? 10 : 13 }, g);
    const above = n.y === 5 || n.name === 'Medical_Center';
    s('text', { class: 'node-label', y: above ? (mini ? -22 : -26) : (mini ? 32 : 36), text: pretty(n.name), style: mini ? 'font-size:25px' : null }, g);
    if (!mini) s('text', { class: 'node-h', y: above ? -42 : 51, 'data-h': '' }, g);
    if (interactive) {
      g.setAttribute('tabindex', '0'); g.setAttribute('role', 'button');
      g.setAttribute('aria-label', pretty(n.name));
      g.addEventListener('click', () => pickNode(n.name));
      g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pickNode(n.name); } });
    }
    refs.nodes[n.name] = g;
  }
  return refs;
}

function clearMapState(refs) {
  Object.values(refs.nodes).forEach((g) => g.classList.remove('frontier', 'explored', 'current', 'on-path', 'is-source', 'is-goal'));
  refs.gP.innerHTML = '';
}
function markEnds(refs, src, dst) {
  refs.nodes[src]?.classList.add('is-source');
  refs.nodes[dst]?.classList.add('is-goal');
}
async function drawPath(refs, path, run, instant = false) {
  refs.gP.innerHTML = '';
  for (let i = 1; i < path.length; i++) {
    const a = S.pos[path[i - 1]]; const b = S.pos[path[i]];
    if (!a || !b) continue;
    const ln = s('line', { class: 'path-seg', x1: MX(a.x), y1: MY(a.y), x2: MX(b.x), y2: MY(b.y) }, refs.gP);
    const L = Math.hypot(MX(a.x) - MX(b.x), MY(a.y) - MY(b.y));
    refs.nodes[path[i - 1]]?.classList.add('on-path');
    if (instant) continue;
    ln.style.strokeDasharray = L; ln.style.strokeDashoffset = L;
    ln.getBoundingClientRect();
    const dur = Math.max(260, L * 1.6) * mapSpeed();
    ln.style.transition = `stroke-dashoffset ${dur}ms cubic-bezier(.4,0,.2,1)`;
    ln.style.strokeDashoffset = 0;
    await sleep(dur);
    if (run != null && run !== S.runs.map) return;
  }
  refs.nodes[path[path.length - 1]]?.classList.add('on-path');
}
const mapSpeed = () => +$('#m-speed').value || 1;

function buildMap() {
  S.mapRefs = drawCampus($('#campus-map'), { interactive: true });
  $('#k-val').textContent = Math.abs(S.graph.heuristic_k - 1 / 3) < 0.01 ? '1/3' : S.graph.heuristic_k;
  $('#m-src').addEventListener('change', (e) => { S.mapSrc = e.target.value; syncMapControls(); });
  $('#m-dst').addEventListener('change', (e) => { S.mapDst = e.target.value; syncMapControls(); });
  $('#m-swap').addEventListener('click', () => { [S.mapSrc, S.mapDst] = [S.mapDst, S.mapSrc]; syncMapControls(); });
  $$('input[name="graph-mode"]').forEach((r) => r.addEventListener('change', syncMapControls));
  $('#m-run').addEventListener('click', runMapSearch);
  $('#cmp-run').addEventListener('click', runCompare);
  syncMapControls();
}

const POLICY = {
  unweighted: { algo: 'BFS', why: 'Unweighted graph: every edge counts as one step, so breadth-first search returns the path with the fewest steps.' },
  'weighted-h': { algo: 'A*', why: 'Weighted graph with an admissible heuristic available, so A* finds the cheapest path while expanding fewer nodes.' },
  weighted: { algo: 'UCS', why: 'Weighted graph but no heuristic, so uniform-cost search expands by path cost g(n) and still guarantees the cheapest path.' },
};
const graphMode = () => $('input[name="graph-mode"]:checked').value;

function syncMapControls() {
  $('#m-src').value = S.mapSrc; $('#m-dst').value = S.mapDst;
  const mode = graphMode();
  const pol = POLICY[mode];
  const el = $('#policy-algo');
  if (el.textContent !== pol.algo) { el.textContent = pol.algo; el.classList.remove('swap'); void el.offsetWidth; el.classList.add('swap'); }
  $('#policy-why').textContent = pol.why;
  $('#campus-map').classList.toggle('unweighted', mode === 'unweighted');
  S.runs.map++;
  clearMapState(S.mapRefs);
  markEnds(S.mapRefs, S.mapSrc, S.mapDst);
  // live heuristic values towards the goal
  const goal = S.pos[S.mapDst]; const k = S.graph.heuristic_k;
  $$('[data-h]', S.mapRefs.svg).forEach((t) => {
    const n = S.pos[t.parentNode.dataset.name];
    const hv = k * Math.hypot(n.x - goal.x, n.y - goal.y);
    t.textContent = mode === 'weighted-h' ? `h=${hv.toFixed(2)}` : '';
  });
  $('#h-live').textContent = mode === 'weighted-h' ? `Small grey numbers on the map show h(n) towards ${pretty(S.mapDst)}.` : '';
  $('#map-hint').textContent = `Source: ${pretty(S.mapSrc)} · Destination: ${pretty(S.mapDst)}. Click nodes to change (next click sets the ${S.pickNext}).`;
  $('#cmp-sub').textContent = `${pretty(S.mapSrc)} → ${pretty(S.mapDst)}, weighted graph.`;
  $('#exp-strip').innerHTML = '';
  ['#st-cost', '#st-steps', '#st-exp'].forEach((id) => { $(id).textContent = '–'; });
  $('#st-path').textContent = '';
}

function pickNode(name) {
  if (S.pickNext === 'source') { S.mapSrc = name; S.pickNext = 'destination'; }
  else { if (name === S.mapSrc) return; S.mapDst = name; S.pickNext = 'source'; }
  syncMapControls();
}

async function runMapSearch() {
  if (S.mapSrc === S.mapDst) { toast('Pick two different locations.'); return; }
  const mode = graphMode();
  const res = await safe(() => API.search({
    source: S.mapSrc, destination: S.mapDst,
    graph_type: mode === 'unweighted' ? 'unweighted' : 'weighted',
    heuristic_available: mode === 'weighted-h',
  }), 'Search failed');
  if (!res) return;
  $$('.cmp-table tr.is-playing').forEach((r) => r.classList.remove('is-playing'));
  animateSearch({ found: true, ...res });
}

async function animateSearch(result) {
  const run = ++S.runs.map;
  const refs = S.mapRefs;
  clearMapState(refs);
  const src = S.mapSrc; const dst = S.mapDst;
  markEnds(refs, src, dst);
  const strip = $('#exp-strip'); strip.innerHTML = '';
  $('#policy-algo').textContent = result.algorithm_used;
  $('#st-cost').textContent = '…'; $('#st-steps').textContent = '…'; $('#st-exp').textContent = '0';
  $('#st-path').textContent = '';
  const explored = new Set();
  const order = result.expanded_order || [];
  const delay = Math.max(140, Math.min(420, 4200 / Math.max(order.length, 1))) * mapSpeed();
  for (let i = 0; i < order.length; i++) {
    if (run !== S.runs.map) return;
    const n = order[i]; const g = refs.nodes[n];
    if (!g) continue;
    Object.values(refs.nodes).forEach((x) => x.classList.remove('current'));
    g.classList.remove('frontier');
    g.classList.add('explored', 'current');
    explored.add(n);
    (S.adj[n] || []).forEach((m) => { if (!explored.has(m)) refs.nodes[m].classList.add('frontier'); });
    strip.append(h('li', { class: 'exp-chip' }, h('b', {}, i + 1), pretty(n)));
    strip.scrollLeft = strip.scrollWidth;
    $('#st-exp').textContent = i + 1;
    await sleep(delay);
  }
  if (run !== S.runs.map) return;
  Object.values(refs.nodes).forEach((x) => x.classList.remove('current'));
  if (result.found !== false && result.path && result.path.length) {
    await drawPath(refs, result.path, run);
    if (run !== S.runs.map) return;
    $('#st-cost').textContent = result.cost; $('#st-steps').textContent = result.steps;
    $('#st-path').textContent = result.path.map(pretty).join(' → ');
  } else {
    $('#st-cost').textContent = '∞'; $('#st-steps').textContent = '–';
    $('#st-path').textContent = 'No path found within the limit.';
  }
  $('#st-exp').textContent = result.nodes_expanded ?? order.length;
}

async function runCompare() {
  if (S.mapSrc === S.mapDst) { toast('Pick two different locations.'); return; }
  const lim = Math.max(1, Math.min(12, +$('#dls-limit').value || 3));
  const btn = $('#cmp-run'); btn.classList.add('is-busy');
  const rows = await safe(() => API.compare({ source: S.mapSrc, destination: S.mapDst, dls_limit: lim }), 'Compare failed');
  btn.classList.remove('is-busy');
  if (!rows) return;
  const found = rows.filter((r) => r.found && r.cost != null);
  const best = found.length ? Math.min(...found.map((r) => r.cost)) : null;
  const body = $('#cmp-body'); body.innerHTML = '';

  const tbody = h('tbody');
  rows.forEach((r, i) => {
    const opt = r.found && r.cost === best;
    const tr = h('tr', {
      class: opt ? 'optimal' : '', tabindex: '0', style: { animationDelay: `${i * 40}ms` },
      'aria-label': `Replay ${r.algorithm_used}`,
    },
    h('td', {}, h('b', {}, r.algorithm_used === 'DLS' ? `DLS (limit ${lim})` : r.algorithm_used), opt ? h('span', { class: 'opt-badge' }, 'optimal') : null),
    h('td', {}, r.found ? h('span', { class: 'yes' }, 'yes') : h('span', { class: 'no' }, 'no')),
    h('td', { class: 'cmp-path' }, r.found ? r.path.map(pretty).join(' → ') : '–'),
    h('td', { class: 'num' }, r.found ? r.cost : '–'),
    h('td', { class: 'num' }, r.found ? r.steps : '–'),
    h('td', { class: 'num' }, r.nodes_expanded),
    h('td', { class: 'num' }, fmtNum(r.time_ms, 3)));
    const play = () => {
      $$('tr.is-playing', tbody).forEach((x) => x.classList.remove('is-playing'));
      tr.classList.add('is-playing');
      $('.map-card').scrollIntoView({ behavior: reducedMotion.matches ? 'auto' : 'smooth', block: 'start' });
      setTimeout(() => animateSearch(r), 250);
    };
    tr.addEventListener('click', play);
    tr.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); play(); } });
    tbody.append(tr);
  });
  body.append(h('div', { class: 'cmp-table-wrap' }, h('table', { class: 'cmp-table' },
    h('thead', {}, h('tr', {}, h('th', {}, 'Algorithm'), h('th', {}, 'Found'), h('th', {}, 'Path'), h('th', { class: 'num' }, 'Cost'), h('th', { class: 'num' }, 'Steps'), h('th', { class: 'num' }, 'Expanded'), h('th', { class: 'num' }, 'ms'))),
    tbody)));

  const charts = h('div', { class: 'charts' },
    hbarChart('Nodes expanded (lower is better)', rows.map((r) => ({ label: r.algorithm_used, value: r.nodes_expanded, hl: r.found && r.cost === best }))),
    hbarChart('Path cost (lower is better; blue = optimal)', rows.map((r) => ({ label: r.algorithm_used, value: r.found ? r.cost : null, hl: r.found && r.cost === best }))));
  body.append(charts);
  requestAnimationFrame(() => requestAnimationFrame(() => $$('[data-w]', body).forEach((i) => { i.style.width = i.dataset.w; })));
}

function hbarChart(title, items) {
  const max = Math.max(1, ...items.map((i) => i.value || 0));
  return h('div', { class: 'hbar-chart' }, h('h4', {}, title),
    ...items.map((it) => h('div', { class: `hbar${it.hl ? ' hl' : ''}` },
      h('span', { class: 'lbl', title: it.label }, it.label),
      h('span', { class: 'track' }, h('i', { 'data-w': `${((it.value || 0) / max) * 100}%` })),
      h('span', { class: 'val' }, it.value == null ? '–' : it.value))));
}

/* ==========================================================================
   SCHEDULING / CSP
   ========================================================================== */
async function refreshBookings(hide) {
  const list = await safe(() => API.bookings(), 'Could not load bookings');
  if (list) renderBookings(list, hide);
  return list;
}
function renderBookings(list, hide) {
  const g = $('#booking-grid');
  g.innerHTML = '';
  g.append(h('div', { class: 'bg-head', style: { textAlign: 'left' } }, 'Room'));
  [1, 2, 3, 4].forEach((sl) => g.append(h('div', { class: 'bg-head' }, h('b', {}, `Slot ${sl}`), SLOT_TIMES[sl])));
  ROOMS.forEach((room) => {
    g.append(h('div', { class: 'bg-room', 'data-room-label': room }, pretty(room)));
    [1, 2, 3, 4].forEach((sl) => {
      const bk = list.find((b) => b.room === room && b.slot === sl && !(hide && hide.room === room && hide.slot === sl));
      g.append(h('div', { class: `cell${bk ? ' booked' : ''}`, 'data-room': room, 'data-slot': sl },
        bk ? h('span', { class: 'who' }, bk.request_id || 'Booked') : 'free'));
    });
  });
}
const cellEl = (room, slot) => $(`.cell[data-room="${room}"][data-slot="${slot}"]`);

async function animateBooking(a, reqId) {
  if (!a) return;
  const run = ++S.runs.csp;
  await refreshBookings(a);
  if (run !== S.runs.csp) return;
  const dl = a.deadline ?? DEADLINE[a.priority] ?? 4;
  [1, 2, 3, 4].forEach((sl) => { if (sl > dl) cellEl(a.room, sl).classList.add('past-deadline'); });
  $(`[data-room-label="${a.room}"]`).classList.add('row-hl');
  const note = $('#csp-note');
  note.hidden = false; note.innerHTML = '';
  note.append(h('strong', {}, `${reqId}: `), `${pretty(a.priority || 'normal')} priority, so the deadline is slot ${dl}. `);

  const wrap = $('.booking-wrap');
  const tok = $('#booking-token');
  const startSlot = a.preferred_slot || a.slot;
  const place = (cell, instant) => {
    const wr = wrap.getBoundingClientRect(); const cr = cell.getBoundingClientRect();
    if (instant) tok.style.transition = 'none';
    tok.style.width = `${cr.width}px`;
    tok.style.transform = `translate(${cr.left - wr.left}px, ${cr.top - wr.top}px)`;
    if (instant) { tok.getBoundingClientRect(); tok.style.transition = ''; }
  };
  tok.textContent = reqId; tok.hidden = false; tok.style.opacity = '1';
  place(cellEl(a.room, startSlot), true);
  cellEl(a.room, startSlot).scrollIntoView({ behavior: reducedMotion.matches ? 'auto' : 'smooth', block: 'center' });
  await sleep(650);
  if (run !== S.runs.csp) return;

  if (a.preferred_slot && a.preferred_slot !== a.slot) {
    const pc = cellEl(a.room, a.preferred_slot);
    pc.classList.add('flash-conflict');
    pc.append(h('span', { class: 'tag' }, a.preferred_slot > dl ? 'past deadline' : 'taken'));
    if (!a.notes) note.append(`Preferred slot ${a.preferred_slot} ${a.preferred_slot > dl ? 'violates the deadline' : 'is already booked'}. `);
    await sleep(900);
    if (run !== S.runs.csp) return;
  }
  place(cellEl(a.room, a.slot));
  await sleep(720);
  if (run !== S.runs.csp) return;
  const c = cellEl(a.room, a.slot);
  c.className = 'cell booked just-booked';
  c.innerHTML = '';
  c.append(h('span', { class: 'who' }, reqId));
  tok.style.opacity = '0';
  setTimeout(() => { tok.hidden = true; }, 300);
  note.append(h('span', {}, a.notes || `Assigned ${pretty(a.room)} slot ${a.slot}.`));
}

function buildCSP() {
  $('#try-booking').addEventListener('submit', async (e) => {
    e.preventDefault();
    // DrKhan (instructor) may request every non-viva category in the KB (R9, R13, R14, R15).
    const body = { name: 'DrKhan', role: 'instructor', request_type: 'Booking_or_Scheduling', category: $('#tb-cat').value, preferred_slot: +$('#tb-slot').value };
    const res = await safe(() => API.submitRequest(body), 'Booking failed');
    if (!res) return;
    recordHistory(res, body);
    S.current = { res, body };
    renderResult(res, body);
    if (res.assignment) animateBooking(res.assignment, res.request_id);
    else {
      const note = $('#csp-note'); note.hidden = false; note.innerHTML = '';
      note.append(h('strong', {}, `${res.request_id} rejected: `), res.message);
      refreshBookings();
    }
  });
  buildViva();
}

/* ---------- Viva constraint graph ---------- */
const VIVA_POS = { G2: [270, 48], G1: [120, 150], G4: [270, 196], G5: [420, 150], G3: [270, 330], G6: [460, 306] };
const VIVA_EDGES = [
  ['G1', 'G2', 'examiner'], ['G1', 'G4', 'examiner'], ['G1', 'G3', 'examiner'],
  ['G2', 'G4', 'supervisor'], ['G2', 'G5', 'supervisor'],
  ['G3', 'G5', 'other'], ['G3', 'G6', 'other'], ['G5', 'G6', 'other'],
];
const VIVA_PREC = [['G4', 'G3']];
const SLOT_COLORS = { 1: '#2dd4bf', 2: '#fbbf24', 3: '#f472b6', 4: '#a5b4fc' };
const vivaRefs = { nodes: {}, edges: {} };

function buildViva() {
  const svg = $('#viva-graph');
  svg.innerHTML = '';
  const defs = s('defs', {}, svg);
  const mk = s('marker', { id: 'arrow-prec', viewBox: '0 0 10 10', refX: '9', refY: '5', markerWidth: '7', markerHeight: '7', orient: 'auto-start-reverse' }, defs);
  s('path', { d: 'M0 0L10 5L0 10z', fill: 'var(--warn)' }, mk);
  const gE = s('g', {}, svg); const gN = s('g', {}, svg);
  VIVA_EDGES.forEach(([a, b, kind]) => {
    const [x1, y1] = VIVA_POS[a]; const [x2, y2] = VIVA_POS[b];
    vivaRefs.edges[ekey(a, b)] = s('line', { class: `v-edge ${kind}`, x1, y1, x2, y2 }, gE);
  });
  VIVA_PREC.forEach(([a, b]) => {
    const [x1, y1] = VIVA_POS[a]; const [x2, y2] = VIVA_POS[b];
    const len = Math.hypot(x2 - x1, y2 - y1); const ux = (x2 - x1) / len; const uy = (y2 - y1) / len;
    const ox = -uy * 14; const oy = ux * 14; // offset so it does not sit on top of any other edge
    vivaRefs.edges[`prec|${a}|${b}`] = s('line', {
      class: 'v-edge prec', x1: x1 + ux * 30 + ox, y1: y1 + uy * 30 + oy, x2: x2 - ux * 32 + ox, y2: y2 - uy * 32 + oy, 'marker-end': 'url(#arrow-prec)',
    }, gE);
    s('text', { x: (x1 + x2) / 2 + ox + 10, y: (y1 + y2) / 2 + oy, class: 'a-label', style: 'font-size:11.5px;fill:var(--warn)', text: 'before' }, gE);
  });
  Object.entries(VIVA_POS).forEach(([g, [x, y]]) => {
    const node = s('g', { class: 'v-node', transform: `translate(${x},${y})` }, gN);
    s('circle', { r: 26 }, node);
    s('text', { class: 'v-name', y: -1, text: g }, node);
    s('text', { class: 'v-slot', y: 40, text: '' }, node);
    vivaRefs.nodes[g] = node;
  });
  const key = $('#slot-key'); key.innerHTML = '';
  [1, 2, 3, 4].forEach((sl) => key.append(h('span', { style: { '--slot': SLOT_COLORS[sl] } }, h('i'), `S${sl} · ${SLOT_TIMES[sl]}`)));
  $('#viva-solve').addEventListener('click', solveViva);
}

function vivaReset() {
  Object.values(vivaRefs.nodes).forEach((n) => { n.setAttribute('class', 'v-node'); n.style.removeProperty('--slot'); $('.v-slot', n).textContent = ''; });
  Object.values(vivaRefs.edges).forEach((e) => e.classList.remove('clash'));
}

function vivaReasons(g, upTo, asg) {
  const out = [];
  for (let u = 1; u < upTo; u++) {
    const nb = VIVA_EDGES.find(([a, b]) => (a === g || b === g) && asg[a === g ? b : a] === u);
    if (nb) { const o = nb[0] === g ? nb[1] : nb[0]; out.push({ slot: u, other: o, edge: ekey(g, o), why: `${nb[2]} clash with ${o}` }); continue; }
    const pr = VIVA_PREC.find(([a, b]) => (a === g && asg[b] !== undefined && u >= asg[b]) || (b === g && asg[a] !== undefined && u <= asg[a]));
    if (pr) { const o = pr[0] === g ? pr[1] : pr[0]; out.push({ slot: u, other: o, edge: `prec|${pr[0]}|${pr[1]}`, why: `${pr[0]} must be before ${pr[1]}` }); }
  }
  return out;
}

async function solveViva() {
  const run = ++S.runs.viva;
  const btn = $('#viva-solve'); btn.classList.add('is-busy');
  const res = await safe(() => API.solveViva(), 'Viva solver failed');
  btn.classList.remove('is-busy');
  if (!res) return;
  vivaReset();
  const log = $('#viva-log'); log.innerHTML = '';
  $('#viva-table').innerHTML = '';
  $('#viva-tried').textContent = '…'; $('#viva-bt').textContent = '0';
  const asg = {}; let bts = 0;
  const addLog = (text, cls) => { log.append(h('li', { class: cls || '' }, text)); log.scrollTop = log.scrollHeight; };

  for (const st of res.steps) {
    if (run !== S.runs.viva) return;
    const node = vivaRefs.nodes[st.group];
    if (st.action === 'assign') {
      node.classList.add('considering');
      for (const r of vivaReasons(st.group, st.slot, asg)) {
        const other = vivaRefs.nodes[r.other]; const edge = vivaRefs.edges[r.edge];
        other.classList.add('clash'); edge?.classList.add('clash');
        addLog(`${st.group} = S${r.slot} ✗ ${r.why}`, 'cf');
        await sleep(520);
        other.classList.remove('clash'); edge?.classList.remove('clash');
        if (run !== S.runs.viva) return;
      }
      asg[st.group] = st.slot;
      node.classList.remove('considering');
      node.classList.add('assigned');
      node.style.setProperty('--slot', SLOT_COLORS[st.slot]);
      $('.v-slot', node).textContent = `S${st.slot} · ${SLOT_TIMES[st.slot]}`;
      addLog(`${st.group} = S${st.slot} ✓ consistent`);
      await sleep(560);
    } else {
      bts++;
      $('#viva-bt').textContent = bts;
      const stuck = Object.keys(VIVA_POS).filter((g) => asg[g] === undefined && g !== st.group && vivaReasons(g, 5, asg).length >= 4);
      stuck.forEach((g) => vivaRefs.nodes[g].classList.add('clash'));
      node.classList.add('backtrack');
      addLog(`↩ backtrack ${st.group} (undo S${st.slot})${stuck.length ? `: ${stuck.join(', ')} has no legal slot` : ''}`, 'bt');
      await sleep(900);
      stuck.forEach((g) => vivaRefs.nodes[g].classList.remove('clash'));
      delete asg[st.group];
      node.setAttribute('class', 'v-node');
      node.style.removeProperty('--slot');
      $('.v-slot', node).textContent = '';
      await sleep(250);
    }
  }
  if (run !== S.runs.viva) return;
  $('#viva-tried').textContent = res.stats.assignments_tried;
  $('#viva-bt').textContent = res.stats.backtracks;
  addLog(`Solved: all 6 groups assigned with ${res.stats.backtracks} backtrack${res.stats.backtracks === 1 ? '' : 's'}.`);
  const rows = [1, 2, 3, 4].map((sl) => {
    const gs = Object.entries(res.timetable).filter(([, v]) => v === sl).map(([g]) => g);
    return h('tr', {}, h('td', {}, h('span', { class: 'slot-dot', style: { '--slot': SLOT_COLORS[sl] } }), h('b', {}, `Slot ${sl}`)), h('td', { class: 'mono' }, SLOT_TIMES[sl]), h('td', {}, gs.join(', ') || '–'));
  });
  $('#viva-table').append(h('span', { class: 'card-label' }, 'Final timetable'),
    h('table', { class: 'tt-table' }, h('thead', {}, h('tr', {}, h('th', {}, 'Slot'), h('th', {}, 'Time'), h('th', {}, 'Groups'))), h('tbody', {}, rows)));
}

/* ==========================================================================
   KNOWLEDGE BASE
   ========================================================================== */
function renderKB() {
  const fl = $('#fact-list'); fl.innerHTML = '';
  S.kb.facts.forEach((f) => fl.append(h('li', { 'data-fact': f }, f)));
  S.derived.forEach((d) => fl.append(h('li', { class: 'derived', 'data-fact': d.fact }, d.fact, h('small', {}, d.rule))));
  $('#fact-count').textContent = S.kb.facts.length + S.derived.length;
  const rl = $('#rule-list'); rl.innerHTML = '';
  S.kb.rules.forEach((r) => rl.append(h('li', { 'data-rule': r.id },
    h('span', { class: 'rule-id' }, r.id), h('span', { class: 'rule-text' }, r.text),
    h('span', { class: `src-tag ${r.source === 'handout' ? 'handout' : 'team'}` }, r.source === 'handout' ? 'handout' : 'team-defined'))));
  $('#rule-count').textContent = S.kb.rules.length;
}

function normProof(step) {
  if (typeof step === 'string') {
    const m = step.match(/^(R\d+)\b[:\s-]*(.*)$/);
    if (m) return { type: 'rule', rule: m[1], text: m[2] || m[1] };
    if (/^missing/i.test(step)) return { type: 'missing', text: step.replace(/^missing[:\s]*/i, '') };
    return { type: 'fact', text: step };
  }
  return step;
}

async function runKBQuery(e) {
  e.preventDefault();
  const q = $('#kb-query').value.trim();
  if (!q) return;
  const run = ++S.runs.kb;
  const res = await safe(() => API.kbQuery({ query: q }), 'Query failed');
  if (!res || run !== S.runs.kb) return;
  $$('.fact-list li.hl, .rule-list li.hl').forEach((x) => x.classList.remove('hl'));
  const v = $('#kb-verdict');
  v.hidden = true;
  const proof = $('#kb-proof'); proof.innerHTML = '';
  const steps = (res.proof || []).map(normProof);
  const arrow = (bad) => { const a = h('span', { class: `parrow${bad ? ' bad' : ''}` }); a.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS.arrow}</svg>`; return a; };
  const kinds = { fact: 'Fact', rule: 'Rule', conclusion: 'Derived', missing: 'Missing premise', blocked: 'Blocked' };
  for (let i = 0; i < steps.length; i++) {
    if (run !== S.runs.kb) return;
    const st = steps[i];
    if (i > 0) proof.append(arrow(st.type === 'missing' || st.type === 'blocked'));
    proof.append(h('div', { class: `pcard ${st.type}` },
      h('div', { class: 'pk' }, st.type === 'rule' ? `Rule ${st.rule}` : st.type === 'blocked' ? `${st.rule || 'Rule'} blocked` : kinds[st.type] || st.type),
      h('div', { class: 'pt' }, st.type === 'blocked' ? st.text.replace(/^R\d+\s*/, '') : st.text)));
    if (st.type === 'fact') $(`.fact-list li[data-fact="${CSS.escape(st.text)}"]`)?.classList.add('hl');
    if (st.type === 'rule' || st.type === 'blocked') $(`.rule-list li[data-rule="${st.rule}"]`)?.classList.add('hl');
    await sleep(st.type === 'missing' ? 600 : 380);
  }
  if (run !== S.runs.kb) return;
  v.className = `verdict ${res.entailed ? 'ok' : 'bad'}`;
  v.innerHTML = '';
  v.append(icon(res.entailed ? 'check' : 'x'), h('div', {},
    h('strong', {}, res.entailed ? `Entailed: ${res.query}` : `Not entailed: ${res.query}`),
    h('div', { class: 'sub-val' }, res.explanation),
    res.answers && res.answers.length ? h('div', { class: 'answers' }, res.answers.map((a) => h('span', {}, a))) : null));
  v.hidden = false;
  if (!steps.length && !res.entailed) proof.append(h('p', { class: 'muted' }, 'No rule or fact concludes this query.'));
}

async function runForward() {
  const btn = $('#kb-forward'); btn.disabled = true;
  const run = ++S.runs.kb;
  const res = await safe(() => API.kbForward(), 'Forward chaining failed');
  if (!res) { btn.disabled = false; return; }
  S.derived = []; renderKB();
  const log = $('#forward-log'); log.innerHTML = '';
  for (const line of res.log) {
    if (run !== S.runs.kb) break;
    const m = line.match(/^(R\d+)\s+fired\s*->\s*(.+)$/);
    const rule = m ? m[1] : ''; const fact = m ? m[2].trim() : line;
    log.append(h('li', {}, h('span', { class: 'rule-id' }, rule), h('span', { class: 'arrow' }, 'fired →'), h('span', { class: 'fact' }, fact)));
    log.scrollTop = log.scrollHeight;
    S.derived.push({ fact, rule });
    const li = h('li', { class: 'derived', 'data-fact': fact }, fact, h('small', {}, rule));
    $('#fact-list').append(li);
    $('#fact-count').textContent = S.kb.facts.length + S.derived.length;
    const rl = $(`.rule-list li[data-rule="${rule}"]`);
    rl?.classList.add('fired'); setTimeout(() => rl?.classList.remove('fired'), 700);
    await sleep(380);
  }
  if (run === S.runs.kb) log.append(h('li', {}, h('span', { class: 'yes' }, `Fixed point reached: ${res.log.length} new facts derived.`)));
  btn.disabled = false;
}

/* ==========================================================================
   ANN
   ========================================================================== */
const ANN_LAYERS = [7, 4, 3, 4];
const ANN_X = [150, 330, 490, 640];
const ANN_IN = ['Role', 'RequestType', 'Severity', 'TimeSensitivity', 'CrowdLevel', 'Distance', 'Eligibility'];
const ANN_OUT = ['low', 'normal', 'high', 'urgent'];
const annRefs = { neurons: [], edges: [] };
const annY = (n, i) => { const top = 52; const bottom = 392; return n === 1 ? (top + bottom) / 2 : top + ((bottom - top) * i) / (n - 1) * (n < 7 ? 0.7 : 1) + (n < 7 ? (bottom - top) * 0.15 : 0); };

function buildANN() {
  const svg = $('#ann-net'); svg.innerHTML = '';
  const gE = s('g', {}, svg); const gN = s('g', {}, svg);
  ['Input', 'Hidden 1', 'Hidden 2', 'Output'].forEach((t, l) => s('text', { class: 'a-layer', x: ANN_X[l], y: 22, text: `${t} (${ANN_LAYERS[l]})` }, svg));
  for (let l = 0; l < ANN_LAYERS.length - 1; l++) {
    annRefs.edges[l] = [];
    for (let i = 0; i < ANN_LAYERS[l]; i++) {
      for (let j = 0; j < ANN_LAYERS[l + 1]; j++) {
        annRefs.edges[l].push(s('line', { class: 'a-edge', x1: ANN_X[l], y1: annY(ANN_LAYERS[l], i), x2: ANN_X[l + 1], y2: annY(ANN_LAYERS[l + 1], j) }, gE));
      }
    }
  }
  ANN_LAYERS.forEach((n, l) => {
    annRefs.neurons[l] = [];
    for (let i = 0; i < n; i++) {
      const y = annY(n, i);
      const g = s('g', { class: 'a-neuron', transform: `translate(${ANN_X[l]},${y})` }, gN);
      s('circle', { class: 'bg', r: 17 }, g);
      s('circle', { class: 'act', r: 17 }, g);
      s('text', { class: 'val', text: '' }, g);
      if (l === 0) s('text', { class: 'a-label', x: ANN_X[0] - 28, y, 'text-anchor': 'end', text: ANN_IN[i] }, gN);
      if (l === 3) s('text', { class: 'a-label out', x: ANN_X[3] + 28, y, text: cap(ANN_OUT[i]) }, gN);
      annRefs.neurons[l].push(g);
    }
  });
  buildPerceptron();
  const pb = $('#prob-bars'); pb.innerHTML = '';
  ANN_OUT.forEach((k) => pb.append(h('span', { class: 'lbl', 'data-k': k }, k), h('span', { class: 'track', 'data-k': k }, h('i')), h('span', { class: 'num', 'data-k': k }, '–')));
  $('#ann-form').addEventListener('submit', (e) => { e.preventDefault(); runPredict(); });
}

function setNeuron(g, v) {
  $('.act', g).style.opacity = Math.max(0.04, Math.min(1, v));
  $('.val', g).textContent = fmtNum(v);
  g.classList.add('lit');
}

const annFeatures = () => [+$('#a-role').value, +$('#a-type').value, +$('#a-sev').value, +$('#a-time').value, +$('#a-crowd').value, +$('#a-dist').value, $('#a-elig').checked ? 1 : 0];
function setAnnInputs(f) {
  $('#a-role').value = f[0]; $('#a-type').value = f[1];
  [['#a-sev', 2], ['#a-time', 3], ['#a-crowd', 4], ['#a-dist', 5]].forEach(([id, i]) => { $(id).value = f[i]; syncRange($(id)); });
  $('#a-elig').checked = !!f[6];
}
// Same scaling as the ANN (divide by FEATURE_MAX); the live API also returns scaled_features.
const normInputs = (f) => [f[0] / 2, f[1] / 4, f[2] / 10, f[3] / 10, f[4] / 10, Math.min(f[5], 15) / 15, f[6] ? 1 : 0];

async function runPredict() {
  const run = ++S.runs.ann;
  const feats = annFeatures();
  const res = await safe(() => API.annPredict({ features: feats }), 'Prediction failed');
  if (!res || run !== S.runs.ann) return;
  annRefs.neurons.flat().forEach((g) => { $('.act', g).style.opacity = 0; g.classList.remove('lit'); });
  $$('.a-label.win').forEach((x) => x.classList.remove('win'));
  $$('#prob-bars .win').forEach((x) => x.classList.remove('win'));
  $$('#prob-bars .track i').forEach((i) => { i.style.width = '0'; });
  $('#ann-verdict').innerHTML = '';
  const probs = res.probabilities || {};
  const layers = [res.scaled_features || normInputs(feats), res.activations?.hidden1 || [], res.activations?.hidden2 || [], ANN_OUT.map((k) => probs[k] || 0)];
  for (let l = 0; l < layers.length; l++) {
    if (run !== S.runs.ann) return;
    annRefs.neurons[l].forEach((g, i) => setNeuron(g, layers[l][i] ?? 0));
    if (l === layers.length - 1) break;
    await sleep(320);
    annRefs.edges[l].forEach((e) => e.classList.add('pulse'));
    await sleep(620);
    annRefs.edges[l].forEach((e) => e.classList.remove('pulse'));
  }
  const win = res.final_priority;
  const outIdx = ANN_OUT.indexOf(win);
  $$('.a-label.out')[outIdx]?.classList.add('win');
  ANN_OUT.forEach((k) => {
    const on = k === win;
    $$(`#prob-bars [data-k="${k}"]`).forEach((x) => x.classList.toggle('win', on));
    $(`#prob-bars .track[data-k="${k}"] i`).style.width = `${(probs[k] || 0) * 100}%`;
    $(`#prob-bars .num[data-k="${k}"]`).textContent = fmtNum(probs[k] || 0);
  });
  $('#ann-verdict').append(
    h('div', { class: 'stat' }, h('span', { class: `stat-v p-${win}` }, `${win} (${fmtNum(res.confidence)})`), h('span', { class: 'stat-l' }, 'MLP final priority')),
    h('div', { class: 'stat' }, h('span', { class: `stat-v ${res.binary_priority === 'urgent' ? 'p-urgent' : 'p-low'}` }, pretty(res.binary_priority)), h('span', { class: 'stat-l' }, 'Perceptron binary')));
  animatePerceptron(feats, res, run);
}

/* ---------- perceptron ---------- */
const percRefs = {};
function buildPerceptron() {
  const svg = $('#perceptron'); svg.innerHTML = '';
  const ys = ANN_IN.map((_, i) => 22 + i * 34);
  const sx = 430; const sy = 125;
  percRefs.edges = []; percRefs.inputs = []; percRefs.w = [];
  ys.forEach((y, i) => {
    percRefs.edges.push(s('line', { class: 'p-edge', x1: 190, y1: y, x2: sx - 34, y2: sy }, svg));
  });
  ys.forEach((y, i) => {
    s('text', { class: 'p-text', x: 160, y, 'text-anchor': 'end', text: ANN_IN[i] }, svg);
    percRefs.inputs.push(s('circle', { class: 'p-node', cx: 180, cy: y, r: 9 }, svg));
    percRefs.w.push(s('text', { class: 'p-w', x: 190 + (sx - 34 - 190) * 0.42, y: y + (sy - y) * 0.42 - 4, text: '' }, svg));
  });
  percRefs.sum = s('circle', { class: 'p-node', cx: sx, cy: sy, r: 34 }, svg);
  s('text', { class: 'p-big', x: sx, y: sy - 4, text: 'Σ' }, svg);
  percRefs.sumVal = s('text', { class: 'p-w', x: sx, y: sy + 52, text: 'Σ wᵢxᵢ + bias' }, svg);
  s('line', { class: 'p-edge', x1: sx + 34, y1: sy, x2: 540, y2: sy }, svg);
  s('rect', { class: 'p-node', x: 540, y: sy - 32, width: 76, height: 64, rx: 10 }, svg);
  s('path', { class: 'p-step', d: `M552 ${sy + 16} H578 V${sy - 16} H604` }, svg);
  s('text', { class: 'p-w', x: 578, y: sy + 48, text: 'step(z ≥ 0)' }, svg);
  s('line', { class: 'p-edge', x1: 616, y1: sy, x2: 664, y2: sy }, svg);
  percRefs.out = s('circle', { class: 'p-node p-out', cx: 696, cy: sy, r: 30 }, svg);
  percRefs.outVal = s('text', { class: 'p-big', x: 696, y: sy, text: '?' }, svg);
  percRefs.outLbl = s('text', { class: 'p-text', x: 696, y: sy + 48, 'text-anchor': 'middle', text: 'Urgent 0/1' }, svg);
}
async function animatePerceptron(feats, res, run) {
  const p = res.perceptron;
  const x = res.scaled_features || normInputs(feats);
  percRefs.inputs.forEach((c, i) => c.classList.toggle('lit', x[i] > 0.05));
  percRefs.w.forEach((t, i) => { t.textContent = p ? `w=${p.weights[i]}` : ''; });
  percRefs.edges.forEach((e, i) => e.classList.toggle('neg', !!p && p.weights[i] < 0));
  percRefs.out.classList.remove('on'); percRefs.sum.classList.remove('lit');
  percRefs.outVal.textContent = '?';
  percRefs.edges.forEach((e) => e.classList.add('pulse'));
  await sleep(700);
  if (run !== S.runs.ann) return;
  percRefs.edges.forEach((e) => e.classList.remove('pulse'));
  percRefs.sum.classList.add('lit');
  percRefs.sumVal.textContent = p ? `z = ${fmtNum(p.sum)}` : '';
  await sleep(450);
  const urgent = res.binary_priority === 'urgent';
  percRefs.out.classList.toggle('on', urgent);
  percRefs.outVal.textContent = urgent ? '1' : '0';
  percRefs.outLbl.textContent = urgent ? 'Urgent' : 'Not urgent';
}

/* ---------- metrics ---------- */
function renderMetrics(m) {
  const acc = $('#acc-bars'); acc.innerHTML = '';
  const lo = 60;
  const rows = [
    { l: 'MLP (4 classes)', v: m.mlp_accuracy },
    { l: 'Noise ceiling (4 classes)', v: m.noise_ceiling, cls: 'ref' },
    { l: 'MLP collapsed to binary', v: m.mlp_binary_accuracy, cls: 'alt' },
    { l: 'Perceptron (binary)', v: m.perceptron_accuracy, cls: 'alt' },
  ];
  rows.forEach((r) => acc.append(h('div', { class: `acc-row ${r.cls || ''}` },
    h('div', { class: 'acc-top' }, h('span', {}, r.l), h('b', {}, `${fmtNum(r.v)}%`)),
    h('div', { class: 'acc-track' }, h('i', { 'data-w': `${((r.v - lo) / (100 - lo)) * 100}%` })))));
  acc.append(h('div', { class: 'acc-axis' }, h('span', {}, `${lo}%`), h('span', {}, '80%'), h('span', {}, '100%')),
    h('p', { class: 'acc-note' }, `The MLP reaches ${fmtNum(m.mlp_accuracy / m.noise_ceiling * 100, 1)}% of the best accuracy the label noise allows. The perceptron solves the easier 2-class task; compare it with the MLP collapsed to binary.`));

  $('#cm-mlp').append(confusion(m.mlp_confusion, ANN_OUT));
  $('#cm-perc').append(confusion(m.perceptron_confusion, ['not urgent', 'urgent']));
  drawLoss(m.loss_curve, m.loss_epochs);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    $$('#acc-bars [data-w]').forEach((i) => { i.style.width = i.dataset.w; });
  }));
}
function confusion(mat, labels) {
  const n = labels.length;
  const max = Math.max(...mat.flat());
  const grid = h('div', { class: 'cm', style: { gridTemplateColumns: `64px repeat(${n}, minmax(0, ${n > 2 ? 56 : 80}px))` } });
  grid.append(h('span', { class: 'cm-h' }, ''), ...labels.map((l) => h('span', { class: 'cm-h' }, l)));
  mat.forEach((row, i) => {
    grid.append(h('span', { class: 'cm-r' }, labels[i]));
    row.forEach((v, j) => {
      const pct = Math.round((v / max) * 85);
      grid.append(h('span', {
        class: `cm-c${i === j ? ' diag' : ''}`,
        title: `Actual ${labels[i]}, predicted ${labels[j]}: ${v}`,
        style: { background: `color-mix(in srgb, var(--ann) ${pct}%, var(--surface-2))`, color: pct > 50 ? 'var(--on-accent)' : 'var(--text)', transitionDelay: `${(i * n + j) * 30}ms` },
      }, v));
    });
  });
  const wrap = h('div', {}, grid, h('div', { class: 'cm-axis' }, 'Rows: actual · Columns: predicted'));
  const io = new IntersectionObserver((ents) => ents.forEach((en) => { if (en.isIntersecting) { grid.classList.add('in'); io.disconnect(); } }));
  io.observe(grid);
  return wrap;
}
function drawLoss(loss, epochs) {
  const svg = $('#loss-curve'); svg.innerHTML = '';
  const W = 360; const H = 200; const L = 40; const R = 10; const T = 12; const B = 30;
  const max = Math.ceil(Math.max(...loss) * 10) / 10; const min = 0;
  const x = (i) => L + (i / (loss.length - 1)) * (W - L - R);
  const y = (v) => T + (1 - (v - min) / (max - min)) * (H - T - B);
  for (let t = 0; t <= 4; t++) {
    const v = min + (max - min) * (t / 4);
    s('line', { class: 'grid-line', x1: L, x2: W - R, y1: y(v), y2: y(v) }, svg);
    s('text', { class: 'axis-text', x: L - 6, y: y(v) + 3.5, 'text-anchor': 'end', text: v.toFixed(1) }, svg);
  }
  [0, Math.floor((loss.length - 1) / 2), loss.length - 1].forEach((i) => s('text', { class: 'axis-text', x: x(i), y: H - 12, 'text-anchor': i === loss.length - 1 ? 'end' : 'middle', text: epochs ? epochs[i] : i + 1 }, svg));
  s('text', { class: 'axis-text', x: (L + W - R) / 2, y: H - 1, 'text-anchor': 'middle', text: 'epoch' }, svg);
  const pts = loss.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  s('polygon', { class: 'loss-area', points: `${x(0)},${y(min)} ${pts} ${x(loss.length - 1)},${y(min)}` }, svg);
  const line = s('polyline', { class: 'loss-line', points: pts }, svg);
  const len = line.getTotalLength ? line.getTotalLength() : 800;
  line.style.strokeDasharray = len; line.style.strokeDashoffset = len;
  const io = new IntersectionObserver((ents) => ents.forEach((en) => {
    if (!en.isIntersecting) return;
    line.style.transition = 'stroke-dashoffset 1.4s cubic-bezier(.4,0,.2,1)';
    line.style.strokeDashoffset = 0; io.disconnect();
  }));
  io.observe(svg);
  s('text', { class: 'axis-text', x: W - R, y: y(loss[loss.length - 1]) - 8, 'text-anchor': 'end', text: `final ${loss[loss.length - 1].toFixed(3)}` }, svg);
}

/* ==========================================================================
   RESET & INIT
   ========================================================================== */
async function resetSystem() {
  const ok = await safe(() => API.reset(), 'Reset failed');
  if (!ok) return;
  Object.keys(S.runs).forEach((k) => S.runs[k]++);
  S.history = []; S.current = null; S.derived = [];
  renderHistory();
  resetPipeline();
  $('#pipe-meta').textContent = 'Submit a request to watch it move through the modules the router selects.';
  $('#pipe-replay').disabled = true;
  $('#result').innerHTML = '';
  const empty = h('div', { class: 'empty-state' }, icon('final', 'ico big'), h('p', {}, h('strong', {}, 'System reset.'), ' Bookings, request IDs and history are back to their initial state.'));
  $('#result').append(empty);
  $('#csp-note').hidden = true; $('#booking-token').hidden = true;
  await refreshBookings();
  vivaReset(); $('#viva-log').innerHTML = ''; $('#viva-table').innerHTML = '';
  $('#viva-tried').textContent = '–'; $('#viva-bt').textContent = '–';
  renderKB(); $('#forward-log').innerHTML = ''; $('#kb-proof').innerHTML = ''; $('#kb-verdict').hidden = true;
  syncMapControls();
  toast('System reset');
}

async function init() {
  applyTheme(loadTheme());
  fillIcons();
  $('#api-mode-text').textContent = API.mode() === 'mock' ? 'Mock data (USE_MOCK = true)' : 'Live API';
  $('#api-mode').classList.toggle('live', API.mode() !== 'mock');

  $$('.nav-item').forEach((b) => b.addEventListener('click', () => go(b.dataset.section, { focus: true })));
  $('#history-counter').addEventListener('click', () => go('history', { focus: true }));
  $('#theme-toggle').addEventListener('click', () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
  $('#reset-btn').addEventListener('click', resetSystem);
  $('#pipe-replay').addEventListener('click', () => S.current && runPipeline(S.current.res, S.current.body));

  buildForm();
  buildPipeline();
  buildCSP();
  buildANN();
  $('#kb-form').addEventListener('submit', runKBQuery);
  $('#kb-forward').addEventListener('click', runForward);

  const [graph, demos, kb, metrics] = await Promise.all([
    safe(() => API.graph(), 'Could not load campus graph'),
    safe(() => API.demoScenarios(), 'Could not load demo scenarios'),
    safe(() => API.kb(), 'Could not load knowledge base'),
    safe(() => API.annMetrics(), 'Could not load ANN metrics'),
  ]);
  if (graph) {
    S.graph = graph;
    graph.nodes.forEach((n) => { S.pos[n.name] = n; S.adj[n.name] = []; });
    graph.edges.forEach((e) => { S.adj[e.a].push(e.b); S.adj[e.b].push(e.a); });
    buildMap();
  }
  if (demos) {
    S.demos = demos;
    const sel = $('#demo-select');
    demos.forEach((d, i) => sel.append(h('option', { value: i }, d.name)));
  }
  if (kb) { S.kb = kb; renderKB(); }
  if (metrics) renderMetrics(metrics);
  await refreshBookings();
  renderHistory();
}

document.addEventListener('DOMContentLoaded', init);
