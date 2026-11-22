// Single entry point for data. `VITE_API=real` talks to the search server (API.md);
// anything else uses the mock adapter built from project 2's results.
import * as mock from './mock.js';

async function request(path, options) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `The search server answered ${res.status}.`);
  return body;
}
const qs = (params) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString();

const real = {
  isMock: false,
  info: () => request('/info'),
  queries: () => request('/queries'),
  search: (p) => request(`/search?${qs(p)}`),
  judgments: (p = {}) => request(`/judgments?${qs(p)}`),
  saveJudgment: (j) => request('/judgments', { method: 'POST', body: JSON.stringify(j) }),
  deleteJudgments: (p) => request(`/judgments?${qs(p)}`, { method: 'DELETE' }),
  metrics: (p) => request(`/metrics?${qs(p)}`),
};

export const api = import.meta.env.VITE_API === 'real' ? real : mock;
