import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { api } from '../api/client.js';
import { useInfo } from '../App.jsx';
import { ConfigFields, Crawling, ResultRow } from '../components/Results.jsx';
import { fmtInt, fmtMs, shortHost } from '../lib/format.jsx';
import logo from '../assets/logo.png';

const SIZES = [10, 20, 50];

export default function SearchPage() {
  const info = useInfo();
  const [params, setParams] = useSearchParams();
  const q = params.get('q') || '';
  const engine = params.get('engine') || info?.default.engine;
  const policy = params.get('policy') || info?.default.policy;
  const site = params.get('site') || '';
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
      .search({ q, engine, policy, site, page, size })
      .then((data) => alive && setState({ status: 'done', data }))
      .catch((e) => alive && setState({ status: 'error', error: e.message }));
    return () => {
      alive = false;
    };
  }, [q, engine, policy, site, page, size, info]);

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

  return (
    <>
      <section className="masthead">
        <div className="masthead-inner">
          <h1 className="masthead-title">
            Search
            <small>Vector-space model · tf-idf</small>
          </h1>
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
                <span className="sep">·</span>
                <span>
                  {engineLabel}, policy {policy}
                </span>
                {site && (
                  <>
                    <span className="sep">·</span>
                    <span>only {shortHost(site)}</span>
                  </>
                )}
              </>
            )}
            {state.status === 'idle' && info && (
              <span>
                Searching with {engineLabel}, policy {policy} · {pol?.label}
              </span>
            )}
          </p>
        </div>
      </section>

      <div className="page">
        <aside className="rail" aria-label="Advanced search">
          <h2 className="panel-title small">Advanced search</h2>
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
          {state.status === 'idle' && <Cover info={info} queries={queries} onPick={(text) => update({ q: text })} />}
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
                {site
                  ? `Nothing from ${shortHost(site)} contains these terms. Try all sites, or a broader query.`
                  : 'None of the indexed documents contain these terms after normalization. Try fewer words, or switch to policy C, which adds synonyms and lemmas.'}
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
              <ol className="sheet">
                {data.results.map((r, i) => (
                  <ResultRow key={r.doc} r={r} words={words} index={i} />
                ))}
              </ol>
              {pages > 1 && <Pager page={data.page} pages={pages} onPage={(p) => update({ page: p }, false)} />}
            </>
          )}
        </section>

        <aside className="notes" aria-label="About this search">
          {state.status === 'done' && data ? (
            <>
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
              {data.testQueryId && (
                <div className="notes-block">
                  <p>
                    This is test query <strong>{data.testQueryId}</strong>. Mark which results answer it in Evaluate.
                  </p>
                  <Link className="btn" to={`/evaluate?query=${data.testQueryId}&engine=${engine}&policy=${policy}`}>
                    Judge these results <ArrowRight size={15} aria-hidden />
                  </Link>
                </div>
              )}
            </>
          ) : null}
          {info && (
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
      </div>
    </>
  );
}

function Cover({ info, queries, onPick }) {
  return (
    <div className="cover">
      <div className="cover-lede">
        <img className="cover-logo" src={logo} alt="ThePremArchive logo: a spider beside a football" width="230" height="133" />
        <h1>The Premier League, archived.</h1>
        <p>
          Every result here comes from pages our own crawler collected from English football's newspapers, clubs and
          statistics sites, cleaned and indexed twice: once in a binary index we built by hand, once in Apache Lucene.
        </p>
      </div>
      {info && (
        <div className="cover-figures">
          <div>
            <strong className="num">{fmtInt(info.collection.documents)}</strong>
            <span>documents indexed</span>
          </div>
          <div>
            <strong className="num">{fmtInt(info.collection.crawled)}</strong>
            <span>pages crawled</span>
          </div>
          <div>
            <strong className="num">{info.engines.length}</strong>
            <span>search engines</span>
          </div>
          <div>
            <strong className="num">{info.policies.length}</strong>
            <span>normalization policies</span>
          </div>
        </div>
      )}
      {queries.length > 0 && (
        <div>
          <div className="sheet-head">
            <h2>Today’s line-up</h2>
            <span className="aside-note">The test queries used to evaluate both engines</span>
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
