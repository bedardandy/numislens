import * as api from '../api.js';
import { toast } from '../app.js';

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
}
