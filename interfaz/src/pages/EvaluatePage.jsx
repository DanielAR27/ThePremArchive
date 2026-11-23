import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, Check, CircleHelp, Search, Trash2, X } from 'lucide-react';
import { api } from '../api/client.js';
import { useInfo } from '../App.jsx';
import { ConfigFields, Crawling, ResultRow } from '../components/Results.jsx';

const VERDICTS = [
  { v: 'relevant', label: 'Relevant', key: '1', Icon: Check },
  { v: 'not_relevant', label: 'Not relevant', key: '2', Icon: X },
  { v: 'unsure', label: 'Unsure', key: '3', Icon: CircleHelp },
];
const EVALUATOR_KEY = 'tpa.evaluator';

const norm = (s) => (s || '').toLowerCase().replace(/\s+/g, ' ').trim();
/** Key that identifies a query: the test-query id, or the normalized text for a search of the person's own. */
const queryKey = (id, text) => id || `free:${norm(text)}`;

function readEvaluator() {
  try {
    return localStorage.getItem(EVALUATOR_KEY) || '';
  } catch {
    return '';
  }
}

/** Index of the next result that has no verdict yet, looking forward first and then wrapping around. */
function nextUnjudged(rows, from, judged) {
  for (let step = 1; step <= rows.length; step += 1) {
    const i = (from + step) % rows.length;
    if (!judged.has(rows[i].doc)) return i;
  }
  return from;
}

export default function EvaluatePage() {
  const info = useInfo();
  const [params, setParams] = useSearchParams();
  const [queries, setQueries] = useState([]);
  const [evaluator, setEvaluator] = useState(readEvaluator);
  const [draftName, setDraftName] = useState('');
  const [draftQuery, setDraftQuery] = useState('');
  const [mine, setMine] = useState([]); // this evaluator's judgments, all queries
  const [results, setResults] = useState({ status: 'idle' });
  const [active, setActive] = useState(0);
  const [saved, setSaved] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const listRef = useRef(null);

  const ownText = (params.get('q') || '').trim();
  const queryId = params.get('query') || queries[0]?.id;
  const engine = params.get('engine') || info?.default.engine;
  const policy = params.get('policy') || info?.default.policy;
  const query = ownText ? { id: null, text: ownText } : queries.find((q) => q.id === queryId);
  const qKey = query ? queryKey(query.id, query.text) : null;

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
    if (!query?.text || !info) return;
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query?.id, query?.text, engine, policy, info]);

  const verdictOf = useMemo(() => {
    const m = new Map();
    for (const j of mine) m.set(`${queryKey(j.queryId, j.query)}|${j.doc}`, j.judgment);
    return m;
  }, [mine]);

  const rows = results.status === 'done' ? results.data.results : [];
  const judgedDocs = new Set(rows.filter((r) => verdictOf.has(`${qKey}|${r.doc}`)).map((r) => r.doc));
  // The key handler and the click handler read the latest values from here, so they never act on stale rows.
  const latest = useRef({});
  latest.current = { rows, judgedDocs, active };

  const judge = useCallback(
    async (r, index, judgment) => {
      const name = evaluator.trim();
      if (!name || !query) return;
      setSaveError(null);
      try {
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
        setMine((list) => [
          ...list.filter((j) => !(queryKey(j.queryId, j.query) === queryKey(entry.queryId, entry.query) && j.doc === entry.doc)),
          entry,
        ]);
        setSaved(new Date(entry.judgedAt));
      } catch (e) {
        setSaveError(e.message || 'The judgment could not be saved.');
        return;
      }
      // Move on to the next result that still has no verdict.
      const { rows: current, judgedDocs: done } = latest.current;
      setActive(nextUnjudged(current, index, new Set([...done, r.doc])));
    },
    [evaluator, query, engine, policy],
  );

  const counts = { relevant: 0, not_relevant: 0, unsure: 0 };
  for (const r of rows) {
    const v = verdictOf.get(`${qKey}|${r.doc}`);
    if (v) counts[v] += 1;
  }
  const judgedHere = counts.relevant + counts.not_relevant + counts.unsure;
  const allJudged = rows.length > 0 && judgedHere === rows.length;

  const perQuery = useMemo(() => {
    const m = new Map();
    for (const j of mine) {
      const k = queryKey(j.queryId, j.query);
      m.set(k, (m.get(k) || 0) + 1);
    }
    return m;
  }, [mine]);
  const ownSearches = useMemo(() => {
    const m = new Map();
    for (const j of mine) if (!j.queryId) m.set(norm(j.query), j.query);
    return [...m.values()];
  }, [mine]);

  // Keyboard: J/K or arrows move between results, 1/2/3 judge the highlighted one, O opens its page.
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.closest('input, select, textarea') || e.metaKey || e.ctrlKey || e.altKey) return;
      const { rows: current, active: a } = latest.current;
      if (!current.length) return;
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        setActive((a) => Math.min(current.length - 1, a + 1));
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        setActive((a) => Math.max(0, a - 1));
      } else if (e.key === 'o') {
        e.preventDefault();
        window.open(current[a]?.url, '_blank', 'noopener');
      } else {
        const verdict = VERDICTS.find((x) => x.key === e.key);
        if (verdict && evaluator.trim()) {
          e.preventDefault();
          judge(current[a], a, verdict.v);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [judge, evaluator]);

  useEffect(() => {
    listRef.current?.children[active]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [active]);

  const go = (patch) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v === '' || v == null) next.delete(k);
      else next.set(k, v);
    }
    setParams(next);
  };
  const pickTest = (id) => go({ query: id, q: '' });
  const submitOwn = (e) => {
    e.preventDefault();
    const text = draftQuery.trim();
    if (!text) return;
    document.activeElement?.blur();   // el foco sale del cuadro para que las teclas 1 / 2 / 3 / J / K funcionen enseguida
    go({ q: text, query: '' });
  };
  const startJudging = (e) => {
    e.preventDefault();
    if (draftName.trim()) setEvaluator(draftName.trim());
  };
  const continueAsGuest = () => {
    setEvaluator(`Guest ${Math.floor(100 + Math.random() * 900)}`);
  };
  const clearMine = async () => {
    await api.deleteJudgments({ evaluator: evaluator.trim() });
    setMine([]);
    setSaved(null);
    setConfirmClear(false);
  };
  const currentTopicIndex = queries.findIndex((q) => q.id === queryId);
  const nextQuery = useMemo(() => {
    if (!queries.length) return null;
    const start = currentTopicIndex >= 0 ? currentTopicIndex : 0;
    for (let step = 1; step <= queries.length; step += 1) {
      const candidate = queries[(start + step) % queries.length];
      if ((perQuery.get(candidate.id) || 0) < 10) return candidate;
    }
    return null;
  }, [queries, currentTopicIndex, perQuery]);
  const completedTopics = useMemo(
    () => queries.filter((q) => (perQuery.get(q.id) || 0) >= 10).length,
    [queries, perQuery],
  );
  const noName = !evaluator.trim();

  return (
    <>
      <section className="masthead">
        <div className="masthead-inner">
          <form className="searchbar" role="search" onSubmit={submitOwn}>
            <span className="searchbar-icon">
              <Search size={18} strokeWidth={2} aria-hidden />
            </span>
            <label htmlFor="own-query" className="visually-hidden">
              Search any topic to rate
            </label>
            <input
              id="own-query"
              type="search"
              autoComplete="off"
              value={draftQuery}
              onChange={(e) => setDraftQuery(e.target.value)}
              placeholder="Search any Premier League topic to rate..."
            />
            <button className="btn btn-primary" type="submit">
              Load results
            </button>
          </form>
          <p className="edition" style={{ fontSize: 'var(--step-0)' }}>
            Tell us whether each result answers the search — your picks save automatically.
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
              placeholder="e.g. Alex"
              autoComplete="name"
            />
            <span className="field-hint">Your ratings are saved under this name.</span>
          </label>
          {mine.length > 0 &&
            (confirmClear ? (
              <div className="field">
                <span className="field-hint">
                  Delete all {mine.length} ratings saved as “{evaluator.trim()}”? This cannot be undone.
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
                <Trash2 size={14} aria-hidden /> Clear my {mine.length} ratings
              </button>
            ))}
          <ConfigFields info={info} engine={engine} policy={policy} onChange={go} idPrefix="e" />
          <div className="notes-block">
            <div className="rail-head">
              <h2 className="panel-title small">Suggested topics</h2>
              {queries.length > 0 && (
                <span className="field-hint num">
                  {completedTopics}/{queries.length} done
                </span>
              )}
            </div>
            <ul className="query-list">
              {queries.map((q, i) => {
                const n = perQuery.get(q.id) || 0;
                const done = n >= 10;
                return (
                  <li key={q.id}>
                    <button
                      type="button"
                      aria-current={!ownText && q.id === queryId}
                      onClick={() => pickTest(q.id)}
                      title={q.text}
                    >
                      <span className="qid">{i + 1}</span>
                      <span className="qtext">{q.text}</span>
                      <span className={`qcount ${done ? 'done' : ''}`}>
                        {done ? <Check size={14} strokeWidth={2.5} aria-label="Completed" /> : n ? `${n}/10` : '—'}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
          {ownSearches.length > 0 && (
            <div className="notes-block">
              <h2 className="panel-title small">Your searches</h2>
              <ul className="query-list">
                {ownSearches.map((text) => {
                  const n = perQuery.get(queryKey(null, text)) || 0;
                  const done = n >= 10;
                  return (
                    <li key={text}>
                      <button
                        type="button"
                        aria-current={norm(text) === norm(ownText)}
                        onClick={() => go({ q: text, query: '' })}
                        title={text}
                      >
                        <span className="qid">
                          <Search size={14} aria-hidden />
                        </span>
                        <span className="qtext">{text}</span>
                        <span className={`qcount ${done ? 'done' : ''}`}>
                          {done ? <Check size={14} strokeWidth={2.5} aria-label="Completed" /> : n ? `${n}/10` : '—'}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </aside>

        <section aria-label="Results to rate" style={{ minWidth: 0 }}>
          {noName && (
            <form className="name-card" onSubmit={startJudging}>
              <h3>Before you start</h3>
              <p>Enter a name or nickname so your ratings stay separate from everyone else’s, or jump straight in as a guest.</p>
              <div className="name-card-row">
                <input
                  className="input"
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  placeholder="Your name or nickname"
                  autoComplete="name"
                  autoFocus
                  aria-label="Your name"
                />
                <button className="btn btn-primary" type="submit" disabled={!draftName.trim()}>
                  Start rating
                </button>
                <button className="btn" type="button" onClick={continueAsGuest}>
                  Continue as guest
                </button>
              </div>
            </form>
          )}
          {query && (
            <div className="sheet-head">
              <h2>
                “{query.text}”
                <span className="tag">
                  {query.id && currentTopicIndex >= 0
                    ? `Topic ${currentTopicIndex + 1} of ${queries.length}`
                    : 'Your search'}
                </span>
              </h2>
              <span className="aside-note num">
                {judgedHere} of {rows.length || 10} rated
              </span>
            </div>
          )}
          {results.status === 'loading' && <Crawling label="Fetching the top ten…" rows={4} />}
          {results.status === 'error' && (
            <div className="message error">
              <h3>The results could not be loaded.</h3>
              <p>{results.error}</p>
            </div>
          )}
          {results.status === 'done' && rows.length === 0 && (
            <div className="message">
              <h3>Nothing to rate.</h3>
              <p>No page contains these words. Try a different search.</p>
            </div>
          )}
          {results.status === 'done' && rows.length > 0 && (
            <ol className="sheet" ref={listRef}>
              {rows.map((r, i) => {
                const v = verdictOf.get(`${qKey}|${r.doc}`);
                return (
                  <ResultRow
                    key={r.doc}
                    r={r}
                    words={results.data.terms}
                    index={i}
                    showScore={false}
                    className={`judging${i === active ? ' is-active' : ''}${v ? ` v-${v}` : ''}`}
                    tabIndex={-1}
                    onClick={() => setActive(i)}
                    onFocus={() => setActive(i)}
                    children={{
                      meta: v && <span className={`stamp ${v}`}>{VERDICTS.find((x) => x.v === v).label}</span>,
                      side: (
                        <div className="judge" role="group" aria-label={`Rate result ${r.rank}`}>
                          {VERDICTS.map(({ v: value, label, key, Icon }) => (
                            <button
                              key={value}
                              type="button"
                              data-v={value}
                              aria-pressed={v === value}
                              disabled={noName}
                              onClick={() => judge(r, i, value)}
                              title={noName ? 'Enter a name or continue as guest first' : `${label} (${key})`}
                            >
                              <Icon size={15} strokeWidth={2.4} aria-hidden />
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
          {allJudged && (
            <div className="done-card">
              <div>
                <strong>
                  {query?.id && !nextQuery
                    ? 'All suggested topics completed — thank you!'
                    : `All ${rows.length} results rated. Thank you!`}
                </strong>
                <span>
                  {counts.relevant} relevant · {counts.not_relevant} not relevant · {counts.unsure} unsure
                </span>
              </div>
              <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap' }}>
                {query?.id && nextQuery ? (
                  <button className="btn btn-primary" type="button" onClick={() => pickTest(nextQuery.id)}>
                    Next unrated topic <ArrowRight size={15} aria-hidden />
                  </button>
                ) : query?.id ? (
                  <Link className="btn btn-primary" to="/metrics">
                    See the metrics <ArrowRight size={15} aria-hidden />
                  </Link>
                ) : (
                  <button className="btn btn-primary" type="button" onClick={() => document.getElementById('own-query')?.focus()}>
                    Rate another search
                  </button>
                )}
              </div>
            </div>
          )}
        </section>

        <aside className="notes" aria-label="Progress">
          <div className="notes-block">
            <h2 className="panel-title small">This search</h2>
            <div className="tally">
              <div className="t-yes">
                <strong className="num">{counts.relevant}</strong>
                <span>Relevant</span>
              </div>
              <div className="t-no">
                <strong className="num">{counts.not_relevant}</strong>
                <span>Not relevant</span>
              </div>
              <div className="t-unsure">
                <strong className="num">{counts.unsure}</strong>
                <span>Unsure</span>
              </div>
            </div>
            <div
              className="progress-split"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={rows.length || 10}
              aria-valuenow={judgedHere}
            >
              <i className="p-yes" style={{ width: `${(counts.relevant / (rows.length || 10)) * 100}%` }} />
              <i className="p-no" style={{ width: `${(counts.not_relevant / (rows.length || 10)) * 100}%` }} />
              <i className="p-unsure" style={{ width: `${(counts.unsure / (rows.length || 10)) * 100}%` }} />
            </div>
            <p className={`saved${saveError ? ' error' : ''}`} aria-live="polite">
              {saveError ? (
                saveError
              ) : (
                saved && (
                  <>
                    <Check size={14} aria-hidden /> Saved at{' '}
                    {saved.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    {api.isMock && ' in this browser'}
                  </>
                )
              )}
            </p>
          </div>
          <div className="notes-block">
            <h2 className="panel-title small">What counts as relevant</h2>
            <p>
              A result is relevant when a football fan typing this search would be glad to open it: it answers the topic
              directly, not just a menu or link directory mentioning the words.
            </p>
            <Link to="/metrics" className="btn btn-quiet" style={{ justifySelf: 'start' }}>
              See the metrics <ArrowRight size={15} aria-hidden />
            </Link>
          </div>
          <details className="notes-details">
            <summary className="panel-title small">Keyboard shortcuts</summary>
            <dl className="keys">
              <dt>
                <kbd>J</kbd> <kbd>K</kbd>
              </dt>
              <dd>Next / previous result (or ↓ ↑)</dd>
              <dt>
                <kbd className="k-yes">1</kbd>
              </dt>
              <dd>Relevant</dd>
              <dt>
                <kbd className="k-no">2</kbd>
              </dt>
              <dd>Not relevant</dd>
              <dt>
                <kbd className="k-unsure">3</kbd>
              </dt>
              <dd>Unsure</dd>
              <dt>
                <kbd>O</kbd>
              </dt>
              <dd>Open the original page</dd>
            </dl>
            <p className="field-hint">Rating a result automatically moves to the next unrated one.</p>
          </details>
        </aside>
      </div>
    </>
  );
}
