import { useState } from 'react';
import { fmt2 } from '../lib/format.jsx';

// Two series, validated together on the cream surface (dataviz validate_palette: all checks pass).
export const SERIES = {
  manual: { label: 'Own index', color: 'var(--olive-500)' },
  lucene: { label: 'Apache Lucene', color: 'var(--burgundy-500)' },
};

export function Legend({ keys }) {
  return (
    <div className="legend">
      {keys.map((k) => (
        <span key={k}>
          <i style={{ background: SERIES[k].color }} />
          {SERIES[k].label}
        </span>
      ))}
    </div>
  );
}

function Tooltip({ tip }) {
  if (!tip) return null;
  return (
    <div className="tooltip" style={{ left: tip.x, top: tip.y }} role="status">
      <strong>{tip.title}</strong>
      {tip.rows.map((r) => (
        <div className="tt-row" key={r.label}>
          <span>
            <i style={{ background: r.color }} />
            {r.label}
          </span>
          <b>{fmt2(r.value)}</b>
        </div>
      ))}
    </div>
  );
}

const TICKS = [0, 0.25, 0.5, 0.75, 1];
const roundTop = (x, y, w, h, r) =>
  h <= 0 ? '' : `M${x},${y + h} V${y + Math.min(r, h)} Q${x},${y} ${x + Math.min(r, w / 2)},${y} H${x + w - Math.min(r, w / 2)} Q${x + w},${y} ${x + w},${y + Math.min(r, h)} V${y + h} Z`;
const roundRight = (x, y, w, h, r) =>
  w <= 0 ? '' : `M${x},${y} H${x + w - Math.min(r, w)} Q${x + w},${y} ${x + w},${y + Math.min(r, h / 2)} V${y + h - Math.min(r, h / 2)} Q${x + w},${y + h} ${x + w - Math.min(r, w)},${y + h} H${x} Z`;

/** Horizontal grouped bars, 0–1 scale. rows: [{ label, sub, values: { manual, lucene } }] */
export function HBarChart({ rows, keys, label }) {
  const [tip, setTip] = useState(null);
  const W = 640;
  const left = 236;
  const right = 16;
  const bar = 9;
  const gap = 2;
  const group = keys.length * bar + (keys.length - 1) * gap;
  const pitch = group + 14;
  const top = 8;
  const H = top + rows.length * pitch + 24;
  const x = (v) => left + v * (W - left - right);

  return (
    <div className="chart chart-scroll" style={{ position: 'relative' }} onMouseLeave={() => setTip(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        {TICKS.map((t) => (
          <g key={t}>
            <line className={t === 0 ? 'baseline' : 'grid-line'} x1={x(t)} x2={x(t)} y1={top - 4} y2={H - 20} />
            <text className="axis-label" x={x(t)} y={H - 6} textAnchor="middle">
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        {rows.map((row, i) => {
          const y0 = top + i * pitch;
          return (
            <g key={row.label}>
              <text x={left - 10} y={y0 + group / 2 + 4} textAnchor="end" fontSize="12.5">
                <tspan style={{ fontFamily: 'var(--font-display)', fill: 'var(--burgundy-700)' }} fontSize="13">
                  {row.sub}
                </tspan>
                <tspan dx="6">{row.label.length > 30 ? `${row.label.slice(0, 29)}…` : row.label}</tspan>
              </text>
              {keys.map((k, j) => (
                <path
                  key={k}
                  d={roundRight(x(0), y0 + j * (bar + gap), x(row.values[k] ?? 0) - x(0), bar, 4)}
                  style={{ fill: SERIES[k].color }}
                />
              ))}
              <rect
                className="hit"
                x={0}
                y={y0 - 5}
                width={W}
                height={pitch}
                onMouseMove={(e) => {
                  const box = e.currentTarget.ownerSVGElement.getBoundingClientRect();
                  setTip({
                    x: e.clientX - box.left,
                    y: ((y0 - 4) / H) * box.height,
                    title: row.label,
                    rows: keys.map((k) => ({ label: SERIES[k].label, color: SERIES[k].color, value: row.values[k] })),
                  });
                }}
              />
            </g>
          );
        })}
      </svg>
      <Tooltip tip={tip} />
    </div>
  );
}

/** Vertical grouped bars, 0–1 scale. groups: [{ label, title, values: { manual, lucene } }] */
export function VBarChart({ groups, keys, label, highlight }) {
  const [tip, setTip] = useState(null);
  const W = 460;
  const H = 280;
  const left = 34;
  const bottom = 40;
  const top = 10;
  const plotW = W - left - 8;
  const slot = plotW / groups.length;
  const bar = Math.min(22, (slot - 18) / keys.length);
  const y = (v) => top + (1 - v) * (H - top - bottom);

  return (
    <div className="chart" style={{ position: 'relative' }} onMouseLeave={() => setTip(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        {TICKS.map((t) => (
          <g key={t}>
            <line className={t === 0 ? 'baseline' : 'grid-line'} x1={left} x2={W - 8} y1={y(t)} y2={y(t)} />
            <text className="axis-label" x={left - 6} y={y(t) + 4} textAnchor="end">
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        {groups.map((g, i) => {
          const cx = left + slot * i + slot / 2;
          const x0 = cx - (keys.length * bar + (keys.length - 1) * 2) / 2;
          return (
            <g key={g.label}>
              {keys.map((k, j) => {
                const v = g.values[k] ?? 0;
                return (
                  <path key={k} d={roundTop(x0 + j * (bar + 2), y(v), bar, y(0) - y(v), 4)} style={{ fill: SERIES[k].color }} />
                );
              })}
              <text
                x={cx}
                y={H - bottom + 18}
                textAnchor="middle"
                fontSize="17"
                style={{
                  fontFamily: 'var(--font-display)',
                  fill: g.label === highlight ? 'var(--burgundy-700)' : 'var(--ink-2)',
                }}
              >
                {g.label}
              </text>
              <text x={cx} y={H - bottom + 33} textAnchor="middle" className="axis-label" fontSize="10">
                {g.short}
              </text>
              <rect
                className="hit"
                x={cx - slot / 2}
                y={top}
                width={slot}
                height={H - top - bottom}
                onMouseMove={(e) => {
                  const box = e.currentTarget.ownerSVGElement.getBoundingClientRect();
                  const best = Math.max(...keys.map((k) => g.values[k] ?? 0));
                  setTip({
                    x: (cx / W) * box.width,
                    y: (y(best) / H) * box.height,
                    title: g.title,
                    rows: keys.map((k) => ({ label: SERIES[k].label, color: SERIES[k].color, value: g.values[k] })),
                  });
                }}
              />
            </g>
          );
        })}
      </svg>
      <Tooltip tip={tip} />
    </div>
  );
}
