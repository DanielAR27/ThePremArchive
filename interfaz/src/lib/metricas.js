// Reference implementation of the evaluation metrics (Manning, Raghavan & Schütze, 2008, ch. 8).
// Used by the mock adapter; the search server can port it as is.
// Unjudged documents count as not relevant; "unsure" counts as judged but not relevant.

export const CUTOFF = 10;

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

/** Latest judgment per (queryId, doc): later entries win. */
export function relevanceMap(judgments) {
  const map = new Map();
  for (const j of judgments) map.set(`${j.queryId}|${j.doc}`, j.judgment);
  return map;
}

/** Metrics for one ranked list. `rel` is an array of 1 / 0 / null per rank; `knownRelevant` comes from the pool. */
export function scoreRanking(rel, knownRelevant) {
  const top = rel.slice(0, CUTOFF);
  const hit = top.map((r) => (r === 1 ? 1 : 0));
  const pAt = (k) => hit.slice(0, k).reduce((a, b) => a + b, 0) / k;

  const first = hit.indexOf(1);
  const rr = first === -1 ? 0 : 1 / (first + 1);

  let found = 0;
  let sumPrec = 0;
  hit.forEach((h, i) => {
    if (h) {
      found += 1;
      sumPrec += found / (i + 1);
    }
  });
  const ap = knownRelevant ? sumPrec / Math.min(knownRelevant, CUTOFF) : 0;

  const dcg = hit.reduce((acc, h, i) => acc + h / Math.log2(i + 2), 0);
  const ideal = Array.from({ length: Math.min(knownRelevant, CUTOFF) }, (_, i) => 1 / Math.log2(i + 2))
    .reduce((a, b) => a + b, 0);
  const ndcg10 = ideal ? dcg / ideal : 0;

  return { p5: pAt(5), p10: pAt(10), rr, ap, ndcg10, judged: top.filter((r) => r !== null).length };
}

/**
 * Full metrics payload, shaped like GET /api/metrics.
 * rankings: { "engine:policy": { queryId: [doc, ...] } }
 */
export function computeMetrics({ queries, rankings, judgments, engine, policy }) {
  const rel = relevanceMap(judgments);
  const relevantPerQuery = new Map();
  for (const [key, value] of rel) {
    if (value !== 'relevant') continue;
    const q = key.split('|')[0];
    relevantPerQuery.set(q, (relevantPerQuery.get(q) || 0) + 1);
  }

  const scoreConfig = (configKey) =>
    queries.map((q) => {
      const docs = rankings[configKey]?.[q.id] || [];
      const relevantAtRank = docs.slice(0, CUTOFF).map((d) => {
        const j = rel.get(`${q.id}|${d}`);
        return j === undefined ? null : j === 'relevant' ? 1 : 0;
      });
      return { id: q.id, text: q.text, relevantAtRank, ...scoreRanking(relevantAtRank, relevantPerQuery.get(q.id) || 0) };
    });

  const perQuery = scoreConfig(`${engine}:${policy}`);
  const summarize = (rows) => ({
    p5: mean(rows.map((r) => r.p5)),
    p10: mean(rows.map((r) => r.p10)),
    mrr: mean(rows.map((r) => r.rr)),
    map: mean(rows.map((r) => r.ap)),
    ndcg10: mean(rows.map((r) => r.ndcg10)),
  });

  const byConfig = Object.keys(rankings)
    .sort()
    .map((key) => {
      const [e, p] = key.split(':');
      return { engine: e, policy: p, ...summarize(scoreConfig(key)) };
    });

  const perDay = new Map();
  for (const j of judgments) {
    if (!j.judgedAt) continue;
    const day = j.judgedAt.slice(0, 10);
    perDay.set(day, (perDay.get(day) || 0) + 1);
  }

  return {
    engine,
    policy,
    summary: {
      queries: queries.length,
      judged: rel.size,
      evaluators: new Set(judgments.map((j) => j.evaluator)).size,
      ...summarize(perQuery),
    },
    perQuery,
    byConfig,
    activity: [...perDay].sort().map(([date, n]) => ({ date, judgments: n })),
  };
}
