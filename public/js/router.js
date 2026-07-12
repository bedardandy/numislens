function parseHash(hash) {
  const path = (hash || '').replace(/^#/, '') || '/';
  if (path === '/' || path === '') return { name: 'inventory', params: {} };
  if (path === '/settings') return { name: 'settings', params: {} };
  if (path === '/add') return { name: 'add', params: {} };
  if (path === '/locations') return { name: 'locations', params: {} };
  if (path === '/sets') return { name: 'sets', params: {} };
  if (path === '/melt') return { name: 'melt', params: {} };
  if (path === '/report') return { name: 'report', params: {} };
  const m = path.match(/^\/coin\/(.+)$/);
  if (m) return { name: 'coin', params: { accession: decodeURIComponent(m[1]) } };
  const sm = path.match(/^\/sets\/(.+)$/);
  if (sm) return { name: 'setboard', params: { setId: decodeURIComponent(sm[1]) } };
  const cm = path.match(/^\/count\/(.+)$/);
  if (cm) return { name: 'count', params: { locationId: decodeURIComponent(cm[1]) } };
  return { name: 'inventory', params: {} };
}

function redirectPathToHash() {
  const m = location.pathname.match(/^\/c\/(.+)$/);
  if (!m) return false;
  const accession = encodeURIComponent(decodeURIComponent(m[1]));
  location.replace(`/#/coin/${accession}`);
  return true;
}

export function navigate(hash) {
  location.hash = hash;
}

export function initRouter(onRoute) {
  const dispatch = () => onRoute(parseHash(location.hash));
  window.addEventListener('hashchange', dispatch);
  if (redirectPathToHash()) return;
  dispatch();
}
