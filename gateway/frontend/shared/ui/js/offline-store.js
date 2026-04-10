// offline-store.js
const DB_NAME = 'TerreneitorDB';
const STORE_NAME = 'offline_photos';
const DB_VERSION = 1;

let db;

function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (e) => {
      db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
      }
    };

    request.onsuccess = (e) => {
      db = e.target.result;
      resolve(db);
    };

    request.onerror = (e) => {
      reject('Error opening DB: ' + e.target.errorCode);
    };
  });
}

async function savePhotoOffline(photoBlob, metadata) {
  if (!db) await openDB();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readwrite');
    const store = transaction.objectStore(STORE_NAME);

    const record = {
      photo: photoBlob,
      metadata: metadata,
      timestamp: new Date().toISOString(),
    };

    const request = store.add(record);

    request.onsuccess = (e) => resolve(e.target.result);
    request.onerror = (e) => reject(e);
  });
}

async function getOfflinePhotos() {
  if (!db) await openDB();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readonly');
    const store = transaction.objectStore(STORE_NAME);
    const request = store.getAll();

    request.onsuccess = () => resolve(request.result);
    request.onerror = (e) => reject(e);
  });
}

async function clearOfflinePhoto(id) {
  if (!db) await openDB();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readwrite');
    const store = transaction.objectStore(STORE_NAME);
    const request = store.delete(id);

    request.onsuccess = () => resolve(true);
    request.onerror = (e) => reject(e);
  });
}

// Export globally
window.OfflineStore = {
  init: openDB,
  save: savePhotoOffline,
  getAll: getOfflinePhotos,
  remove: clearOfflinePhoto,
};
