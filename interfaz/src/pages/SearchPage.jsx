import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { api } from '../api/client.js';
import { useInfo } from '../App.jsx';
import { ConfigFields, Crawling, ResultRow } from '../components/Results.jsx';
import { fmtDate, fmtInt, fmtMs, shortHost } from '../lib/format.jsx';
import logo from '../assets/logo.png';

const SIZES = [10, 20, 50];

// Orden de los resultados. "recent" mezcla relevancia y frescura: el peso de una página baja a la mitad cada 180 días.
const SORTS = [
  { id: 'relevance', label: 'Relevance', hint: 'Best match first.' },
  { id: 'newest', label: 'Newest', hint: 'Newest pages first; undated ones last.' },
  { id: 'recent', label: 'Fresh', hint: 'Best matches, favouring recent pages.' },
];

const addDays = (iso, n) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

export default function SearchPage() {
  const info = useInfo();
  // El servidor ofrece varios motores o políticas solo en modo --dev: ahí se muestra lo técnico.
  const lab = Boolean(info && (info.engines.length > 1 || info.policies.length > 1));
  const [params, setParams] = useSearchParams();
  const q = params.get('q') || '';
  const engine = params.get('engine') || info?.default.engine;
  const policy = params.get('policy') || info?.default.policy;
  const site = params.get('site') || '';
  const from = params.get('from') || '';
  const to = params.get('to') || '';
  const sort = params.get('sort') || 'relevance';
  const page = Number(params.get('page') || 1);
  const size = Number(params.get('size') || 10);

  const [draft, setDraft] = useState(q);
  const [state, setState] = useState({ status: 'idle' });
  const [queries, setQueries] = useState([]);

  useEffect(() => setDraft(q), [q]);
  useEffect(() => {
    api.queries().then(setQueries, () => setQueries([]));
  }, []);

  useEffect(() => {
    if (!q || !info) {
      setState({ status: 'idle' });
      return;
    }
    let alive = true;
    setState((s) => ({ status: 'loading', data: s.data }));
    api
      .search({ q, engine, policy, site, from, to, sort, page, size })
      .then((data) => alive && setState({ status: 'done', data }))
      .catch((e) => alive && setState({ status: 'error', error: e.message }));
    return () => {
      alive = false;
    };
  }, [q, engine, policy, site, from, to, sort, page, size, info]);

  const update = (patch, resetPage = true) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v === '' || v == null) next.delete(k);
      else next.set(k, String(v));
    }
    if (resetPage && !('page' in patch)) next.delete('page');
    setParams(next);
  };

  const submit = (e) => {
    e.preventDefault();
    const text = draft.trim();
    if (text) update({ q: text });
  };

  const data = state.data;
  const words = useMemo(() => [...(data?.terms || []), ...q.toLowerCase().split(/\W+/)], [data, q]);
  const engineLabel = info?.engines.find((e) => e.id === engine)?.label;
  const pol = info?.policies.find((p) => p.id === policy);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const dates = info?.collection.dates;
  const showNotes = lab || (state.status === 'done' && Boolean(data?.testQueryId));
  const presets = dates
    ? [
        { label: 'Any time', from: '' },
        { label: 'Past year', from: addDays(dates.maxima, -364) },
        { label: '30 days', from: addDays(dates.maxima, -29) },
      ]
    : [];

  return (
    <>
      <section className="masthead">
        <div className="masthead-inner">
          <form className="searchbar" role="search" onSubmit={submit}>
            <span className="searchbar-icon">
              <Search size={18} strokeWidth={2} aria-hidden />
            </span>
            <label htmlFor="q" className="visually-hidden">
              Search the archive
            </label>
            <input
              id="q"
              type="search"
              autoComplete="off"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={
                info ? `Search ${fmtInt(info.collection.documents)} Premier League documents` : 'Search the archive'
              }
              autoFocus
            />
            <button className="btn btn-primary" type="submit">
              Search
            </button>
          </form>
          <p className="edition" aria-live="polite">
            {state.status === 'done' && data && (
              <>
                <span>
                  <strong className="num">{fmtInt(data.total)}</strong> results
                </span>
                <span className="sep">·</span>
                <span className="num">{fmtMs(data.tookMs)}</span>
                {lab && (
                  <>
                    <span className="sep">·</span>
                    <span>
                      {engineLabel}, policy {policy}
                    </span>
                  </>
                )}
                {site && (
                  <>
                    <span className="sep">·</span>
                    <span>only {shortHost(site)}</span>
                  </>
                )}
                {(from || to) && (
                  <>
                    <span className="sep">·</span>
                    <span>
                      published {from ? fmtDate(from) : 'any date'} – {to ? fmtDate(to) : 'latest'}
                    </span>
                  </>
                )}
                {sort !== 'relevance' && (
                  <>
                    <span className="sep">·</span>
                    <span>{SORTS.find((x) => x.id === sort)?.label.toLowerCase()} order</span>
                  </>
                )}
              </>
            )}
            {state.status === 'idle' && lab && (
              <span>
                Searching with {engineLabel}, policy {policy} · {pol?.label}
              </span>
            )}
          </p>
        </div>
      </section>

      <div className={`page${showNotes ? '' : ' page-two'}`}>
        <aside className="rail" aria-label="Filters">
          <h2 className="panel-title small">{lab ? 'Advanced search' : 'Filters'}</h2>
          <ConfigFields info={info} engine={engine} policy={policy} onChange={(p) => update(p)} idPrefix="s" />
          {info && (
            <label className="field">
              <span className="field-label">Site</span>
              <select className="select" value={site} onChange={(e) => update({ site: e.target.value })}>
                <option value="">All {info.collection.hosts.length} sites</option>
                {info.collection.hosts.map((h) => (
                  <option key={h} value={h}>
                    {shortHost(h)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {dates && (
            <>
              <div className="field">
                <span className="field-label" id="date-l">
                  Published
                </span>
                <div className="segmented" role="group" aria-labelledby="date-l">
                  {presets.map((pr) => (
                    <button
                      key={pr.label}
                      type="button"
                      aria-pressed={from === pr.from && to === ''}
                      onClick={() => update({ from: pr.from, to: '' })}
                    >
                      {pr.label}
                    </button>
                  ))}
                </div>
                <div className="date-range">
                  <label>
                    <span className="field-hint">From</span>
                    <input
                      className="input"
                      type="date"
                      min={dates.minima}
                      max={dates.maxima}
                      value={from}
                      onChange={(e) => update({ from: e.target.value })}
                    />
                  </label>
                  <label>
                    <span className="field-hint">To</span>
                    <input
                      className="input"
                      type="date"
                      min={dates.minima}
                      max={dates.maxima}
                      value={to}
                      onChange={(e) => update({ to: e.target.value })}
                    />
                  </label>
                </div>
              </div>
              <div className="field">
                <span className="field-label" id="sort-l">
                  Sort by
                </span>
                <div className="segmented" role="group" aria-labelledby="sort-l">
                  {SORTS.map((o) => (
                    <button key={o.id} type="button" aria-pressed={sort === o.id} onClick={() => update({ sort: o.id === 'relevance' ? '' : o.id })}>
                      {o.label}
                    </button>
                  ))}
                </div>
                <span className="field-hint">{SORTS.find((o) => o.id === sort)?.hint}</span>
              </div>
            </>
          )}
          <div className="field">
            <span className="field-label" id="size-l">
              Results per page
            </span>
            <div className="segmented" role="group" aria-labelledby="size-l">
              {SIZES.map((n) => (
                <button key={n} type="button" aria-pressed={size === n} onClick={() => update({ size: n })}>
                  {n}
                </button>
              ))}
            </div>
          </div>
        </aside>

        <section aria-label="Results" style={{ minWidth: 0 }}>
          {state.status === 'idle' && <Cover info={info} queries={queries} lab={lab} onPick={(text) => update({ q: text })} />}
          {state.status === 'loading' && <Crawling rows={Math.min(size, 6)} />}
          {state.status === 'error' && (
            <div className="message error">
              <h3>The search failed.</h3>
              <p>{state.error}</p>
            </div>
          )}
          {state.status === 'done' && data.results.length === 0 && (
            <div className="message">
              <h3>No documents match “{q}”.</h3>
              <p>
                {from || to
                  ? `No page published in this period contains these terms${data.undatedHidden ? `, and ${fmtInt(data.undatedHidden)} matching pages have no date.` : '.'} Try a wider period or Any time.`
                  : site
                  ? `Nothing from ${shortHost(site)} contains these terms. Try all sites, or a broader query.`
                  : `None of the indexed pages contain these words. Try fewer or different words${lab ? ', or switch to policy C, which adds synonyms and lemmas' : ''}.`}
              </p>
            </div>
          )}
          {state.status === 'done' && data.results.length > 0 && (
            <>
              <div className="sheet-head">
                <h2>“{data.query}”</h2>
                <span className="aside-note num">
                  {fmtInt((data.page - 1) * data.size + 1)}–{fmtInt((data.page - 1) * data.size + data.results.length)}{' '}
                  of {fmtInt(data.total)}
                </span>
              </div>
              {(from || to) && data.undatedHidden > 0 && (
                <p className="field-hint" style={{ margin: '0 0 var(--s3)' }}>
                  {fmtInt(data.undatedHidden)} matching pages have no publication date and are left out while a date filter is on.
                </p>
              )}
              <ol className="sheet">
                {data.results.map((r, i) => (
                  <ResultRow key={r.doc} r={r} words={words} index={i} showScore={lab} />
                ))}
              </ol>
              {pages > 1 && <Pager page={data.page} pages={pages} onPage={(p) => update({ page: p }, false)} />}
            </>
          )}
        </section>

        {showNotes && (
        <aside className="notes" aria-label="About this search">
          {state.status === 'done' && data ? (
            <>
              {lab && (
              <div className="notes-block">
                <h2 className="panel-title small">What was searched</h2>
                <p>Your words after normalization with policy {policy}. These are the terms looked up in the index.</p>
                <div className="chips">
                  {data.terms.length ? (
                    data.terms.map((t) => (
                      <span className="chip" key={t}>
                        {t}
                      </span>
                    ))
                  ) : (
                    <span className="field-hint">No term survived normalization.</span>
                  )}
                </div>
              </div>
              )}
              {data.testQueryId && (
                <div className="notes-block">
                  <p>
                    {lab ? (
                      <>
                        Sample topic <strong>{data.testQueryId}</strong>. Mark which results answer it in Rate results.
                      </>
                    ) : (
                      'Help us improve the search: tell us which of these results are useful.'
                    )}
                  </p>
                  <Link className="btn" to={`/evaluate?query=${data.testQueryId}&engine=${engine}&policy=${policy}`}>
                    {lab ? 'Judge these results' : 'Rate these results'} <ArrowRight size={15} aria-hidden />
                  </Link>
                </div>
              )}
            </>
          ) : null}
          {lab && info && (
            <div className="notes-block">
              <h2 className="panel-title small">The archive</h2>
              <dl className="facts">
                <dt>Documents indexed</dt>
                <dd>{fmtInt(info.collection.documents)}</dd>
                <dt>Pages crawled</dt>
                <dd>{fmtInt(info.collection.crawled)}</dd>
                <dt>Distinct terms ({policy})</dt>
                <dd>{info.collection.termsByPolicy?.[policy] ? fmtInt(info.collection.termsByPolicy[policy]) : '—'}</dd>
                <dt>Sites</dt>
                <dd>{info.collection.hosts.length}</dd>
              </dl>
            </div>
          )}
        </aside>
        )}
      </div>
    </>
  );
}

function Cover({ info, queries, lab, onPick }) {
  return (
    <div className="cover">
      <div className="cover-lede">
        <img className="cover-logo" src={logo} alt="ThePremArchive logo: a spider beside a football" width="230" height="133" />
        <h1>The Premier League, archived.</h1>
        <p>
          Search news, results, transfers and stories from over a million pages about English football.
        </p>
      </div>
      {info && (
        <div className="cover-figures">
          <div>
            <strong className="num">{fmtInt(info.collection.documents)}</strong>
            <span>pages you can search</span>
          </div>
          <div>
            <strong className="num">{info.collection.hosts.length}</strong>
            <span>news and stats sites</span>
          </div>
          {lab && (
            <>
              <div>
                <strong className="num">{info.engines.length}</strong>
                <span>search engines</span>
              </div>
              <div>
                <strong className="num">{info.policies.length}</strong>
                <span>normalization policies</span>
              </div>
            </>
          )}
        </div>
      )}
      {queries.length > 0 && (
        <div>
          <div className="sheet-head">
            <h2>Try a search</h2>
            {lab && <span className="aside-note">Sample searches used to compare both engines</span>}
          </div>
          <ol className="lineup">
            {queries.map((qq, i) => (
              <li key={qq.id}>
                <button type="button" onClick={() => onPick(qq.text)}>
                  <span className="n">{i + 1}</span>
                  <span className="q">{qq.text}</span>
                  <ArrowRight className="go" size={15} aria-hidden />
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function Pager({ page, pages, onPage }) {
  const around = [...new Set([1, page - 1, page, page + 1, pages])].filter((p) => p >= 1 && p <= pages);
  return (
    <nav className="pager" aria-label="Pages">
      <button className="btn btn-quiet" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        <ChevronLeft size={16} aria-hidden /> Previous
      </button>
      <div className="pager-pages">
        {around.map((p, i) => (
          <span key={p} style={{ display: 'contents' }}>
            {i > 0 && p - around[i - 1] > 1 && <span aria-hidden>…</span>}
            <button aria-current={p === page ? 'page' : undefined} onClick={() => onPage(p)}>
              {p}
            </button>
          </span>
        ))}
      </div>
      <button className="btn btn-quiet" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next <ChevronRight size={16} aria-hidden />
      </button>
    </nav>
  );
}
