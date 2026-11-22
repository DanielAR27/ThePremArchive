const int = new Intl.NumberFormat('en-GB');
export const fmtInt = (n) => int.format(n);
export const fmt2 = (n) => (n == null ? '—' : n.toFixed(2));
export const fmtMs = (ms) => (ms < 10 ? `${ms.toFixed(1)} ms` : `${Math.round(ms)} ms`);
export const shortHost = (h) => h.replace(/^www\./, '');

/** Parses ISO dates; a bare YYYY-MM-DD is read as a local calendar day, not UTC midnight. */
export const parseDate = (iso) => new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T12:00:00` : iso);

export function fmtDate(iso) {
  if (!iso) return null;
  const d = parseDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** Splits text into plain and highlighted parts for the query words (prefix match). */
export function highlight(text, words) {
  const ws = [...new Set(words.filter((w) => w.length > 1))].sort((a, b) => b.length - a.length);
  if (!ws.length) return [text];
  const esc = ws.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const re = new RegExp(`\\b(${esc.join('|')})[a-z]*`, 'gi');
  const out = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(<mark key={m.index}>{m[0]}</mark>);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
