import * as api from './api.js';
import { initRouter, navigate } from './router.js';
import { renderSettings } from './views/settings.js';
import { renderInventory } from './views/inventory.js';
import { renderCoin } from './views/coin.js';
import { renderAdd } from './views/add.js';
import { renderLocations } from './views/locations.js';
import { renderSets, renderSetBoard } from './views/sets.js';
import { renderMelt } from './views/melt.js';
import { renderReport } from './views/report.js';
import { renderCycleCount } from './views/cyclecount.js';
import { replayMoveQueue, queuedMoveCount } from './offline.js';

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

export async function refreshQueueBanner() {
  const bar = document.getElementById('status-bar');
  if (!bar) return;
  let count = 0;
  try { count = await queuedMoveCount(); } catch { count = 0; }
  if (count > 0) {
    bar.hidden = false;
    bar.textContent = count + ' queued move' + (count === 1 ? '' : 's') + (navigator.onLine ? ' — syncing…' : ' — will sync when online');
  } else if (!navigator.onLine) {
    bar.hidden = false;
    bar.textContent = 'Offline';
  } else {
    bar.hidden = true;
    bar.textContent = '';
  }
}

async function runReplay() {
  if (!navigator.onLine) return;
  let res;
  try { res = await replayMoveQueue(); } catch { return; }
  if (res.busy) return;
  if (res.replayed > 0) toast('Synced ' + res.replayed + ' queued move' + (res.replayed === 1 ? '' : 's'), 'success');
  if (res.stopped) toast('Sync stopped: ' + res.error, 'error');
  await refreshQueueBanner();
}

const NAV_ITEMS = [
  { id: 'inventory', label: 'Inventory', hash: '#/', route: 'inventory', group: 'primary' },
  { id: 'add', label: 'Add', hash: '#/add', route: 'add', group: 'primary' },
  { id: 'sets', label: 'Sets', hash: '#/sets', route: 'sets', group: 'more' },
  { id: 'melt', label: 'Melt', hash: '#/melt', route: 'melt', group: 'more' },
  { id: 'report', label: 'Report', hash: '#/report', route: 'report', group: 'more' },
  { id: 'locations', label: 'Locations', hash: '#/locations', route: 'locations', group: 'more' },
  { id: 'settings', label: 'Settings', hash: '#/settings', route: 'settings', group: 'more' },
];

function buildShell() {
  const app = document.getElementById('app');
  if (!app) return null;

  app.replaceChildren();

  const header = document.createElement('header');
  const nav = document.createElement('nav');
  nav.className = 'top-nav';
  nav.setAttribute('aria-label', 'Main');

  function makeNavLink(item) {
    const link = document.createElement('a');
    link.className = 'nav-item';
    link.id = `nav-${item.id}`;
    link.href = item.hash;
    link.textContent = item.label;
    link.dataset.route = item.route;
    return link;
  }

  for (const item of NAV_ITEMS) {
    if (item.group === 'primary') {
      nav.appendChild(makeNavLink(item));
    }
  }

  const more = document.createElement('div');
  more.className = 'nav-more';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'nav-more-toggle';
  toggle.textContent = 'More \u25be';
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-controls', 'nav-more-panel');
  toggle.setAttribute('aria-haspopup', 'true');
  const panel = document.createElement('div');
  panel.className = 'nav-more-panel';
  panel.id = 'nav-more-panel';
  panel.hidden = true;
  for (const item of NAV_ITEMS) {
    if (item.group === 'more') {
      panel.appendChild(makeNavLink(item));
    }
  }
  function closeMore() {
    panel.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
  }
  function openMore() {
    panel.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
  }
  toggle.addEventListener('click', (e) => {
    e.stopPropagation();
    if (panel.hidden) openMore();
    else closeMore();
  });
  panel.addEventListener('click', (e) => {
    if (e.target.closest('a')) closeMore();
  });
  document.addEventListener('click', (e) => {
    if (!more.contains(e.target)) closeMore();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMore();
  });
  more.appendChild(toggle);
  more.appendChild(panel);
  nav.appendChild(more);

  header.appendChild(nav);
  app.appendChild(header);

  const statusBar = document.createElement('div');
  statusBar.id = 'status-bar';
  statusBar.className = 'status-bar';
  statusBar.hidden = true;
  statusBar.setAttribute('role', 'status');
  statusBar.setAttribute('aria-live', 'polite');
  app.appendChild(statusBar);

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
  const activeRoute =
    routeName === 'coin' ? 'inventory' : routeName === 'setboard' ? 'sets' : routeName === 'count' ? 'locations' : routeName;
  for (const item of NAV_ITEMS) {
    if (!item.route) continue;
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
  refreshQueueBanner();

  if (!api.getToken() && route.name !== 'settings') {
    renderConnectPrompt(viewEl);
    return;
  }

  switch (route.name) {
    case 'inventory':
      renderInventory(viewEl);
      break;
    case 'add':
      renderAdd(viewEl);
      break;
    case 'locations':
      renderLocations(viewEl);
      break;
    case 'sets':
      renderSets(viewEl);
      break;
    case 'setboard':
      renderSetBoard(viewEl, route.params.setId);
      break;
    case 'melt':
      renderMelt(viewEl);
      break;
    case 'report':
      renderReport(viewEl);
      break;
    case 'coin':
      renderCoin(viewEl, route.params.accession);
      break;
    case 'settings':
      renderSettings(viewEl);
      break;
    case 'count':
      renderCycleCount(viewEl, route.params.locationId);
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
  window.addEventListener('online', () => { runReplay(); });
  window.addEventListener('offline', () => { refreshQueueBanner(); });
  refreshQueueBanner();
  runReplay();
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}
