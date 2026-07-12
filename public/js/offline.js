import { kvGet, kvSet, queueAdd, queueAll, queueDelete, queueCount } from './store.js';
import { moveCoin } from './api.js';

const SNAP_PREFIX = 'snap:';

export function isNetworkError(err) {
  return err != null && (err.status === 0 || !navigator.onLine);
}

export async function cacheSnapshot(key, data) {
  await kvSet(SNAP_PREFIX + key, { data, cachedAt: new Date().toISOString() });
}

export async function readSnapshot(key) {
  const entry = await kvGet(SNAP_PREFIX + key);
  if (entry == null) return null;
  return entry;
}

export function offlineBanner(cachedAt) {
  const banner = document.createElement('div');
  banner.className = 'offline-banner';
  banner.setAttribute('role', 'status');
  banner.textContent = 'OFFLINE \u2014 data as of ' + (cachedAt || '\u2014');
  return banner;
}

export async function enqueueMove(accession, locationId, expectedFrom) {
  await queueAdd({
    accession,
    location_id: locationId,
    expected_from: expectedFrom != null ? expectedFrom : null,
    queued_at: new Date().toISOString(),
  });
}

export async function listQueuedMoves() {
  return queueAll();
}

export async function discardMove(key) {
  await queueDelete(key);
}

export async function queuedMoveCount() {
  return queueCount();
}

let replaying = false;

export async function replayMoveQueue() {
  if (replaying) return { replayed: 0, busy: true };
  replaying = true;
  let replayed = 0;
  try {
    const items = await listQueuedMoves();
    for (const item of items) {
      try {
        await moveCoin(item.record.accession, item.record.location_id, item.record.expected_from);
      } catch (err) {
        let message = err.message;
        if (err.status === 409) {
          message = item.record.accession + ' moved elsewhere since you queued this \u2014 review and discard or retry (Settings > Queued offline moves). ' + err.message;
        }
        return { replayed, stopped: true, error: message, record: item.record };
      }
      await discardMove(item.key);
      replayed += 1;
    }
    return { replayed, stopped: false };
  } finally {
    replaying = false;
  }
}
