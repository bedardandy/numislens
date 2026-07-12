const TOKEN_KEY = 'numislens_token';

export function getToken() {
  const t = localStorage.getItem(TOKEN_KEY);
  return t || null;
}

export function setToken(t) {
  if (t != null && t !== '') {
    localStorage.setItem(TOKEN_KEY, t);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function throwApiError(response) {
  let message = `Request failed (${response.status})`;
  try {
    const data = await response.json();
    if (data?.detail != null) {
      message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    }
  } catch {
    /* non-JSON error body */
  }
  const err = new Error(message);
  err.status = response.status;
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent('numislens:unauthorized'));
  }
  throw err;
}

function networkError() {
  const err = new Error('Cannot reach daemon');
  err.status = 0;
  throw err;
}

export async function apiFetch(path, options = {}) {
  const headers = authHeaders({ Accept: 'application/json', ...options.headers });
  if (options.body != null && !headers['Content-Type'] && !headers['content-type']) {
    headers['Content-Type'] = 'application/json';
  }

  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    networkError();
  }

  if (!response.ok) await throwApiError(response);
  return response.json();
}

export async function fetchBlob(path) {
  let response;
  try {
    response = await fetch(path, { headers: authHeaders() });
  } catch {
    networkError();
  }

  if (!response.ok) await throwApiError(response);
  return response.blob();
}

export function health() {
  return apiFetch('/api/v1/health');
}

export function listCoins(params = {}) {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value != null && value !== '') qs.set(key, value);
  }
  const query = qs.toString();
  return apiFetch(`/api/v1/coins${query ? `?${query}` : ''}`);
}

export function getCoin(accession) {
  return apiFetch(`/api/v1/coins/${encodeURIComponent(accession)}`);
}

export function moveCoin(accession, locationId) {
  return apiFetch(`/api/v1/coins/${encodeURIComponent(accession)}/move`, {
    method: 'POST',
    body: JSON.stringify({ location_id: locationId }),
  });
}

export function locationTree() {
  return apiFetch('/api/v1/locations/tree');
}
