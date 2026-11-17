/* ==========================================================================
   Smart Campus AI — api.js
   The ONLY file that talks to the backend. Every call uses fetch() against
   API_BASE. While USE_MOCK is true, the same functions return mock data that
   follows the exact response shapes of the Flask API, so the UI works
   standalone. Flip USE_MOCK to false to go live.
   ========================================================================== */
'use strict';

const USE_MOCK = false;
const API_BASE = '/api';

async function http(method, path, body) {
  let res;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (_) {
    // fetch() only throws when no response arrives at all (server stopped / network down).
    throw new Error('Server not reachable. Start it with "python server.py", then try again.');
  }
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).error || ''; } catch (_) { /* ignore */ }
    throw new Error(`${method} ${API_BASE}${path} failed (${res.status}) ${detail}`.trim());
  }
  return res.json();
}

const API = {
  submitRequest: (body) => USE_MOCK ? mockCall(() => Mock.processRequest(body)) : http('POST', '/request', body),
  demoScenarios: () => USE_MOCK ? mockCall(() => Mock.DEMOS) : http('GET', '/demo-scenarios'),
  graph: () => USE_MOCK ? mockCall(() => Mock.graph()) : http('GET', '/graph'),
  search: (body) => USE_MOCK ? mockCall(() => Mock.search(body)) : http('POST', '/search', body),
  compare: (body) => USE_MOCK ? mockCall(() => Mock.compare(body)) : http('POST', '/search/compare', body),
  bookings: () => USE_MOCK ? mockCall(() => Mock.bookings()) : http('GET', '/bookings'),
  solveViva: () => USE_MOCK ? mockCall(() => Mock.solveViva()) : http('POST', '/viva/solve', {}),
  kb: () => USE_MOCK ? mockCall(() => Mock.kb()) : http('GET', '/kb'),
  kbQuery: (body) => USE_MOCK ? mockCall(() => Mock.query(body.query)) : http('POST', '/kb/query', body),
  kbForward: () => USE_MOCK ? mockCall(() => Mock.forward()) : http('POST', '/kb/forward', {}),
  annPredict: (body) => USE_MOCK ? mockCall(() => Mock.predict(body.features)) : http('POST', '/ann/predict', body),
  annMetrics: () => USE_MOCK ? mockCall(() => Mock.metrics()) : http('GET', '/ann/metrics'),
  // Every request processed this session, oldest first: [{request, response, time}] (History survives a reload).
  history: () => USE_MOCK ? mockCall(() => Mock.history()) : http('GET', '/history'),
  reset: () => USE_MOCK ? mockCall(() => Mock.reset()) : http('POST', '/reset', {}),
  // Bookings only (request ids keep counting): run before every demo scenario, like cli.py's demo mode.
  resetBookings: () => USE_MOCK ? mockCall(() => Mock.resetBookings()) : http('POST', '/reset', { keep_counter: true }),
  mode: () => (USE_MOCK ? 'mock' : 'live'),
};

/* Simulates network latency and returns a deep copy, like a real response. */
async function mockCall(fn) {
  await new Promise((r) => setTimeout(r, 90 + Math.random() * 110));
  return JSON.parse(JSON.stringify(fn()));
}

/* ==========================================================================
   MOCK BACKEND — mirrors the Python modules so every visual is consistent.
   ========================================================================== */
const Mock = (() => {
  /* ---------------- Campus graph ---------------- */
  const NODES = [
    ['Main_Gate', 0, 4], ['Parking', 2, 4], ['Admin_Block', 3, 5], ['Student_Services', 6, 5],
    ['Exam_Hall', 8, 5], ['Seminar_Room', 10, 4], ['Library', 6, 2], ['AI_Lab', 9, 2],
    ['Bus_Stop', 0, 1], ['Medical_Center', 1, 1], ['Cafeteria', 4, 1], ['Science_Block', 7, 1],
    ['Hostel', 2, 0],
  ].map(([name, x, y]) => ({ name, x, y }));

  const EDGES = [
    ['Main_Gate', 'Bus_Stop', 1], ['Main_Gate', 'Parking', 2], ['Main_Gate', 'Admin_Block', 4],
    ['Main_Gate', 'Hostel', 5], ['Parking', 'Bus_Stop', 2], ['Parking', 'Science_Block', 3],
    ['Admin_Block', 'Student_Services', 1], ['Admin_Block', 'Exam_Hall', 2],
    ['Student_Services', 'Library', 2], ['Exam_Hall', 'Seminar_Room', 1],
    ['Exam_Hall', 'Science_Block', 3], ['Seminar_Room', 'Science_Block', 2],
    ['Library', 'Cafeteria', 2], ['Library', 'AI_Lab', 3], ['AI_Lab', 'Science_Block', 1],
    ['Bus_Stop', 'Medical_Center', 2], ['Medical_Center', 'Hostel', 3],
    ['Hostel', 'Cafeteria', 2], ['Cafeteria', 'Science_Block', 3],
  ].map(([a, b, cost]) => ({ a, b, cost }));

  const K = 1 / 3;
  const POS = Object.fromEntries(NODES.map((n) => [n.name, n]));
  const ADJ = Object.fromEntries(NODES.map((n) => [n.name, []]));
  EDGES.forEach(({ a, b, cost }) => { ADJ[a].push({ n: b, cost }); ADJ[b].push({ n: a, cost }); });
  Object.values(ADJ).forEach((l) => l.sort((p, q) => p.n.localeCompare(q.n)));

  const euclid = (a, b) => Math.hypot(POS[a].x - POS[b].x, POS[a].y - POS[b].y);
  const heur = (n, goal) => K * euclid(n, goal);
  const edgeCost = (a, b) => (ADJ[a].find((e) => e.n === b) || { cost: Infinity }).cost;
  const pathCost = (p) => p.slice(1).reduce((sum, n, i) => sum + edgeCost(p[i], n), 0);

  /* ---------------- Search algorithms ---------------- */
  function bfs(s, g) {
    const q = [[s]]; const seen = new Set([s]); const order = [];
    while (q.length) {
      const p = q.shift(); const n = p[p.length - 1]; order.push(n);
      if (n === g) return { found: true, path: p, order };
      for (const { n: m } of ADJ[n]) if (!seen.has(m)) { seen.add(m); q.push([...p, m]); }
    }
    return { found: false, path: [], order };
  }

  function dfs(s, g) {
    const st = [[s]]; const ex = new Set(); const order = [];
    while (st.length) {
      const p = st.pop(); const n = p[p.length - 1];
      if (ex.has(n)) continue;
      ex.add(n); order.push(n);
      if (n === g) return { found: true, path: p, order };
      const nb = ADJ[n].map((e) => e.n).filter((m) => !ex.has(m)).reverse();
      for (const m of nb) st.push([...p, m]);
    }
    return { found: false, path: [], order };
  }

  function dlsRec(path, g, limit, order) {
    const n = path[path.length - 1]; order.push(n);
    if (n === g) return path;
    if (limit === 0) return null;
    for (const { n: m } of ADJ[n]) {
      if (path.includes(m)) continue;
      const r = dlsRec([...path, m], g, limit - 1, order);
      if (r) return r;
    }
    return null;
  }
  function dls(s, g, limit) {
    const order = []; const p = dlsRec([s], g, limit, order);
    return { found: !!p, path: p || [], order };
  }
  function ids(s, g) {
    const order = [];
    for (let d = 0; d <= NODES.length; d++) {
      const p = dlsRec([s], g, d, order);
      if (p) return { found: true, path: p, order };
    }
    return { found: false, path: [], order };
  }

  function bibfs(s, g) {
    const order = [];
    if (s === g) return { found: true, path: [s], order: [s] };
    const pf = { [s]: null }; const pb = { [g]: null };
    let qf = [s]; let qb = [g];
    const join = (m) => {
      const out = []; let x = m;
      while (x !== null) { out.unshift(x); x = pf[x]; }
      x = pb[m];
      while (x !== null) { out.push(x); x = pb[x]; }
      return out;
    };
    while (qf.length && qb.length) {
      let nq = [];
      for (const n of qf) {
        order.push(n);
        for (const { n: m } of ADJ[n]) {
          if (m in pf) continue;
          pf[m] = n;
          if (m in pb) return { found: true, path: join(m), order };
          nq.push(m);
        }
      }
      qf = nq; nq = [];
      for (const n of qb) {
        order.push(n);
        for (const { n: m } of ADJ[n]) {
          if (m in pb) continue;
          pb[m] = n;
          if (m in pf) return { found: true, path: join(m), order };
          nq.push(m);
        }
      }
      qb = nq;
    }
    return { found: false, path: [], order };
  }

  function bestFirst(s, g, f, greedy = false) {
    let tie = 0;
    const open = [{ n: s, g: 0, p: [s], f: f(0, s), t: tie++ }];
    const best = { [s]: 0 }; const closed = new Set(); const order = [];
    while (open.length) {
      open.sort((a, b) => a.f - b.f || a.t - b.t);
      const cur = open.shift();
      if (closed.has(cur.n)) continue;
      closed.add(cur.n); order.push(cur.n);
      if (cur.n === g) return { found: true, path: cur.p, order };
      for (const { n: m, cost } of ADJ[cur.n]) {
        if (closed.has(m)) continue;
        const ng = cur.g + cost;
        if (!greedy && best[m] !== undefined && best[m] <= ng) continue;
        best[m] = ng;
        open.push({ n: m, g: ng, p: [...cur.p, m], f: f(ng, m), t: tie++ });
      }
    }
    return { found: false, path: [], order };
  }

  function rbfs(s, g) {
    const order = [];
    const H = (n) => heur(n, g);
    function rec(node, fLimit) {
      order.push(node.n);
      if (node.n === g) return [node, node.f];
      if (order.length > 400) return [null, Infinity];
      const succ = ADJ[node.n].filter((e) => !node.p.includes(e.n)).map((e) => {
        const gg = node.g + e.cost;
        return { n: e.n, g: gg, p: [...node.p, e.n], f: Math.max(gg + H(e.n), node.f) };
      });
      if (!succ.length) return [null, Infinity];
      for (;;) {
        succ.sort((a, b) => a.f - b.f);
        const bestS = succ[0];
        if (bestS.f > fLimit) return [null, bestS.f];
        const alt = succ.length > 1 ? succ[1].f : Infinity;
        const [res, nf] = rec(bestS, Math.min(fLimit, alt));
        bestS.f = nf;
        if (res) return [res, nf];
        if (order.length > 400) return [null, Infinity];
      }
    }
    const [res] = rec({ n: s, g: 0, p: [s], f: H(s) }, Infinity);
    return { found: !!res, path: res ? res.p : [], order };
  }

  const ALGOS = {
    'BFS': (s, g) => bfs(s, g),
    'DFS': (s, g) => dfs(s, g),
    'DLS': (s, g, lim) => dls(s, g, lim),
    'IDS': (s, g) => ids(s, g),
    'Bidirectional BFS': (s, g) => bibfs(s, g),
    'UCS': (s, g) => bestFirst(s, g, (gc) => gc),
    'Greedy': (s, g) => bestFirst(s, g, (gc, n) => heur(n, g), true),
    'A*': (s, g) => bestFirst(s, g, (gc, n) => gc + heur(n, g)),
    'RBFS': (s, g) => rbfs(s, g),
  };

  function runAlgo(name, s, g, { limit = 3, unweighted = false } = {}) {
    const t0 = performance.now();
    const r = ALGOS[name](s, g, limit);
    const t = performance.now() - t0;
    const cost = r.found ? (unweighted ? r.path.length - 1 : pathCost(r.path)) : null;
    return {
      algorithm_used: name, found: r.found, path: r.path, cost,
      steps: r.found ? r.path.length - 1 : 0, nodes_expanded: r.order.length,
      time_ms: Math.max(0.001, +t.toFixed(3)), expanded_order: r.order,
    };
  }

  function checkNodes(...names) {
    for (const n of names) if (!POS[n]) throw new Error(`Unknown location: ${n}`);
  }

  function search({ source, destination, graph_type = 'weighted', heuristic_available = true }) {
    checkNodes(source, destination);
    const unweighted = graph_type === 'unweighted';
    const algo = unweighted ? 'BFS' : (heuristic_available ? 'A*' : 'UCS');
    const r = runAlgo(algo, source, destination, { unweighted });
    delete r.found; delete r.time_ms;
    return r;
  }

  function compare({ source, destination, dls_limit = 3 }) {
    checkNodes(source, destination);
    return Object.keys(ALGOS).map((a) => runAlgo(a, source, destination, { limit: +dls_limit }));
  }

  /* ---------------- Bookings (CSP state) ---------------- */
  const BASE_BOOKINGS = [
    { room: 'AI_Lab', slot: 2 }, { room: 'Exam_Hall', slot: 1 }, { room: 'Exam_Hall', slot: 3 },
    { room: 'Seminar_Room', slot: 2 }, { room: 'Admin_Block', slot: 1 },
    { room: 'Student_Services', slot: 4 }, { room: 'Medical_Center', slot: 3 },
  ];
  let bookingsState = BASE_BOOKINGS.map((b) => ({ ...b }));

  /* ---------------- Viva CSP ---------------- */
  const VIVA_GROUPS = ['G1', 'G2', 'G3', 'G4', 'G5', 'G6'];
  const VIVA_EDGES = [
    ['G1', 'G2'], ['G1', 'G4'], ['G1', 'G3'], ['G2', 'G4'], ['G2', 'G5'],
    ['G3', 'G5'], ['G3', 'G6'], ['G5', 'G6'],
  ];
  const PRECEDENCE = [['G4', 'G3']]; // G4 must be before G3

  function vivaConsistent(g, v, asg) {
    for (const [a, b] of VIVA_EDGES) {
      const o = a === g ? b : b === g ? a : null;
      if (o && asg[o] === v) return false;
    }
    for (const [a, b] of PRECEDENCE) {
      if (a === g && asg[b] !== undefined && !(v < asg[b])) return false;
      if (b === g && asg[a] !== undefined && !(asg[a] < v)) return false;
    }
    return true;
  }

  function solveViva() {
    const slots = [1, 2, 3, 4]; const asg = {}; const steps = [];
    let tried = 0; let backtracks = 0;
    const legal = (g) => slots.filter((v) => vivaConsistent(g, v, asg));
    const degree = (g) => VIVA_EDGES.filter((e) => e.includes(g)).length
      + PRECEDENCE.filter((e) => e.includes(g)).length;
    function bt() {
      const un = VIVA_GROUPS.filter((g) => asg[g] === undefined);
      if (!un.length) return true;
      un.sort((a, b) => legal(a).length - legal(b).length || degree(b) - degree(a) || a.localeCompare(b));
      const g = un[0];
      for (const v of slots) {
        tried++;
        if (!vivaConsistent(g, v, asg)) continue;
        asg[g] = v; steps.push({ group: g, slot: v, action: 'assign' });
        if (bt()) return true;
        delete asg[g]; backtracks++;
        steps.push({ group: g, slot: v, action: 'backtrack' });
      }
      return false;
    }
    bt();
    const timetable = {};
    VIVA_GROUPS.forEach((g) => { timetable[g] = asg[g]; });
    return { timetable, steps, stats: { assignments_tried: tried, backtracks } };
  }

  /* ---------------- Knowledge base (FOL, backward + forward chaining) ---------------- */
  const FACT_TEXT = [
    'Faculty(DrKhan)', 'Teaches(DrKhan, AI)', 'AssignedLab(AI, Lab1)',
    'Student(Ali)', 'Student(Sara)', 'Student(Ahmed)', 'Staff(Bilal)',
    'Enrolled(Ali, AI)', 'Enrolled(Sara, AI)', 'Enrolled(Ahmed, AI)',
    'Completed(Ali, ProgrammingFundamentals)', 'Completed(Ahmed, ProgrammingFundamentals)',
    'VivaGroup(G4)', 'MemberOf(Ahmed, G4)',
  ];
  const RULE_DEFS = [
    ['R1', 'Teaches(x, c) ∧ AssignedLab(c, l) → UsesLab(x, l)', 'handout'],
    ['R2', 'Faculty(x) ∧ Teaches(x, c) → Instructor(x, c)', 'handout'],
    ['R3', 'Enrolled(s, c) ∧ Completed(s, ProgrammingFundamentals) → Eligible(s, c)', 'handout'],
    ['R4', 'Student(s) ∧ Eligible(s, AI) → CanRequest(s, AI_Lab_Support)', 'handout'],
    ['R5', 'Instructor(x, c) → CanRequest(x, AI_Lab_Support)', 'team'],
    ['R6', 'Staff(x) → CanRequest(x, AI_Lab_Support)', 'team'],
    ['R7', 'Student(x) → CanRequest(x, Emergency_Help)', 'team'],
    ['R8', 'Staff(x) → CanRequest(x, Emergency_Help)', 'team'],
    ['R9', 'Faculty(x) → CanRequest(x, Emergency_Help)', 'team'],
    ['R10', 'Staff(x) → CanRequest(x, Maintenance)', 'team'],
    ['R11', 'Student(x) → CanRequest(x, Maintenance)', 'team'],
    ['R12', 'Faculty(x) → CanRequest(x, Access_Request)', 'team'],
    ['R13', 'Student(s) ∧ Eligible(s, AI) → CanRequest(s, Access_Request)', 'team'],
    ['R14', 'MemberOf(s, g) ∧ VivaGroup(g) → CanBookViva(s, g)', 'team'],
    ['R15', 'Instructor(x, c) ∧ AssignedLab(c, l) → Supervises(x, l)', 'team'],
  ];

  const parseAtom = (str) => {
    const m = String(str).trim().match(/^([A-Za-z_]\w*)\s*\(\s*([^()]*)\)$/);
    if (!m) return null;
    const args = m[2].split(',').map((t) => t.trim()).filter(Boolean);
    return args.length ? { p: m[1], args } : null;
  };
  const isVar = (t) => /^[a-z]/.test(t);
  const fmt = (a) => `${a.p}(${a.args.join(', ')})`;
  const clean = (s) => s.replace(/_v\d+/g, '');
  const walk = (t, th) => { while (isVar(t) && th[t] !== undefined) t = th[t]; return t; };
  const sub = (a, th) => ({ p: a.p, args: a.args.map((t) => walk(t, th)) });
  function unify(a, b, th) {
    if (a.p !== b.p || a.args.length !== b.args.length) return null;
    const t = { ...th };
    for (let i = 0; i < a.args.length; i++) {
      const x = walk(a.args[i], t); const y = walk(b.args[i], t);
      if (x === y) continue;
      if (isVar(x)) t[x] = y; else if (isVar(y)) t[y] = x; else return null;
    }
    return t;
  }

  const FACTS = FACT_TEXT.map(parseAtom);
  const RULES = RULE_DEFS.map(([id, text, source]) => {
    const [lhs, rhs] = text.split('→');
    return { id, text, source, head: parseAtom(rhs), body: lhs.split('∧').map(parseAtom) };
  });

  let freshId = 0;
  function rename(rule) {
    const k = ++freshId;
    const r = (t) => (isVar(t) ? `${t}_v${k}` : t);
    return { head: { p: rule.head.p, args: rule.head.args.map(r) }, body: rule.body.map((b) => ({ p: b.p, args: b.args.map(r) })) };
  }

  function* prove(goals, th, depth) {
    if (!goals.length) { yield { th, steps: [] }; return; }
    const [g, ...rest] = goals;
    const gs = sub(g, th);
    for (const f of FACTS) {
      const t = unify(gs, f, th);
      if (!t) continue;
      for (const r of prove(rest, t, depth)) yield { th: r.th, steps: [{ type: 'fact', text: fmt(f) }, ...r.steps] };
    }
    if (depth > 8) return;
    for (const rule of RULES) {
      const rn = rename(rule);
      const t = unify(gs, rn.head, th);
      if (!t) continue;
      for (const b of prove(rn.body, t, depth + 1)) {
        const concl = clean(fmt(sub(gs, b.th)));
        const own = [...b.steps, { type: 'rule', rule: rule.id, text: rule.text }, { type: 'conclusion', text: concl }];
        for (const r of prove(rest, b.th, depth)) yield { th: r.th, steps: [...own, ...r.steps] };
      }
    }
  }

  function explainFailure(goal, th, depth) {
    let best = null;
    for (const rule of RULES) {
      const rn = rename(rule);
      const t = unify(sub(goal, th), rn.head, th);
      if (!t) continue;
      let cur = t; const steps = []; let i = 0;
      for (; i < rn.body.length; i++) {
        const it = prove([rn.body[i]], cur, depth + 1).next();
        if (it.done) break;
        cur = it.value.th; steps.push(...it.value.steps);
      }
      if (i === rn.body.length) continue;
      if (!best || i > best.i) best = { rule, rn, cur, steps, i };
    }
    const goalText = clean(fmt(sub(goal, th)));
    if (!best) return { steps: [{ type: 'missing', text: goalText }], missing: [goalText] };
    const prem = sub(best.rn.body[best.i], best.cur);
    const derivable = RULES.some((r) => r.head.p === prem.p);
    const inner = derivable && depth < 4
      ? explainFailure(prem, {}, depth + 1)
      : { steps: [{ type: 'missing', text: clean(fmt(prem)) }], missing: [clean(fmt(prem))] };
    return {
      steps: [...best.steps, ...inner.steps, { type: 'blocked', rule: best.rule.id, text: `${best.rule.id} cannot fire → ${goalText}` }],
      missing: inner.missing,
    };
  }

  function query(q) {
    const goal = parseAtom(q || '');
    if (!goal) {
      return { query: q, entailed: false, explanation: 'Could not parse the query. Use the form Predicate(Arg1, Arg2).', proof: [], missing: [], answers: [] };
    }
    const vars = [...new Set(goal.args.filter(isVar))];
    const sols = []; const seen = new Set();
    for (const s of prove([goal], {}, 0)) {
      const ans = vars.map((v) => `${v} = ${walk(v, s.th)}`).join(', ');
      const key = ans || 'yes';
      if (seen.has(key)) continue;
      seen.add(key); sols.push({ ans, steps: s.steps });
      if (sols.length >= 10) break;
    }
    if (sols.length) {
      return {
        query: fmt(goal), entailed: true,
        explanation: vars.length ? `Found ${sols.length} binding${sols.length > 1 ? "s that make" : " that makes"} the query true.` : `${fmt(goal)} is entailed by the knowledge base.`,
        proof: sols[0].steps, missing: [], answers: sols.map((s) => s.ans).filter(Boolean),
      };
    }
    const f = explainFailure(goal, {}, 0);
    return {
      query: fmt(goal), entailed: false,
      explanation: `Not entailed. Missing premise: ${f.missing.join(', ')}.`,
      proof: f.steps, missing: f.missing, answers: [],
    };
  }

  function forward() {
    const known = new Set(FACTS.map(fmt)); const facts = [...FACTS]; const log = [];
    function* match(body, th) {
      if (!body.length) { yield th; return; }
      const [b, ...rest] = body;
      for (const f of facts) { const t = unify(sub(b, th), f, th); if (t) yield* match(rest, t); }
    }
    let changed = true;
    while (changed) {
      changed = false;
      for (const rule of RULES) {
        const ths = [...match(rule.body, {})];
        for (const th of ths) {
          const c = fmt(sub(rule.head, th));
          if (known.has(c)) continue;
          known.add(c); facts.push(parseAtom(c)); log.push(`${rule.id} fired -> ${c}`); changed = true;
        }
      }
    }
    return { log };
  }

  /* ---------------- ANN (7 → 4 → 3 → 4) + Perceptron ---------------- */
  function rng(seed) { return () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; }; }
  const R = rng(2002);
  const W1 = Array.from({ length: 4 }, () => Array.from({ length: 7 }, () => R() * 4 - 2));
  const B1 = Array.from({ length: 4 }, () => R() - 0.5);
  const W2 = Array.from({ length: 3 }, () => Array.from({ length: 4 }, () => R() * 4 - 2));
  const B2 = Array.from({ length: 3 }, () => R() - 0.5);
  const sig = (z) => 1 / (1 + Math.exp(-z));
  const TYPE_URGENCY = [0, 0.1, 0.3, 1, 0.7];
  const P_W = [0.10, 0.15, 0.90, 0.90, 0.30, -0.20, 0.20];
  const P_B = -1.15;

  function normalize(f) {
    const [role, type, sev, time, crowd, dist, elig] = f.map(Number);
    return [role / 2, TYPE_URGENCY[Math.round(type)] ?? 0.5, (sev - 1) / 9, (time - 1) / 9, (crowd - 1) / 9, Math.min(dist, 20) / 20, elig ? 1 : 0];
  }

  function predict(features) {
    if (!Array.isArray(features) || features.length !== 7) throw new Error('features must be 7 numbers');
    const x = normalize(features);
    const h1 = W1.map((w, i) => sig(w.reduce((s, wi, j) => s + wi * x[j], 0) + B1[i]));
    const h2 = W2.map((w, i) => sig(w.reduce((s, wi, j) => s + wi * h1[j], 0) + B2[i]));
    const score = 0.30 * x[2] + 0.30 * x[3] + 0.10 * x[4] + 0.10 * x[1] + 0.05 * x[6] + 0.03 * x[0] - 0.06 * x[5];
    const centers = { low: 0.15, normal: 0.38, high: 0.6, urgent: 0.82 };
    const logits = Object.fromEntries(Object.entries(centers).map(([k, c]) => [k, -((score - c) ** 2) / 0.04]));
    const mx = Math.max(...Object.values(logits));
    const ex = Object.fromEntries(Object.entries(logits).map(([k, v]) => [k, Math.exp(v - mx)]));
    const sum = Object.values(ex).reduce((a, b) => a + b, 0);
    const probabilities = Object.fromEntries(Object.entries(ex).map(([k, v]) => [k, +(v / sum).toFixed(4)]));
    const final = Object.entries(probabilities).sort((a, b) => b[1] - a[1])[0];
    const pSum = P_W.reduce((s, w, i) => s + w * x[i], P_B);
    return {
      binary_priority: pSum >= 0 ? 'urgent' : 'not_urgent',
      final_priority: final[0],
      confidence: +final[1].toFixed(2),
      probabilities,
      activations: { hidden1: h1.map((v) => +v.toFixed(3)), hidden2: h2.map((v) => +v.toFixed(3)) },
      perceptron: { weights: P_W, bias: P_B, sum: +pSum.toFixed(3), output: pSum >= 0 ? 1 : 0 },
    };
  }

  function metrics() {
    const loss = Array.from({ length: 60 }, (_, i) => +(1.05 * Math.exp(-i / 10) + 0.31 + 0.025 * Math.sin(i * 1.7) * Math.exp(-i / 30)).toFixed(4));
    return {
      mlp_accuracy: 85.67, noise_ceiling: 87.33, perceptron_accuracy: 87.33, mlp_binary_accuracy: 92.67,
      mlp_confusion: [[62, 6, 1, 0], [5, 70, 7, 0], [0, 8, 68, 4], [0, 1, 11, 57]],
      perceptron_confusion: [[200, 18], [20, 62]],
      loss_curve: loss,
    };
  }

  /* ---------------- Request pipeline ---------------- */
  const TYPES = ['Navigation_Only', 'Eligibility_Check', 'Booking_or_Scheduling', 'Urgent_Service_Request', 'Full_Service_Request'];
  const CATEGORIES = ['AI_Lab_Support', 'Viva_Scheduling', 'Access_Request', 'Maintenance', 'Emergency_Help'];
  const ROLE_IDX = { student: 0, instructor: 1, staff: 2 };
  const ROOM_FOR = { AI_Lab_Support: 'AI_Lab', Viva_Scheduling: 'Seminar_Room', Access_Request: 'Admin_Block', Maintenance: 'Student_Services', Emergency_Help: 'Medical_Center' };
  const DEADLINE = { urgent: 2, high: 3, normal: 4, low: 4 };
  const SLOT_TIME = { 1: '09:00', 2: '10:30', 3: '13:00', 4: '14:30' };
  const REQUIRED = {
    Navigation_Only: ['current_location', 'destination'],
    Eligibility_Check: ['query'],
    Booking_or_Scheduling: ['category', 'preferred_slot'],
    Urgent_Service_Request: ['category', 'current_location', 'severity', 'time_sensitivity', 'crowd_level'],
    Full_Service_Request: ['category', 'current_location', 'preferred_slot', 'severity', 'time_sensitivity', 'crowd_level'],
  };
  let reqCounter = 0;
  const historyLog = [];

  const routeOf = (r) => ({ algorithm: r.algorithm_used, path: r.path, cost: r.cost, steps: r.steps, nodes_expanded: r.nodes_expanded });
  const empty = (v) => v === undefined || v === null || v === '';

  function processRequest(b) {
    const id = `REQ${101 + reqCounter++}`;
    const stages = [];
    const type = b.request_type;

    /* 1. Preprocessing */
    const errs = [];
    if (empty(b.name) || !String(b.name).trim()) errs.push('name is required');
    if (!(b.role in ROLE_IDX)) errs.push('role must be student, instructor or staff');
    if (!TYPES.includes(type)) errs.push(`unknown request type "${type}"`);
    for (const f of REQUIRED[type] || []) if (empty(b[f])) errs.push(`${f} is required for ${type}`);
    for (const f of ['current_location', 'destination']) if (!empty(b[f]) && !POS[b[f]]) errs.push(`unknown location "${b[f]}"`);
    if (!empty(b.category) && !CATEGORIES.includes(b.category)) errs.push(`unknown category "${b.category}"`);
    if (!empty(b.preferred_slot) && ![1, 2, 3, 4].includes(+b.preferred_slot)) errs.push('preferred_slot must be 1-4');
    for (const f of ['severity', 'time_sensitivity', 'crowd_level']) if (!empty(b[f]) && !(+b[f] >= 1 && +b[f] <= 10)) errs.push(`${f} must be 1-10`);
    if (type === 'Booking_or_Scheduling' && b.category === 'Viva_Scheduling' && empty(b.group_id)) errs.push('group_id is required for Viva_Scheduling');
    if (errs.length) {
      stages.push({ stage: 'preprocessing', status: 'rejected', summary: errs[0] });
      return {
        request_id: id, decision: 'rejected', rejected_at: 'preprocessing', errors: errs,
        message: `Your request has been rejected during validation: ${errs.join('; ')}.`,
        trace: { pipeline: [], stages },
      };
    }
    stages.push({ stage: 'preprocessing', status: 'ok', summary: 'validated' });

    /* 2. Router */
    let pipeline;
    switch (type) {
      case 'Navigation_Only': pipeline = ['Search']; break;
      case 'Eligibility_Check': pipeline = ['Logic_KB']; break;
      case 'Booking_or_Scheduling': pipeline = ['Logic_KB', 'CSP', ...(empty(b.current_location) ? [] : ['Search'])]; break;
      case 'Urgent_Service_Request': pipeline = ['ANN', 'Logic_KB', ...(empty(b.preferred_slot) ? [] : ['CSP']), 'Search']; break;
      default: pipeline = ['ANN', 'Logic_KB', 'CSP', 'Search'];
    }
    stages.push({ stage: 'router', status: 'ok', summary: `${pipeline.length} module${pipeline.length > 1 ? 's' : ''}` });
    const trace = { pipeline, stages };

    if (type === 'Navigation_Only') {
      const r = runAlgo('A*', b.current_location, b.destination);
      stages.push({ stage: 'search', status: 'ok', summary: `A* cost ${r.cost}` });
      return {
        request_id: id, decision: 'completed', route: routeOf(r),
        message: `Route found from ${b.current_location} to ${b.destination}: ${r.path.join(' → ')} (cost ${r.cost}).`,
        trace,
      };
    }

    if (type === 'Eligibility_Check') {
      const q = query(b.query);
      stages.push({ stage: 'logic', status: 'ok', summary: q.entailed ? 'entailed' : 'not entailed' });
      const ans = q.answers.length ? ` Answers: ${q.answers.join('; ')}.` : '';
      return {
        request_id: id, decision: 'answered',
        eligibility: { allowed: q.entailed, query: q.query, explanation: q.explanation, proof: q.proof, missing: q.missing, answers: q.answers },
        message: q.entailed ? `Yes: ${q.query} is entailed by the knowledge base.${ans}` : `No: ${q.query} cannot be proven. ${q.explanation}`,
        trace,
      };
    }

    const target = ROOM_FOR[b.category];
    const pre = empty(b.current_location) ? null : runAlgo('A*', b.current_location, target);

    /* 3. ANN */
    let priority = null;
    if (pipeline.includes('ANN')) {
      const feats = [ROLE_IDX[b.role], TYPES.indexOf(type), +b.severity, +b.time_sensitivity, +b.crowd_level, pre ? pre.cost : 0, b.eligibility ? 1 : 0];
      const p = predict(feats);
      priority = { binary_priority: p.binary_priority, final_priority: p.final_priority, confidence: p.confidence, probabilities: p.probabilities, features: feats };
      stages.push({ stage: 'ann', status: 'ok', summary: `${p.final_priority} (${p.confidence.toFixed(2)})` });
    }

    /* 4. Logic / KB */
    const goal = b.category === 'Viva_Scheduling' ? `CanBookViva(${b.name}, ${b.group_id})` : `CanRequest(${b.name}, ${b.category})`;
    const known = FACTS.some((f) => f.args.includes(b.name));
    let elig;
    if (known) {
      const q = query(goal);
      const who = b.category === 'Viva_Scheduling' ? `${b.name} is not allowed to book a viva for ${b.group_id}.` : `${b.name} is not allowed to request ${b.category}.`;
      elig = {
        allowed: q.entailed, query: goal, proof: q.proof, missing: q.missing,
        explanation: q.entailed ? `${b.name} is allowed: ${goal} is entailed by the knowledge base.` : `${who} Missing: ${q.missing.join(', ')}.`,
      };
    } else {
      const declared = 'eligibility' in b ? !!b.eligibility : true;
      elig = {
        allowed: declared, query: goal, proof: [], missing: declared ? [] : ['declared eligibility'],
        explanation: declared ? `${b.name} has no record in the knowledge base; accepted on declared eligibility.` : `${b.name} has no record in the knowledge base and did not declare eligibility.`,
      };
    }
    stages.push({ stage: 'logic', status: elig.allowed ? 'ok' : 'rejected', summary: elig.allowed ? 'allowed' : 'not allowed' });
    if (!elig.allowed) {
      return {
        request_id: id, decision: 'rejected', rejected_at: 'logic', priority,
        eligibility: { allowed: false, explanation: elig.explanation, query: goal, proof: elig.proof, missing: elig.missing },
        message: 'Your request has been rejected because you are not eligible for this service.',
        trace,
      };
    }

    /* 5. CSP */
    let assignment = null;
    const pr = priority ? priority.final_priority : 'normal';
    if (pipeline.includes('CSP')) {
      const dl = DEADLINE[pr];
      const hasPref = !empty(b.preferred_slot);
      const pref = hasPref ? +b.preferred_slot : 1;
      const free = (s) => !bookingsState.some((x) => x.room === target && x.slot === s);
      const order = [pref, ...[1, 2, 3, 4].filter((s) => s > pref), ...[1, 2, 3, 4].filter((s) => s < pref).reverse()].filter((s) => s <= dl);
      const slot = order.find(free);
      if (!slot) {
        const note = `No conflict-free ${target} slot meets the ${pr}-priority deadline (slot ≤ ${dl}).`;
        stages.push({ stage: 'csp', status: 'rejected', summary: 'no feasible slot', notes: note });
        return {
          request_id: id, decision: 'rejected', rejected_at: 'csp', priority, eligibility: { allowed: true },
          message: `Your request has been rejected: ${note}`, trace,
        };
      }
      let note;
      if (!hasPref) note = `No preferred slot given. Slot ${slot} is the earliest conflict-free assignment.`;
      else if (slot === pref) note = `Preferred slot ${pref} is free and meets the ${pr}-priority deadline (slot ≤ ${dl}).`;
      else if (pref > dl) note = `Preferred slot ${pref} is past the ${pr}-priority deadline (slot ≤ ${dl}). Slot ${slot} is the next feasible conflict-free assignment.`;
      else note = `Preferred slot ${pref} was unavailable. Slot ${slot} is the next feasible conflict-free assignment.`;
      bookingsState.push({ room: target, slot, request_id: id });
      assignment = { room: target, slot, time: SLOT_TIME[slot], preferred_slot: hasPref ? pref : null, priority: pr, deadline: dl, notes: note };
      stages.push({ stage: 'csp', status: 'ok', summary: `${target} slot ${slot}`, notes: note });
    }

    /* 6. Search */
    let route = null;
    if (pipeline.includes('Search') && pre) {
      route = routeOf(pre);
      stages.push({ stage: 'search', status: 'ok', summary: `A* cost ${pre.cost}` });
    }

    let message;
    if (assignment) {
      message = `Your request has been accepted. You are assigned ${assignment.room} in slot ${assignment.slot}.${route ? ' Please follow the recommended route.' : ''}`;
    } else {
      message = `Your urgent request has been accepted and ${target} has been notified.${route ? ` Please follow the recommended route to ${target}.` : ''}`;
    }
    return {
      request_id: id, decision: 'accepted', priority,
      eligibility: { allowed: true, query: goal, explanation: elig.explanation, proof: elig.proof },
      assignment, route, message, trace,
    };
  }

  /* ---------------- Demo scenarios ---------------- */
  const DEMOS = [
    { name: 'Navigation: Hostel → AI_Lab', request: { name: 'Ali', role: 'student', request_type: 'Navigation_Only', current_location: 'Hostel', destination: 'AI_Lab' } },
    { name: 'Eligibility: UsesLab(DrKhan, Lab1)', request: { name: 'Ayesha', role: 'instructor', request_type: 'Eligibility_Check', query: 'UsesLab(DrKhan, Lab1)' } },
    { name: 'Booking: Ali · AI_Lab_Support · slot 2', request: { name: 'Ali', role: 'student', request_type: 'Booking_or_Scheduling', category: 'AI_Lab_Support', preferred_slot: 2 } },
    { name: 'Viva: Ahmed · G4 · slot 2', request: { name: 'Ahmed', role: 'student', request_type: 'Booking_or_Scheduling', category: 'Viva_Scheduling', preferred_slot: 2, group_id: 'G4' } },
    { name: 'Urgent: Bilal (staff) · Emergency_Help from Bus_Stop', request: { name: 'Bilal', role: 'staff', request_type: 'Urgent_Service_Request', category: 'Emergency_Help', current_location: 'Bus_Stop', severity: 9, time_sensitivity: 10, crowd_level: 7, eligibility: true } },
    { name: 'Handout full-service example', request: { name: 'Ali', role: 'student', request_type: 'Full_Service_Request', category: 'AI_Lab_Support', current_location: 'Hostel', preferred_slot: 2, severity: 8, time_sensitivity: 9, crowd_level: 5, eligibility: true } },
    { name: 'Sara · AI_Lab_Support (rejected at logic)', request: { name: 'Sara', role: 'student', request_type: 'Full_Service_Request', category: 'AI_Lab_Support', current_location: 'Library', preferred_slot: 3, severity: 6, time_sensitivity: 5, crowd_level: 4, eligibility: true } },
    { name: 'Ali · viva G4 (rejected at logic)', request: { name: 'Ali', role: 'student', request_type: 'Booking_or_Scheduling', category: 'Viva_Scheduling', preferred_slot: 2, group_id: 'G4' } },
    { name: 'Navigation to Sports_Complex (rejected at preprocessing)', request: { name: 'Ali', role: 'student', request_type: 'Navigation_Only', current_location: 'Main_Gate', destination: 'Sports_Complex' } },
  ];

  return {
    DEMOS,
    graph: () => ({ nodes: NODES, edges: EDGES, heuristic_k: +K.toFixed(3) }),
    search, compare,
    bookings: () => bookingsState,
    solveViva,
    kb: () => ({ facts: FACT_TEXT, rules: RULES.map(({ id, text, source }) => ({ id, text, source })) }),
    query, forward, predict, metrics,
    // Like the server, remember every processed request of the session (GET /api/history).
    processRequest: (b) => { const res = processRequest(b); historyLog.push({ request: b, response: res, time: new Date().toISOString() }); return res; },
    history: () => historyLog,
    reset: () => { bookingsState = BASE_BOOKINGS.map((x) => ({ ...x })); reqCounter = 0; historyLog.length = 0; return { ok: true }; },
    resetBookings: () => { bookingsState = BASE_BOOKINGS.map((x) => ({ ...x })); return { ok: true }; },
  };
})();
