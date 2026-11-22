import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, Check, CircleHelp, Trash2, X } from 'lucide-react';
import { api } from '../api/client.js';
import { useInfo } from '../App.jsx';
import { ConfigFields, Crawling, ResultRow } from '../components/Results.jsx';

const VERDICTS = [
  { v: 'relevant', label: 'Relevant', key: '1', Icon: Check },
  { v: 'not_relevant', label: 'Not relevant', key: '2', Icon: X },
  { v: 'unsure', label: 'Unsure', key: '3', Icon: CircleHelp },
];
const EVALUATOR_KEY = 'tpa.evaluator';

function readEvaluator() {
  try {
    return localStorage.getItem(EVALUATOR_KEY) || '';
  } catch {
    return '';
  }
}

export default function EvaluatePage() {
  const info = useInfo();
  const [params, setParams] = useSearchParams();
  const [queries, setQueries] = useState([]);
  const [evaluator, setEvaluator] = useState(readEvaluator);
  const [mine, setMine] = useState([]); // this evaluator's judgments, all queries
  const [results, setResults] = useState({ status: 'idle' });
  const [active, setActive] = useState(0);
  const [saved, setSaved] = useState(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const listRef = useRef(null);

  const queryId = params.get('query') || queries[0]?.id;
  const engine = params.get('engine') || info?.default.engine;
  const policy = params.get('policy') || info?.default.policy;
  const query = queries.find((q) => q.id === queryId);

  useEffect(() => {
    api.queries().then(setQueries, () => setQueries([]));
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(EVALUATOR_KEY, evaluator);
    } catch {
      /* not persisted */
    }
    if (!evaluator.trim()) {
      setMine([]);
      return;
    }
    api.judgments({ evaluator: evaluator.trim() }).then(setMine, () => setMine([]));
  }, [evaluator]);

  useEffect(() => {
    if (!query || !info) return;
    let alive = true;
    setResults({ status: 'loading' });
    setActive(0);
    api
      .search({ q: query.text, engine, policy, size: 10 })
      .then((data) => alive && setResults({ status: 'done', data }))
      .catch((e) => alive && setResults({ status: 'error', error: e.message }));
    return () => {
      alive = false;
    };
  }, [query, engine, policy, info]);

  const verdictOf = useMemo(() => {
    const m = new Map();
    for (const j of mine) m.set(`${j.queryId}|${j.doc}`, j.judgment);
    return m;
  }, [mine]);

  const judge = useCallback(
    async (r, judgment) => {
      const name = evaluator.trim();
      if (!name || !query) return;
      const entry = await api.saveJudgment({
        queryId: query.id,
        query: query.text,
        doc: r.doc,
        engine,
        policy,
        rank: r.rank,
        judgment,
        evaluator: name,
      });
      setMine((list) => [...list.filter((j) => !(j.queryId === entry.queryId && j.doc === entry.doc)), entry]);
      setSaved(new Date(entry.judgedAt));
    },
    [evaluator, query, engine, policy],
  );

  const rows = results.status === 'done' ? results.data.results : [];
  const counts = { relevant: 0, not_relevant: 0, unsure: 0 };
  for (const r of rows) {
    const v = verdictOf.get(`${queryId}|${r.doc}`);
    if (v) counts[v] += 1;
  }
  const judgedHere = counts.relevant + counts.not_relevant + counts.unsure;
  const perQuery = useMemo(() => {
    const m = new Map();
    for (const j of mine) m.set(j.queryId, (m.get(j.queryId) || 0) + 1);
    return m;
  }, [mine]);

  // Keyboard: J/K or arrows move between results, 1/2/3 judge the focused one.
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.closest('input, select, textarea') || e.metaKey || e.ctrlKey || e.altKey) return;
      if (!rows.length) return;
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        setActive((a) => Math.min(rows.length - 1, a + 1));
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        setActive((a) => Math.max(0, a - 1));
      } else {
        const verdict = VERDICTS.find((x) => x.key === e.key);
        if (verdict && evaluator.trim()) {
          e.preventDefault();
          judge(rows[active], verdict.v);
          setActive((a) => Math.min(rows.length - 1, a + 1));
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [rows, active, judge, evaluator]);

  useEffect(() => {
    listRef.current?.children[active]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [active]);

  const set = (patch) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) next.set(k, v);
    setParams(next);
  };
  const clearMine = async () => {
    await api.deleteJudgments({ evaluator: evaluator.trim() });
    setMine([]);
    setSaved(null);
    setConfirmClear(false);
  };
  const nextQuery = queries[(queries.findIndex((q) => q.id === queryId) + 1) % (queries.length || 1)];
  const noName = !evaluator.trim();

  return (
    <>
      <section className="masthead">
        <div className="masthead-inner">
          <h1 className="masthead-title">
            Evaluate
            <small>Relevance judgments</small>
          </h1>
          <p className="edition" style={{ gridColumn: 'auto', fontSize: 'var(--step-0)' }}>
            Read each result, open the original page when the snippet is not enough, and mark whether it answers the
            query. Every mark is saved at once and feeds the metrics.
          </p>
        </div>
      </section>

      <div className="page">
        <aside className="rail" aria-label="Evaluation set-up">
          <label className="field">
            <span className="field-label">Your name</span>
            <input
              className="input"
              value={evaluator}
              onChange={(e) => setEvaluator(e.target.value)}
              placeholder="e.g. Aurelio"
              autoComplete="name"
            />
            <span className="field-hint">Judgments are recorded under this name.</span>
          </label>
          {mine.length > 0 &&
            (confirmClear ? (
              <div className="field">
                <span className="field-hint">
                  Delete all {mine.length} judgments made as “{evaluator.trim()}”? This cannot be undone.
                </span>
                <div style={{ display: 'flex', gap: 'var(--s2)' }}>
                  <button type="button" className="btn btn-primary" onClick={clearMine}>
                    Delete them
                  </button>
                  <button type="button" className="btn btn-quiet" onClick={() => setConfirmClear(false)}>
                    Keep
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                className="btn btn-quiet"
                style={{ justifySelf: 'start', paddingLeft: 0 }}
                onClick={() => setConfirmClear(true)}
              >
                <Trash2 size={14} aria-hidden /> Clear my {mine.length} judgments
              </button>
            ))}
          <ConfigFields info={info} engine={engine} policy={policy} onChange={set} idPrefix="e" />
          <div className="notes-block">
            <h2 className="panel-title small">Test queries</h2>
            <ul className="query-list">
              {queries.map((q, i) => {
                const n = perQuery.get(q.id) || 0;
                return (
                  <li key={q.id}>
                    <button
                      type="button"
                      aria-current={q.id === queryId}
                      onClick={() => set({ query: q.id })}
                      title={q.text}
                    >
                      <span className="qid">{i + 1}</span>
                      <span className="qtext">{q.text}</span>
                      <span className={`qcount ${n >= 10 ? 'done' : ''}`}>{n ? `${Math.min(n, 10)}/10` : '—'}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </aside>

        <section aria-label="Results to judge" style={{ minWidth: 0 }}>
          {query && (
            <div className="sheet-head">
              <h2>“{query.text}”</h2>
              <span className="aside-note num">{judgedHere} of {rows.length || 10} judged</span>
            </div>
          )}
          {noName && (
            <div className="message">
              <h3>Who is judging?</h3>
              <p>Write your name on the left to start. It keeps your judgments apart from everyone else’s.</p>
            </div>
          )}
          {results.status === 'loading' && <Crawling label="Fetching the top ten…" rows={4} />}
          {results.status === 'error' && (
            <div className="message error">
              <h3>The results could not be loaded.</h3>
              <p>{results.error}</p>
            </div>
          )}
          {results.status === 'done' && (
            <ol className="sheet" ref={listRef}>
              {rows.map((r, i) => {
                const v = verdictOf.get(`${queryId}|${r.doc}`);
                return (
                  <ResultRow
                    key={r.doc}
                    r={r}
                    words={results.data.terms}
                    index={i}
                    className={`judging ${i === active ? 'is-active' : ''}`}
                    tabIndex={-1}
                    onMouseEnter={() => setActive(i)}
                    onFocus={() => setActive(i)}
                    children={{
                      meta: v && (
                        <span className={`stamp ${v}`}>{VERDICTS.find((x) => x.v === v).label}</span>
                      ),
                      side: (
                        <div className="judge" role="group" aria-label={`Judge result ${r.rank}`}>
                          {VERDICTS.map(({ v: value, label, key, Icon }) => (
                            <button
                              key={value}
                              type="button"
                              data-v={value}
                              aria-pressed={v === value}
                              disabled={noName}
                              onClick={() => judge(r, value)}
                              title={`${label} (${key})`}
                            >
                              <Icon size={14} strokeWidth={2.4} aria-hidden />
                              {label}
                              <kbd aria-hidden>{key}</kbd>
                            </button>
                          ))}
                        </div>
                      ),
                    }}
                  />
                );
              })}
            </ol>
          )}
        </section>

        <aside className="notes" aria-label="Progress">
          <div className="notes-block">
            <h2 className="panel-title small">This query</h2>
            <div className="tally">
              <div style={{ color: 'var(--relevant)' }}>
                <strong className="num">{counts.relevant}</strong>
                <span>Relevant</span>
              </div>
              <div style={{ color: 'var(--not-relevant)' }}>
                <strong className="num">{counts.not_relevant}</strong>
                <span>Not relevant</span>
              </div>
              <div style={{ color: 'var(--unsure)' }}>
                <strong className="num">{counts.unsure}</strong>
                <span>Unsure</span>
              </div>
            </div>
            <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={10} aria-valuenow={judgedHere}>
              <i style={{ width: `${(judgedHere / (rows.length || 10)) * 100}%` }} />
            </div>
            <p className="saved" aria-live="polite">
              {saved && (
                <>
                  <Check size={14} aria-hidden /> Saved at{' '}
                  {saved.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  {api.isMock && ' in this browser'}
                </>
              )}
            </p>
            {nextQuery && judgedHere === rows.length && rows.length > 0 && (
              <button className="btn btn-primary" type="button" onClick={() => set({ query: nextQuery.id })}>
                Next query <ArrowRight size={15} aria-hidden />
              </button>
            )}
          </div>
          <div className="notes-block">
            <h2 className="panel-title small">Keyboard</h2>
            <dl className="keys">
              <dt>
                <kbd>J</kbd> <kbd>K</kbd>
              </dt>
              <dd>Next / previous result</dd>
              <dt>
                <kbd>1</kbd>
              </dt>
              <dd>Relevant</dd>
              <dt>
                <kbd>2</kbd>
              </dt>
              <dd>Not relevant</dd>
              <dt>
                <kbd>3</kbd>
              </dt>
              <dd>Unsure</dd>
            </dl>
          </div>
          <div className="notes-block">
            <h2 className="panel-title small">What counts as relevant</h2>
            <p>
              A result is relevant when a football fan typing this query would be glad to open it: it is about the
              query’s subject, not just a page that mentions the words in a menu or a list of links.
            </p>
            <Link to="/metrics" className="btn btn-quiet" style={{ justifySelf: 'start' }}>
              See the metrics <ArrowRight size={15} aria-hidden />
            </Link>
          </div>
        </aside>
      </div>
    </>
  );
}
