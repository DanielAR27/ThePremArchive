import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { api } from '../api/client.js';
import { useInfo } from '../App.jsx';
import { HBarChart, Legend, SERIES, VBarChart } from '../components/Charts.jsx';
import { Crawling } from '../components/Results.jsx';
import { fmt2, fmtInt, parseDate } from '../lib/format.jsx';

const SCORES = [
  { key: 'map', name: 'MAP', def: 'Mean average precision: how early, on average, the relevant documents appear.' },
  { key: 'mrr', name: 'MRR', def: 'Mean reciprocal rank: 1 ÷ the position of the first relevant result.' },
  { key: 'p5', name: 'P@5', def: 'Share of the first five results that are relevant.' },
  { key: 'p10', name: 'P@10', def: 'Share of the first ten results that are relevant.' },
  { key: 'ndcg10', name: 'nDCG@10', def: 'Ranking quality against the ideal order, discounting lower positions.' },
];
const COLUMNS = [
  { key: 'judged', label: 'Rated', title: 'How many of the top 10 results have been rated', fmt: (v) => v },
  { key: 'p5', label: 'P@5', title: 'Precision at 5: share of the top 5 results that are relevant', fmt: fmt2 },
  { key: 'p10', label: 'P@10', title: 'Precision at 10: share of the top 10 results that are relevant', fmt: fmt2 },
  { key: 'rr', label: 'RR', title: 'Reciprocal rank: 1 ÷ position of the first relevant result', fmt: fmt2 },
  { key: 'ap', label: 'AP', title: 'Average precision across the top 10 results', fmt: fmt2 },
  { key: 'ndcg10', label: 'nDCG@10', title: 'Normalized discounted cumulative gain at 10', fmt: fmt2 },
];

export default function MetricsPage() {
  const info = useInfo();
  const [engine, setEngine] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [baseline, setBaseline] = useState(true);
  const [state, setState] = useState({ status: 'loading' });
  const [sort, setSort] = useState({ key: 'id', dir: 1 });

  useEffect(() => {
    if (!info) return;
    setEngine((e) => e || info.default.engine);
    setPolicy((p) => p || info.default.policy);
  }, [info]);

  useEffect(() => {
    if (!engine || !policy || !info) return;
    let alive = true;
    setState((s) => ({ ...s, status: 'loading' }));
    Promise.all([
      ...info.engines.map((e) => api.metrics({ engine: e.id, policy, includeBaseline: baseline })),
      api.judgments(),
    ])
      .then((res) => {
        if (!alive) return;
        const judgments = res.pop();
        const byEngine = Object.fromEntries(info.engines.map((e, i) => [e.id, res[i]]));
        setState({ status: 'done', byEngine, judgments });
      })
      .catch((e) => alive && setState({ status: 'error', error: e.message }));
    return () => {
      alive = false;
    };
  }, [engine, policy, baseline, info]);

  const showEngines = Boolean(info && info.engines.length > 1);
  const showPolicies = Boolean(info && info.policies.length > 1);
  const lab = showEngines || showPolicies;
  const showFilters = lab || api.isMock;
  const keys = info ? info.engines.map((e) => e.id) : [];
  const m = state.byEngine?.[engine];
  const other = keys.find((k) => k !== engine);
  const mOther = other ? state.byEngine?.[other] : null;

  const sorted = useMemo(() => {
    if (!m) return [];
    return [...m.perQuery].sort((a, b) =>
      sort.key === 'id' ? a.id.localeCompare(b.id) * sort.dir : (a[sort.key] - b[sort.key]) * sort.dir,
    );
  }, [m, sort]);

  const evaluators = useMemo(() => {
    const map = new Map();
    for (const j of state.judgments || []) {
      const e = map.get(j.evaluator) || { name: j.evaluator, total: 0, relevant: 0, last: null };
      e.total += 1;
      if (j.judgment === 'relevant') e.relevant += 1;
      if (!e.last || j.judgedAt > e.last) e.last = j.judgedAt;
      map.set(j.evaluator, e);
    }
    return [...map.values()].sort((a, b) => b.total - a.total);
  }, [state.judgments]);

  const engineLabel = (id) => SERIES[id]?.label || id;
  const toggleSort = (key) => setSort((s) => ({ key, dir: s.key === key ? -s.dir : key === 'id' ? 1 : -1 }));

  const topicTable = m && (
    <figure className="figure">
      <div className="figure-head">
        <h2>{lab ? 'Every query' : 'Every topic'}</h2>
        <span className="figure-note">
          {lab ? `${engineLabel(engine)}, policy ${policy} · select a column to sort` : 'Select a column to sort · click any topic to rate it'}
        </span>
      </div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th scope="col" aria-sort={sort.key === 'id' ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
                <button type="button" onClick={() => toggleSort('id')}>
                  {lab ? 'Query' : 'Topic'} <SortIcon on={sort.key === 'id'} dir={sort.dir} />
                </button>
              </th>
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  title={c.title}
                  aria-sort={sort.key === c.key ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}
                >
                  <button type="button" onClick={() => toggleSort(c.key)} title={c.title}>
                    {c.label} <SortIcon on={sort.key === c.key} dir={sort.dir} />
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((q) => (
              <tr key={q.id}>
                <td className="q">
                  <Link
                    className="topic-link"
                    to={`/evaluate?query=${q.id}${lab ? `&engine=${engine}&policy=${policy}` : ''}`}
                    title={`Rate results for “${q.text}”`}
                  >
                    <b>{Number(q.id.slice(1))}</b>
                    {q.text}
                  </Link>
                </td>
                {COLUMNS.map((c) => (
                  <td key={c.key} className={c.key !== 'judged' && q[c.key] === 1 ? 'best' : undefined}>
                    {c.fmt(q[c.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );

  const contributorsCard = m && (
    <figure className="figure">
      <div className="figure-head">
        <h2>{lab ? 'Who judged' : 'Who rated'}</h2>
        <span className="figure-note num">{fmtInt(m.summary.judged)} results rated</span>
      </div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th scope="col">{lab ? 'Evaluator' : 'Contributor'}</th>
              <th scope="col">{lab ? 'Judgments' : 'Ratings'}</th>
              <th scope="col">Relevant</th>
              <th scope="col">Last</th>
            </tr>
          </thead>
          <tbody>
            {m.baseline && (
              <tr>
                <td className="left">{m.baseline.label}</td>
                <td>{fmtInt(m.baseline.judgments)}</td>
                <td>{fmtInt(m.baseline.relevant)}</td>
                <td>{shortDate(m.baseline.date)}</td>
              </tr>
            )}
            {evaluators.map((e) => (
              <tr key={e.name}>
                <td className="left">{e.name}</td>
                <td>{e.total}</td>
                <td>{e.relevant}</td>
                <td>{shortDate(e.last)}</td>
              </tr>
            ))}
            {!evaluators.length && !m.baseline && (
              <tr>
                <td className="left" colSpan={4} style={{ whiteSpace: 'normal', color: 'var(--ink-3)' }}>
                  No one has rated results yet. <Link to="/evaluate">Open Rate results</Link> to start.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <figcaption className="figure-note">
        {lab
          ? 'Definitions follow Manning, Raghavan & Schütze (2008), ch. 8. “Unsure” counts as rated but not relevant.'
          : '“Unsure” counts toward progress, and counts as not relevant in precision scores.'}
      </figcaption>
    </figure>
  );

  return (
    <div className="metrics">
      <header className="metrics-head">
        <div>
          <h1>Metrics</h1>
          <p>
            {lab
              ? 'How well each engine answers the twelve sample queries, scored against the relevance ratings. Unrated results count as not relevant, so scores rise as more results are rated.'
              : 'How well the search answers the twelve suggested topics, based on community relevance ratings. Unrated results count as not relevant, so scores rise as more results are rated.'}
          </p>
        </div>
        {showFilters && (
          <div className="filters">
            {showEngines && (
              <label className="field">
                <span className="field-label">Engine</span>
                <select className="select" value={engine || ''} onChange={(e) => setEngine(e.target.value)}>
                  {info.engines.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {showPolicies && (
              <label className="field">
                <span className="field-label">Normalization policy</span>
                <select className="select" value={policy || ''} onChange={(e) => setPolicy(e.target.value)}>
                  {info.policies.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.id} · {p.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {api.isMock && (
              <label className="check" style={{ paddingBottom: 8 }}>
                <input type="checkbox" checked={baseline} onChange={(e) => setBaseline(e.target.checked)} />
                <span>
                  Include the ratings
                  <br />
                  from project 2
                </span>
              </label>
            )}
          </div>
        )}
      </header>

      {state.status === 'error' && (
        <div className="message error">
          <h3>The metrics could not be computed.</h3>
          <p>{state.error}</p>
        </div>
      )}
      {!m && state.status !== 'error' && <Crawling label="Counting the ratings…" rows={3} />}

      {m && (
        <>
          <dl className="scoreboard" style={{ opacity: state.status === 'loading' ? 0.6 : 1 }}>
            {SCORES.map((s) => {
              const v = m.summary[s.key];
              const o = mOther?.summary[s.key];
              return (
                <div className="score" key={s.key}>
                  <dt>{s.name}</dt>
                  <dd className="value num">{fmt2(v)}</dd>
                  {o != null && (
                    <dd className="vs num">
                      {engineLabel(other)}: {fmt2(o)}{' '}
                      {v !== o && (
                        <span style={{ color: v > o ? 'var(--olive-700)' : 'var(--burgundy-700)', fontWeight: 700 }}>
                          {v > o ? `+${fmt2(v - o)}` : `−${fmt2(o - v)}`}
                        </span>
                      )}
                    </dd>
                  )}
                  <dd className="def">{s.def}</dd>
                </div>
              );
            })}
          </dl>

          <div className="chart-grid">
            <figure className="figure">
              <div className="figure-head">
                <h2>{lab ? 'Precision at 10, by query' : 'Precision at 10, by topic'}</h2>
                {keys.length > 1 && <Legend keys={keys} />}
              </div>
              <HBarChart
                label={`Precision at 10 for each topic${lab ? `, policy ${policy}` : ''}`}
                keys={keys}
                rows={m.perQuery.map((q, i) => ({
                  label: q.text,
                  sub: String(i + 1),
                  values: Object.fromEntries(keys.map((k) => [k, state.byEngine[k].perQuery[i].p10])),
                }))}
              />
              <figcaption className="figure-note">
                {lab
                  ? `Policy ${policy}. Each pair of bars is one query; the longer the bar, the more of the top ten was rated relevant.`
                  : 'Each bar shows how many of the top ten results were rated relevant for that topic.'}
              </figcaption>
            </figure>

            {showPolicies ? (
              <figure className="figure">
                <div className="figure-head">
                  <h2>Mean average precision, by policy</h2>
                  <Legend keys={keys} />
                </div>
                <VBarChart
                  label="Mean average precision for every normalization policy and engine"
                  keys={keys}
                  highlight={policy}
                  groups={info.policies.map((p) => ({
                    label: p.id,
                    short: p.label.split(/[ ,]/)[0],
                    title: `Policy ${p.id} · ${p.label}`,
                    values: Object.fromEntries(
                      keys.map((k) => [k, m.byConfig.find((c) => c.engine === k && c.policy === p.id)?.map]),
                    ),
                  }))}
                />
                <figcaption className="figure-note">
                  Same ratings, every policy. It shows which normalization decisions from project 2 paid off in ranking
                  quality.
                </figcaption>
              </figure>
            ) : (
              contributorsCard
            )}
          </div>

          <figure className="figure">
            <div className="figure-head">
              <h2>Relevance by rank</h2>
              <div className="legend">
                <span>
                  <i style={{ background: 'var(--olive-500)' }} />
                  Relevant
                </span>
                <span>
                  <i style={{ background: 'var(--burgundy-100)', boxShadow: 'inset 0 0 0 1px rgb(138 42 62 / .3)' }} />
                  Not relevant
                </span>
                <span>
                  <i className="hatch" />
                  Not rated yet
                </span>
              </div>
            </div>
            <div className="strip" role="table" aria-label={`Rating of each of the top ten results${lab ? `, ${engineLabel(engine)}, policy ${policy}` : ''}`}>
              <span role="columnheader" />
              {Array.from({ length: 10 }, (_, i) => (
                <span key={i} className="h" role="columnheader">
                  {i + 1}
                </span>
              ))}
              <span className="h" role="columnheader" style={{ fontSize: 'var(--step--1)', fontFamily: 'var(--font-ui)' }}>
                P@10
              </span>
              {m.perQuery.map((q, qi) => (
                <div key={q.id} role="row" style={{ display: 'contents' }}>
                  <span className="qlabel" role="rowheader" title={q.text}>
                    <b>{qi + 1}</b>
                    <span>{q.text}</span>
                  </span>
                  {Array.from({ length: 10 }, (_, i) => {
                    const r = q.relevantAtRank[i];
                    const word = r === 1 ? 'relevant' : r === 0 ? 'not relevant' : 'not rated';
                    return (
                      <span
                        key={i}
                        role="cell"
                        className={`cell ${r === 1 ? 'r1' : r === 0 ? 'r0' : 'rn'}`}
                        title={`“${q.text}”, result ${i + 1}: ${word}`}
                        aria-label={`Result ${i + 1}: ${word}`}
                      />
                    );
                  })}
                  <span className="p10" role="cell">
                    {fmt2(q.p10)}
                  </span>
                </div>
              ))}
            </div>
            <figcaption className="figure-note">
              {lab
                ? `${engineLabel(engine)}, policy ${policy}. Read across a row to see where the good results sit; a strong engine fills the left side.`
                : 'Read across a row to see where relevant results appear; stronger rankings fill the left side.'}
            </figcaption>
          </figure>

          {showPolicies ? (
            <div className="lower-grid">
              {topicTable}
              {contributorsCard}
            </div>
          ) : (
            topicTable
          )}
        </>
      )}
    </div>
  );
}

function shortDate(iso) {
  if (!iso) return '—';
  const d = parseDate(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function SortIcon({ on, dir }) {
  if (!on) return <ArrowDown size={12} style={{ opacity: 0.25 }} aria-hidden />;
  return dir > 0 ? <ArrowUp size={12} aria-hidden /> : <ArrowDown size={12} aria-hidden />;
}
