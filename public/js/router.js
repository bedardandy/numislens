function parseHash(hash) {
  const path = (hash || '').replace(/^#/, '') || '/';
  if (path === '/' || path === '') return { name: 'inventory', params: {} };
  if (path === '/settings') return { name: 'settings', params: {} };
  if (path === '/add') return { name: 'add', params: {} };
  if (path === '/locations') return { name: 'locations', params: {} };
  if (path === '/sets') return { name: 'sets', params: {} };
  if (path === '/melt') return { name: 'melt', params: {} };
  if (path === '/report') return { name: 'report', params: {} };
  if (path === '/rolls') return { name: 'rolls', params: {} };
  if (path === '/albums') return { name: 'albums', params: {} };
  const m = path.match(/^\/coin\/(.+)$/);
  if (m) return { name: 'coin', params: { accession: decodeURIComponent(m[1]) } };
  const sm = path.match(/^\/sets\/(.+)$/);
  if (sm) return { name: 'setboard', params: { setId: decodeURIComponent(sm[1]) } };
  const cm = path.match(/^\/count\/(.+)$/);
  if (cm) return { name: 'count', params: { locationId: decodeURIComponent(cm[1]) } };
  const rm = path.match(/^\/roll\/(.+)$/);
  if (rm) return { name: 'roll', params: { rollNo: decodeURIComponent(rm[1]) } };
  const am = path.match(/^\/album\/(.+)$/);
  if (am) return { name: 'album', params: { importId: decodeURIComponent(am[1]) } };
  return { name: 'inventory', params: {} };
}

function redirectPathToHash() {
  const cm = location.pathname.match(/^\/c\/(.+)$/);
  if (cm) {
    const accession = encodeURIComponent(decodeURIComponent(cm[1]));
    location.replace(`/#/coin/${accession}`);
    return true;
  }
  const rm = location.pathname.match(/^\/r\/(.+)$/);
  if (rm) {
    const rollNo = encodeURIComponent(decodeURIComponent(rm[1]));
    location.replace(`/#/roll/${rollNo}`);
    return true;
  }
  return false;
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
