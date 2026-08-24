/**
 * Centralized API service.
 * Uses /api prefix (proxied by Vite to http://127.0.0.1:8000 in dev).
 * Attaches JWT Bearer token automatically from localStorage.
 */

const PROD_BACKEND = 'https://healthqueue-production.up.railway.app';

function getBaseUrl() {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  const storedUrl = typeof window !== 'undefined' ? localStorage.getItem('hq_api_url') : null;
  const isLocal = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
  let raw = storedUrl || envUrl || (isLocal ? '' : PROD_BACKEND);
  if (raw) {
    raw = raw.trim();
    if (!raw.startsWith('http://') && !raw.startsWith('https://') && !raw.startsWith('/')) {
      raw = `https://${raw}`;
    }
    const clean = raw.replace(/\/+$/, '');
    return clean.endsWith('/api/v1') ? clean : `${clean}/api/v1`;
  }
  return '/api/v1';
}

function getToken() {
  return localStorage.getItem('hq_token') || '';
}

async function request(method, path, body = null, auth = true) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth) {
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  const config = { method, headers };
  if (body !== null) config.body = JSON.stringify(body);

  const baseUrl = getBaseUrl();
  const res = await fetch(`${baseUrl}${path}`, config);

  if (res.status === 204) return null;

  const data = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) {
    const msg = data?.detail || JSON.stringify(data);
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export const api = {
  auth: {
    login: (email, password) =>
      request('POST', '/auth/login', { email, password }, false),
    register: (payload) =>
      request('POST', '/auth/register', payload, false),
  },

  // ── Doctors ────────────────────────────────────────────────────────────────
  doctors: {
    list: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request('GET', `/doctors${q ? '?' + q : ''}`);
    },
    get: (id) => request('GET', `/doctors/${id}`),
    create: (payload) => request('POST', '/doctors/', payload),
    setAvailability: (id, payload) => request('POST', `/doctors/${id}/availability`, payload),
    addLeave: (id, payload) => request('POST', `/doctors/${id}/leave`, payload),
    // AI-powered doctor suggestion based on symptoms or diagnosis text
    suggestBySymptoms: (symptoms) => {
      const q = new URLSearchParams({ symptoms }).toString();
      return request('GET', `/doctors/suggest?${q}`);
    },
    search: (query) => {
      const q = new URLSearchParams({ specialisation: query }).toString();
      return request('GET', `/doctors?${q}`);
    },
  },

  // ── Queue ──────────────────────────────────────────────────────────────────
  queue: {
    book: (payload) => request('POST', '/queue/book', payload),
    status: (queueId) => request('GET', `/queue/${queueId}/status`),
    list: (doctorId, date) => request('GET', `/queue/doctor/${doctorId}?appointment_date=${date}`),
    callNext: (doctorId, session) =>
      request('POST', `/queue/doctor/${doctorId}/call-next`, { session }),
    complete: (queueId) => request('POST', `/queue/${queueId}/complete`),
    escalate: (queueId, tier) => request('POST', `/queue/${queueId}/escalate`, { tier }),
  },

  // ── Clinical ───────────────────────────────────────────────────────────────
  clinical: {
    submitSymptoms: (queueId, symptomText) =>
      request('POST', `/clinical/${queueId}/symptoms`, { symptom_text: symptomText }),
    getSymptoms: (queueId) => request('GET', `/clinical/${queueId}/symptoms`),
    submitNotes: (queueId, payload) =>
      request('POST', `/clinical/${queueId}/post-visit-notes`, payload),
    getNotes: (queueId) => request('GET', `/clinical/${queueId}/post-visit-notes`),
  },

  // ── Admin ──────────────────────────────────────────────────────────────────
  admin: {
    dashboard: () => request('GET', '/admin/dashboard'),
    delays: () => request('GET', '/admin/delays'),
  },

  // ── Health check ───────────────────────────────────────────────────────────
  health: () => fetch('/health').then((r) => r.json()),
};
