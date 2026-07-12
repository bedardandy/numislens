import * as api from './api.js';
import { initRouter, navigate } from './router.js';
import { renderSettings } from './views/settings.js';
import { renderInventory } from './views/inventory.js';
import { renderCoin } from './views/coin.js';

const TOAST_DURATIONS = { error: 8000, info: 4000, success: 4000 };
let toastRegion = null;

export function toast(message, kind = 'info') {
  if (!toastRegion) {
    toastRegion = document.getElementById('toast-region');
  }
  if (!toastRegion) return;

  const item = document.createElement('div');
  item.className = `toast toast--${kind}`;
  item.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  const bg = kind === 'error' ? '#f44336' : kind === 'success' ? '#4caf50' : '#2196f3';
  item.style.cssText = `display:flex;align-items:flex-start;gap:0.5rem;padding:0.75rem 1rem;border-radius:6px;background:${bg};color:#fff;box-shadow:0 2px 8px rgba(0,0,0,0.2);`;

  const text = document.createElement('span');
  text.textContent = message;
  item.appendChild(text);

  const dismiss = document.createElement('button');
  dismiss.type = 'button';
  dismiss.className = 'toast-dismiss';
  dismiss.setAttribute('aria-label', 'Dismiss');
  dismiss.textContent = '\u00d7';
  dismiss.style.cssText = 'background:transparent;border:none;color:inherit;font-size:1.25rem;line-height:1;cursor:pointer;padding:0;margin-left:auto;';
  dismiss.addEventListener('click', () => item.remove());
  item.appendChild(dismiss);

  toastRegion.appendChild(item);

  const duration = TOAST_DURATIONS[kind] ?? TOAST_DURATIONS.info;
  let timer = window.setTimeout(() => item.remove(), duration);
  dismiss.addEventListener('click', () => window.clearTimeout(timer), { once: true });
}

const NAV_ITEMS = [
  { id: 'inventory', label: 'Inventory', hash: '#/', route: 'inventory' },
  { id: 'sets', label: 'Sets', disabled: true },
  { id: 'melt', label: 'Melt', disabled: true },
  { id: 'settings', label: 'Settings', hash: '#/settings', route: 'settings' },
];

function buildShell() {
  const app = document.getElementById('app');
  if (!app) return null;

  app.replaceChildren();

  const header = document.createElement('header');
  const nav = document.createElement('nav');
  nav.className = 'top-nav';
  nav.setAttribute('aria-label', 'Main');
  nav.style.cssText = 'display:flex;gap:0.75rem;flex-wrap:wrap;align-items:center;';

  for (const item of NAV_ITEMS) {
    if (item.disabled) {
      const span = document.createElement('span');
      span.className = 'nav-item nav-item--disabled';
      span.id = `nav-${item.id}`;
      span.textContent = item.label;
      span.title = 'Coming in Phase 3c';
      span.setAttribute('aria-disabled', 'true');
      span.setAttribute('aria-label', `${item.label} — Coming in Phase 3c`);
      span.style.cssText = 'opacity:0.5;cursor:not-allowed;';
      nav.appendChild(span);
    } else {
      const link = document.createElement('a');
      link.className = 'nav-item';
      link.id = `nav-${item.id}`;
      link.href = item.hash;
      link.textContent = item.label;
      link.dataset.route = item.route;
      nav.appendChild(link);
    }
  }

  header.appendChild(nav);
  app.appendChild(header);

  const main = document.createElement('main');
  const viewEl = document.createElement('div');
  viewEl.id = 'view';
  main.appendChild(viewEl);
  app.appendChild(main);

  let region = document.getElementById('toast-region');
  if (!region) {
    region = document.createElement('div');
    region.id = 'toast-region';
    region.className = 'toast-region';
    region.style.cssText = 'position:fixed;bottom:1rem;right:1rem;z-index:1000;display:flex;flex-direction:column;gap:0.5rem;max-width:min(24rem,calc(100vw - 2rem));';
    region.setAttribute('aria-live', 'polite');
    region.setAttribute('aria-atomic', 'false');
    document.body.appendChild(region);
  }
  toastRegion = region;

  return viewEl;
}

function setActiveNav(routeName) {
  const activeRoute = routeName === 'coin' ? 'inventory' : routeName;
  for (const item of NAV_ITEMS) {
    if (item.disabled || !item.route) continue;
    const el = document.getElementById(`nav-${item.id}`);
    if (!el) continue;
    const isActive = item.route === activeRoute;
    el.classList.toggle('nav-item--active', isActive);
    if (el.tagName === 'A') {
      el.style.fontWeight = isActive ? 'bold' : '';
      el.style.textDecoration = isActive ? 'underline' : '';
    }
    if (isActive) {
      el.setAttribute('aria-current', 'page');
    } else {
      el.removeAttribute('aria-current');
    }
  }
}

function renderConnectPrompt(viewEl) {
  viewEl.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Connect to your daemon';
  viewEl.appendChild(heading);

  const text = document.createElement('p');
  text.textContent = 'Enter your daemon bearer token in Settings to get started.';
  viewEl.appendChild(text);

  const link = document.createElement('a');
  link.href = '#/settings';
  link.className = 'btn';
  link.textContent = 'Go to Settings';
  link.addEventListener('click', (e) => {
    e.preventDefault();
    navigate('#/settings');
  });
  viewEl.appendChild(link);
}

function onRoute(route) {
  const viewEl = document.getElementById('view');
  if (!viewEl) return;

  setActiveNav(route.name);

  if (!api.getToken() && route.name !== 'settings') {
    renderConnectPrompt(viewEl);
    return;
  }

  switch (route.name) {
    case 'inventory':
      renderInventory(viewEl);
      break;
    case 'coin':
      renderCoin(viewEl, route.params.accession);
      break;
    case 'settings':
      renderSettings(viewEl);
      break;
    default:
      renderInventory(viewEl);
  }
}

function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}

function init() {
  buildShell();
  initRouter(onRoute);

  window.addEventListener('numislens:unauthorized', () => {
    toast('Session expired or token invalid — please re-enter your token', 'error');
    navigate('#/settings');
  });

  registerServiceWorker();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
