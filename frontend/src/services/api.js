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

function cleanId(id) {
  if (id && typeof id === 'object') return id.id || id.queue_id;
  if (!id || id === 'undefined' || id === 'null') {
    throw new Error('A valid appointment/queue ID is required.');
  }
  return id;
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
    get: (id) => request('GET', `/doctors/${cleanId(id)}`),
    create: (payload) => request('POST', '/doctors', payload),
    setAvailability: (id, payload) => request('POST', `/doctors/${cleanId(id)}/availability`, payload),
    addLeave: (id, payload) => request('POST', `/doctors/${cleanId(id)}/leave`, payload),
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
    book: async (payload) => {
      const data = await request('POST', '/queue/book', payload);
      if (data && data.queue_id != null) {
        data.id = data.queue_id;
      }
      return data;
    },
    status: (queueId) => request('GET', `/queue/${cleanId(queueId)}/status`),
    list: (doctorId, date) => request('GET', `/queue/doctor/${cleanId(doctorId)}?appointment_date=${date}`),
    callNext: (doctorId, session) =>
      request('POST', `/queue/doctor/${cleanId(doctorId)}/call-next`, { session }),
    complete: (queueId) => request('POST', `/queue/${cleanId(queueId)}/complete`),
    escalate: (queueId, tier) => request('POST', `/queue/${cleanId(queueId)}/escalate`, { tier }),
    myAppointments: () => request('GET', '/queue/patient/my'),
  },

  // ── Clinical ───────────────────────────────────────────────────────────────
  clinical: {
    submitSymptoms: (queueId, symptomText) =>
      request('POST', `/clinical/${cleanId(queueId)}/symptoms`, { symptom_text: symptomText }),
    getSymptoms: (queueId) => request('GET', `/clinical/${cleanId(queueId)}/symptoms`),
    submitNotes: (queueId, payload) =>
      request('POST', `/clinical/${cleanId(queueId)}/post-visit`, payload),
    getNotes: (queueId) => request('GET', `/clinical/${cleanId(queueId)}/post-visit`),
  },

  // ── Admin ──────────────────────────────────────────────────────────────────
  admin: {
    dashboard: () => request('GET', '/admin/dashboard'),
    delays: () => request('GET', '/admin/delays'),
    seedDemo: () => request('POST', '/admin/seed-demo', null, false),
  },

  // ── Health check ───────────────────────────────────────────────────────────
  health: () => fetch('/health').then((r) => r.json()),
};
