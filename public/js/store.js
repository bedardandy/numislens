const DB_NAME = 'numislens';
const DB_VERSION = 1;

function idbAvailable() {
  return typeof indexedDB !== 'undefined' && !!indexedDB;
}

function requestToPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transactionToPromise(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('kv')) {
        db.createObjectStore('kv');
      }
      if (!db.objectStoreNames.contains('queue')) {
        db.createObjectStore('queue', { autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function kvGet(key) {
  if (!idbAvailable()) return null;
  const db = await openDb();
  const tx = db.transaction('kv', 'readonly');
  const result = await requestToPromise(tx.objectStore('kv').get(key));
  await transactionToPromise(tx);
  db.close();
  return result === undefined ? null : result;
}

export async function kvSet(key, value) {
  if (!idbAvailable()) return;
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('kv', 'readwrite');
    tx.objectStore('kv').put(value, key);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

export async function kvDelete(key) {
  if (!idbAvailable()) return;
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('kv', 'readwrite');
    tx.objectStore('kv').delete(key);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

export async function queueAdd(record) {
  if (!idbAvailable()) return;
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('queue', 'readwrite');
    const req = tx.objectStore('queue').add(record);
    let key;
    req.onsuccess = () => {
      key = req.result;
    };
    req.onerror = () => {
      db.close();
      reject(req.error);
    };
    tx.oncomplete = () => {
      db.close();
      resolve(key);
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

export async function queueAll() {
  if (!idbAvailable()) return [];
  const db = await openDb();
  const tx = db.transaction('queue', 'readonly');
  const store = tx.objectStore('queue');
  const [keys, records] = await Promise.all([
    requestToPromise(store.getAllKeys()),
    requestToPromise(store.getAll()),
  ]);
  await transactionToPromise(tx);
  db.close();
  return keys.map((key, i) => ({ key, record: records[i] }));
}

export async function queueDelete(key) {
  if (!idbAvailable()) return;
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('queue', 'readwrite');
    tx.objectStore('queue').delete(key);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

export async function queueCount() {
  if (!idbAvailable()) return 0;
  const db = await openDb();
  const tx = db.transaction('queue', 'readonly');
  const count = await requestToPromise(tx.objectStore('queue').count());
  await transactionToPromise(tx);
  db.close();
  return count;
}
