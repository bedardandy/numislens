import * as api from '../api.js';
import { toast, refreshQueueBanner } from '../app.js';
import { listQueuedMoves, discardMove } from '../offline.js';

export function renderSettings(el) {
  el.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Settings';
  el.appendChild(heading);

  const form = document.createElement('form');
  form.className = 'settings-form';
  form.addEventListener('submit', (e) => e.preventDefault());

  const tokenLabel = document.createElement('label');
  tokenLabel.htmlFor = 'token-input';
  tokenLabel.textContent = 'Daemon bearer token';
  form.appendChild(tokenLabel);

  const tokenInput = document.createElement('input');
  tokenInput.type = 'password';
  tokenInput.id = 'token-input';
  tokenInput.name = 'token';
  tokenInput.autocomplete = 'off';
  tokenInput.spellcheck = false;
  const existing = api.getToken();
  if (existing) tokenInput.value = existing;
  form.appendChild(tokenInput);

  const actions = document.createElement('div');
  actions.className = 'settings-actions';

  const saveBtn = document.createElement('button');
  saveBtn.type = 'button';
  saveBtn.textContent = 'Save';
  saveBtn.addEventListener('click', () => {
    api.setToken(tokenInput.value);
    toast('Token saved', 'success');
  });
  actions.appendChild(saveBtn);

  const clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.textContent = 'Clear';
  clearBtn.addEventListener('click', () => {
    api.clearToken();
    tokenInput.value = '';
    toast('Token cleared', 'info');
  });
  actions.appendChild(clearBtn);

  form.appendChild(actions);

  const healthSection = document.createElement('div');
  healthSection.className = 'settings-health';

  const healthBtn = document.createElement('button');
  healthBtn.type = 'button';
  healthBtn.textContent = 'Check daemon health';
  healthSection.appendChild(healthBtn);

  const healthStatus = document.createElement('div');
  healthStatus.className = 'settings-health-status';
  healthStatus.setAttribute('aria-live', 'polite');
  healthSection.appendChild(healthStatus);

  healthBtn.addEventListener('click', async () => {
    healthStatus.replaceChildren();
    healthBtn.disabled = true;
    try {
      const data = await api.health();
      const line = document.createElement('p');
      line.className = 'health-ok';
      const parts = ['Daemon OK'];
      if (data?.status != null) parts.push(`status: ${data.status}`);
      if (data?.version != null) parts.push(`version: ${data.version}`);
      line.textContent = parts.join(' \u2014 ');
      healthStatus.appendChild(line);
    } catch (err) {
      const line = document.createElement('p');
      line.className = 'health-error';
      line.textContent = err.message;
      healthStatus.appendChild(line);
    } finally {
      healthBtn.disabled = false;
    }
  });

  form.appendChild(healthSection);
  el.appendChild(form);

  const queueSection = document.createElement('div');
  queueSection.className = 'settings-queue';
  const queueHeading = document.createElement('h3');
  queueHeading.textContent = 'Queued offline moves';
  queueSection.appendChild(queueHeading);
  const queueList = document.createElement('div');
  queueList.className = 'settings-queue-list';
  queueSection.appendChild(queueList);
  el.appendChild(queueSection);

  async function loadQueue() {
    queueList.replaceChildren();
    let items;
    try {
      items = await listQueuedMoves();
    } catch {
      items = [];
    }
    if (!items.length) {
      const p = document.createElement('p');
      p.className = 'muted';
      p.textContent = 'No queued moves.';
      queueList.appendChild(p);
      return;
    }
    const ul = document.createElement('ul');
    ul.className = 'queue-items';
    for (const item of items) {
      const li = document.createElement('li');
      const span = document.createElement('span');
      span.textContent =
        item.record.accession +
        ' \u2192 location ' +
        item.record.location_id +
        ' (queued ' +
        item.record.queued_at +
        ')';
      li.appendChild(span);
      const discardBtn = document.createElement('button');
      discardBtn.type = 'button';
      discardBtn.textContent = 'Discard';
      discardBtn.addEventListener('click', async () => {
        if (
          !window.confirm(
            'Discard the queued move for ' + item.record.accession + '? This cannot be undone.'
          )
        ) {
          return;
        }
        try {
          await discardMove(item.key);
          toast('Queued move discarded', 'info');
          await loadQueue();
          await refreshQueueBanner();
        } catch (err) {
          toast('Could not discard: ' + err.message, 'error');
        }
      });
      li.appendChild(discardBtn);
      ul.appendChild(li);
    }
    queueList.appendChild(ul);
  }

  loadQueue();
}
