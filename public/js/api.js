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

export async function apiUpload(path, formData) {
  let response;
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: authHeaders(),
      body: formData,
    });
  } catch {
    networkError();
  }
  if (!response.ok) await throwApiError(response);
  return response.json();
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

export function listCompositions() {
  return apiFetch('/api/v1/compositions');
}

export function createCoin(body) {
  return apiFetch('/api/v1/coins', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function uploadCoinImage(accession, kind, blob, filename) {
  const fd = new FormData();
  fd.append(kind, blob, filename || (kind + '.jpg'));
  return apiUpload('/api/v1/coins/' + encodeURIComponent(accession) + '/images', fd);
}

export function moveCoin(accession, locationId, expectedFrom) {
  const body = { location_id: locationId };
  if (expectedFrom != null) body.expected_from_location_id = expectedFrom;
  return apiFetch(`/api/v1/coins/${encodeURIComponent(accession)}/move`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function locationTree() {
  return apiFetch('/api/v1/locations/tree');
}

export function getLocation(locationId, recursive) {
  const base = '/api/v1/locations/' + encodeURIComponent(locationId);
  if (recursive === undefined) return apiFetch(base);
  return apiFetch(base + '?recursive=' + (recursive ? 'true' : 'false'));
}

export function createLocation(kind, label, parentId) {
  const body = { kind, label };
  if (parentId != null) body.parent_id = parentId;
  return apiFetch('/api/v1/locations', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function listSets() {
  return apiFetch('/api/v1/sets');
}

export function getSetStatus(setId) {
  return apiFetch('/api/v1/sets/' + encodeURIComponent(setId) + '/status');
}

export function getSetGaps(setId) {
  return apiFetch('/api/v1/sets/' + encodeURIComponent(setId) + '/gaps');
}

export function getSetBoard(setId) {
  return apiFetch('/api/v1/sets/' + encodeURIComponent(setId) + '/board');
}

export function assignToSet(setId, slot, accession) {
  return apiFetch('/api/v1/sets/' + encodeURIComponent(setId) + '/assign', {
    method: 'POST',
    body: JSON.stringify({ slot, accession }),
  });
}

export function meltStatus() {
  return apiFetch('/api/v1/melt/status');
}

export function portfolioValue() {
  return apiFetch('/api/v1/portfolio/value');
}

export function updateMelt() {
  return apiFetch('/api/v1/melt/update', { method: 'POST' });
}

export function getAppraisalReport(top = 10) {
  return apiFetch(`/api/v1/report/appraisal?top=${encodeURIComponent(top)}`);
}

export function getAppraisalReportPdf(top = 10) {
  return fetchBlob(`/api/v1/report/appraisal.pdf?top=${encodeURIComponent(top)}`);
}

// ---------------------------------------------------------------------------
// Rolls
// ---------------------------------------------------------------------------

export function listRolls(status) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  return apiFetch(`/api/v1/rolls${qs}`);
}

export function getRoll(rollNo) {
  return apiFetch(`/api/v1/rolls/${encodeURIComponent(rollNo)}`);
}

export function createRoll(body) {
  return apiFetch('/api/v1/rolls', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function updateRoll(rollNo, body) {
  return apiFetch(`/api/v1/rolls/${encodeURIComponent(rollNo)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function pullRoll(rollNo, count, quick) {
  const body = { count };
  if (quick != null) body.quick = quick;
  return apiFetch(`/api/v1/rolls/${encodeURIComponent(rollNo)}/pull`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function getRollLabelsPdf(rollNos) {
  const qs = new URLSearchParams();
  for (const rollNo of rollNos || []) qs.append('rolls', rollNo);
  const query = qs.toString();
  return fetchBlob(`/api/v1/labels/rolls.pdf${query ? `?${query}` : ''}`);
}

// ---------------------------------------------------------------------------
// Album imports
// ---------------------------------------------------------------------------

export function listAlbumImports() {
  return apiFetch('/api/v1/albums/imports');
}

export function getAlbumImport(importId) {
  return apiFetch(`/api/v1/albums/imports/${encodeURIComponent(importId)}`);
}

export function createAlbumImport(name) {
  const body = {};
  if (name) body.name = name;
  return apiFetch('/api/v1/albums/imports', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function discardAlbumImport(importId) {
  return apiFetch(`/api/v1/albums/imports/${encodeURIComponent(importId)}`, {
    method: 'DELETE',
  });
}

export function uploadAlbumPages(importId, files) {
  const fd = new FormData();
  for (const file of files) fd.append('pages', file, file.name || 'page.jpg');
  return apiUpload(`/api/v1/albums/imports/${encodeURIComponent(importId)}/pages`, fd);
}

export function getAlbumPageImageUrl(importId, pageId) {
  return `/api/v1/albums/imports/${encodeURIComponent(importId)}/pages/${encodeURIComponent(pageId)}/image`;
}

export function fetchAlbumPageImage(importId, pageId) {
  return fetchBlob(getAlbumPageImageUrl(importId, pageId));
}

export function patchAlbumSlot(importId, slotId, fillState) {
  return apiFetch(
    `/api/v1/albums/imports/${encodeURIComponent(importId)}/slots/${encodeURIComponent(slotId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ fill_state: fillState }),
    },
  );
}

export function commitAlbumImport(importId, body) {
  return apiFetch(`/api/v1/albums/imports/${encodeURIComponent(importId)}/commit`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Set needs / want lists
// ---------------------------------------------------------------------------

export function getSetNeeds(setId) {
  return apiFetch(`/api/v1/sets/${encodeURIComponent(setId)}/needs`);
}

export function getWantlistPdf(setId) {
  return fetchBlob(`/api/v1/sets/${encodeURIComponent(setId)}/wantlist.pdf`);
}
