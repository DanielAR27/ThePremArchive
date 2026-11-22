// Mock adapter: answers like the search server (see API.md) using project 2's real
// top-10 results and judged pool. Judgments are kept in this browser's localStorage.
import datos from '../mock/datos.json';
import { computeMetrics } from '../lib/metricas.js';

const STORE_KEY = 'tpa.judgments.v1';
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
const norm = (s) => s.toLowerCase().replace(/\s+/g, ' ').trim();
const tokens = (s) => norm(s).split(/[^a-z0-9]+/).filter((t) => t.length > 1);

function readStored() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) || '[]');
  } catch {
    return [];
  }
}
function writeStored(list) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(list));
  } catch {
    /* storage unavailable: judgments live for this session only */
  }
}
let memory = readStored();

function toResult(doc, rank, score) {
  const d = datos.docs[doc];
  return {
    rank,
    doc,
    score,
    url: `https://${d.host}/`,
    title: d.title,
    host: d.host,
    publishedAt: null,
    snippet: d.snippet,
  };
}

export async function info() {
  await delay(120);
  const { collection, engines, policies } = datos;
  return { collection, engines, policies, default: datos.default };
}

export async function queries() {
  await delay(80);
  return datos.queries;
}

export async function search({ q, engine, policy, site, page = 1, size = 10 }) {
  const started = performance.now();
  const key = `${engine}:${policy}`;
  const test = datos.queries.find((x) => norm(x.text) === norm(q));
  const terms = tokens(q);
  let ranked;

  if (test && datos.rankings[key]?.[test.id]) {
    const list = datos.rankings[key][test.id];
    ranked = list.map((doc, i) => ({ doc, score: +(1 - i * 0.061).toFixed(4) }));
  } else {
    ranked = Object.entries(datos.docs)
      .map(([doc, d]) => {
        const hay = tokens(`${d.title} ${d.title} ${d.snippet}`);
        const score = terms.reduce((acc, t) => acc + hay.filter((h) => h.startsWith(t)).length, 0);
        return { doc, score: +(score / (hay.length || 1)).toFixed(4) };
      })
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score);
  }
  if (site) ranked = ranked.filter((r) => datos.docs[r.doc].host === site);

  const timing = test ? datos.timings[key]?.[test.id] : null;
  await delay(Math.min(timing ?? 180, 450));
  const start = (page - 1) * size;
  return {
    query: q,
    terms,
    engine,
    policy,
    site: site || null,
    total: ranked.length,
    tookMs: +(timing ?? performance.now() - started).toFixed(1),
    page,
    size,
    results: ranked.slice(start, start + size).map((r, i) => toResult(r.doc, start + i + 1, r.score)),
    testQueryId: test?.id ?? null,
  };
}

export async function judgments({ queryId, evaluator } = {}) {
  await delay(60);
  return memory.filter((j) => (!queryId || j.queryId === queryId) && (!evaluator || j.evaluator === evaluator));
}

export async function saveJudgment(input) {
  await delay(90);
  const judgedAt = new Date().toISOString();
  const i = memory.findIndex(
    (j) => j.queryId === input.queryId && j.query === input.query && j.doc === input.doc && j.evaluator === input.evaluator,
  );
  const saved = { id: i >= 0 ? memory[i].id : memory.length + 1, ...input, judgedAt };
  if (i >= 0) memory[i] = saved;
  else memory.push(saved);
  writeStored(memory);
  return saved;
}

export async function metrics({ engine, policy, includeBaseline = true }) {
  await delay(160);
  const judged = memory.filter((j) => j.queryId);
  const all = includeBaseline ? [...datos.baselineJudgments, ...judged] : judged;
  const result = computeMetrics({ queries: datos.queries, rankings: datos.rankings, judgments: all, engine, policy });
  result.baseline = includeBaseline
    ? {
        label: 'Project 2 pool',
        judgments: datos.baselineJudgments.length,
        relevant: datos.baselineJudgments.filter((j) => j.judgment === 'relevant').length,
        date: datos.baselineDate,
      }
    : null;
  return result;
}

export async function deleteJudgments({ evaluator }) {
  await delay(90);
  const before = memory.length;
  memory = memory.filter((j) => j.evaluator !== evaluator);
  writeStored(memory);
  return { deleted: before - memory.length };
}

export const isMock = true;
