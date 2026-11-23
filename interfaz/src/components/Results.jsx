import { ExternalLink } from 'lucide-react';
import logoMark from '../assets/logo-mark-cream.png';
import { fmtDate, highlight, shortHost } from '../lib/format.jsx';

/** One line of the team sheet: shirt number, title to the original page, provenance, snippet. */
export function ResultRow({ r, words, index = 0, showScore = true, children, className = '', ...rest }) {
  const date = fmtDate(r.publishedAt);
  return (
    <li className={`row ${className}`} style={{ '--i': index }} {...rest}>
      <span className="row-num" aria-label={`Result ${r.rank}`}>
        {r.rank}
      </span>
      <div className="row-body">
        <a className="row-title" href={r.url} target="_blank" rel="noopener noreferrer">
          {highlight(r.title || r.url, words)}
          <ExternalLink size={13} strokeWidth={2} aria-label="(opens the original page)" />
        </a>
        <div className="row-meta">
          <span className="row-host">{shortHost(r.host)}</span>
          {date && <span>{date}</span>}
          {showScore && (
            <span className="num" title="Cosine similarity (tf-idf)">
              score {r.score.toFixed(4)}
            </span>
          )}
          {children?.meta}
        </div>
        {r.snippet && <p className="row-snippet">{highlight(r.snippet, words)}</p>}
        {children?.side}
      </div>
    </li>
  );
}

/** The spider lowering itself on its thread, plus skeleton rows shaped like results. */
export function Crawling({ label = 'Crawling the archive…', rows = 5 }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <div className="crawler">
        <span className="crawler-mark" style={{ WebkitMaskImage: `url(${logoMark})`, maskImage: `url(${logoMark})` }} />
        <span>{label}</span>
      </div>
      <ul className="sheet">
        {Array.from({ length: rows }, (_, i) => (
          <li key={i} className="row row-skeleton" style={{ '--i': i }}>
            <span className="row-num" style={{ color: 'var(--cream-300)' }}>
              {i + 1}
            </span>
            <div className="row-body">
              <div className="bar" style={{ width: `${62 - (i % 3) * 9}%`, height: 16 }} />
              <div className="bar" style={{ width: '22%' }} />
              <div className="bar" style={{ width: '92%' }} />
              <div className="bar" style={{ width: '74%' }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Engine and policy selectors shared by Search, Evaluate and Metrics. */
export function ConfigFields({ info, engine, policy, onChange, idPrefix = 'cfg' }) {
  if (!info) return null;
  const pol = info.policies.find((p) => p.id === policy);
  return (
    <>
      {info.engines.length > 1 && (
        <div className="field">
          <span className="field-label" id={`${idPrefix}-engine`}>
            Engine
          </span>
          <div className="segmented" role="group" aria-labelledby={`${idPrefix}-engine`}>
            {info.engines.map((e) => (
              <button
                key={e.id}
                type="button"
                aria-pressed={engine === e.id}
                onClick={() => onChange({ engine: e.id })}
              >
                {e.label}
              </button>
            ))}
          </div>
        </div>
      )}
      {info.policies.length > 1 && (
        <label className="field">
          <span className="field-label">Normalization policy</span>
          <select className="select" value={policy} onChange={(e) => onChange({ policy: e.target.value })}>
            {info.policies.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id} · {p.label}
              </option>
            ))}
          </select>
          {pol && <span className="field-hint">{pol.description}</span>}
        </label>
      )}
    </>
  );
}
