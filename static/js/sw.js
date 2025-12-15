// Service Worker for Coffee Shop Waiter PWA
// Version 2.0 - Full Offline Support

const CACHE_NAME = 'waiter-pwa-v2';
const OFFLINE_URL = '/waiter/offline/';
const DB_NAME = 'kaffero-offline';
const DB_VERSION = 1;

// Assets to cache on install
const PRECACHE_ASSETS = [
  '/waiter/',
  '/waiter/tables/',
  '/waiter/orders/',
  '/waiter/offline/',
  '/static/manifest.json',
  '/static/js/offline-db.js',
];

// API endpoints to cache for offline
const API_CACHE_URLS = ['/waiter/api/menu/', '/waiter/api/tables/'];

// =============================================================================
// IndexedDB Helper (same schema as offline-db.js)
// =============================================================================

let db = null;

async function openDB() {
  if (db) return db;

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      db = request.result;
      resolve(db);
    };

    request.onupgradeneeded = (event) => {
      const database = event.target.result;

      if (!database.objectStoreNames.contains('menu')) {
        database.createObjectStore('menu', { keyPath: 'id' });
      }

      if (!database.objectStoreNames.contains('tables')) {
        database.createObjectStore('tables', { keyPath: 'id' });
      }

      if (!database.objectStoreNames.contains('pending_orders')) {
        const orderStore = database.createObjectStore('pending_orders', {
          keyPath: 'offline_id',
          autoIncrement: false,
        });
        orderStore.createIndex('table_seat', ['table_id', 'seat'], { unique: false });
        orderStore.createIndex('created_at', 'created_at', { unique: false });
      }

      if (!database.objectStoreNames.contains('cart')) {
        database.createObjectStore('cart', { keyPath: 'key' });
      }
    };
  });
}

async function getPendingOrders() {
  const database = await openDB();
  const tx = database.transaction('pending_orders', 'readonly');
  const store = tx.objectStore('pending_orders');

  return new Promise((resolve, reject) => {
    const request = store.getAll();
    request.onsuccess = () => {
      const pending = request.result.filter((o) => o.status === 'pending' || o.status === 'failed');
      resolve(pending);
    };
    request.onerror = () => reject(request.error);
  });
}

async function updateOrderStatus(offlineId, status, serverOrderNumber = null) {
  const database = await openDB();
  const tx = database.transaction('pending_orders', 'readwrite');
  const store = tx.objectStore('pending_orders');

  return new Promise((resolve, reject) => {
    const getRequest = store.get(offlineId);
    getRequest.onsuccess = () => {
      const order = getRequest.result;
      if (order) {
        order.status = status;
        if (serverOrderNumber) {
          order.server_order_number = serverOrderNumber;
        }
        order.synced_at = new Date().toISOString();

        const putRequest = store.put(order);
        putRequest.onsuccess = () => resolve(order);
        putRequest.onerror = () => reject(putRequest.error);
      } else {
        reject(new Error('Order not found'));
      }
    };
    getRequest.onerror = () => reject(getRequest.error);
  });
}

async function deleteSyncedOrders() {
  const database = await openDB();
  const tx = database.transaction('pending_orders', 'readwrite');
  const store = tx.objectStore('pending_orders');

  return new Promise((resolve, reject) => {
    const request = store.getAll();
    request.onsuccess = () => {
      const synced = request.result.filter((o) => o.status === 'synced');
      for (const order of synced) {
        store.delete(order.offline_id);
      }
      resolve(synced.length);
    };
    request.onerror = () => reject(request.error);
  });
}

// =============================================================================
// Service Worker Events
// =============================================================================

// Install event - cache assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => {
        console.log('Service Worker: Caching files');
        return cache.addAll(PRECACHE_ASSETS);
      })
      .catch((error) => {
        console.error('Service Worker: Cache failed', error);
      })
  );
  // Activate immediately
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('Service Worker: Clearing old cache', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  // Take control of all clients immediately
  self.clients.claim();
});

// Fetch event - network first, then cache
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests (except for our API sync endpoints)
  if (request.method !== 'GET') {
    // Handle POST to sync endpoint specially when offline
    if (request.url.includes('/waiter/api/orders/')) {
      event.respondWith(handleOrderAPI(request));
      return;
    }
    return;
  }

  // Skip cross-origin requests
  if (!request.url.startsWith(self.location.origin)) {
    return;
  }

  // Cache API data for offline use
  if (API_CACHE_URLS.some((apiUrl) => request.url.includes(apiUrl))) {
    event.respondWith(handleAPIRequest(request));
    return;
  }

  // Handle page navigation and assets
  event.respondWith(handlePageRequest(request));
});

// Handle page requests - network first, then cache
async function handlePageRequest(request) {
  try {
    // Try network first
    const response = await fetch(request);

    // Clone and cache successful responses
    if (response.status === 200) {
      const responseClone = response.clone();
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, responseClone);
    }

    return response;
  } catch (error) {
    // Network failed, try cache
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }

    // If it's a navigation request, show offline page
    if (request.mode === 'navigate') {
      const offlinePage = await caches.match(OFFLINE_URL);
      if (offlinePage) {
        return offlinePage;
      }
    }

    return new Response('Offline', {
      status: 503,
      statusText: 'Service Unavailable',
    });
  }
}

// Handle API requests - network first, cache for offline
async function handleAPIRequest(request) {
  try {
    const response = await fetch(request);

    if (response.status === 200) {
      const responseClone = response.clone();
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, responseClone);
    }

    return response;
  } catch (error) {
    // Network failed, try cache
    const cached = await caches.match(request);
    if (cached) {
      console.log('Service Worker: Serving API from cache', request.url);
      return cached;
    }

    return new Response(JSON.stringify({ error: 'Offline', cached: false }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

// Handle order API requests - queue for sync if offline
async function handleOrderAPI(request) {
  try {
    // Try to send to server
    const response = await fetch(request);
    return response;
  } catch (error) {
    // Network failed - orders are already saved to IndexedDB by the client
    // Return a response indicating the order is queued
    return new Response(
      JSON.stringify({
        success: true,
        queued: true,
        message: 'Order saved for sync when online',
      }),
      {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }
    );
  }
}

// =============================================================================
// Background Sync
// =============================================================================

self.addEventListener('sync', (event) => {
  console.log('Service Worker: Sync event', event.tag);

  if (event.tag === 'sync-orders') {
    event.waitUntil(syncOrders());
  }
});

async function syncOrders() {
  console.log('Service Worker: Syncing orders...');

  try {
    const pendingOrders = await getPendingOrders();

    if (pendingOrders.length === 0) {
      console.log('Service Worker: No pending orders to sync');
      return;
    }

    console.log(`Service Worker: Found ${pendingOrders.length} orders to sync`);

    // Mark as syncing
    for (const order of pendingOrders) {
      await updateOrderStatus(order.offline_id, 'syncing');
    }

    // Send to server
    const response = await fetch('/waiter/api/orders/sync/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ orders: pendingOrders }),
    });

    if (!response.ok) {
      throw new Error(`Sync failed: ${response.status}`);
    }

    const result = await response.json();

    // Update statuses
    for (const orderResult of result.results) {
      if (orderResult.success) {
        await updateOrderStatus(orderResult.offline_id, 'synced', orderResult.order_number);
      } else {
        await updateOrderStatus(orderResult.offline_id, 'failed');
      }
    }

    // Clean up synced orders
    await deleteSyncedOrders();

    // Notify clients
    const clients = await self.clients.matchAll();
    for (const client of clients) {
      client.postMessage({
        type: 'SYNC_COMPLETE',
        data: result,
      });
    }

    console.log(`Service Worker: Sync complete - ${result.synced} synced, ${result.failed} failed`);
  } catch (error) {
    console.error('Service Worker: Sync failed', error);

    // Mark orders as failed for retry
    try {
      const pendingOrders = await getPendingOrders();
      for (const order of pendingOrders) {
        if (order.status === 'syncing') {
          await updateOrderStatus(order.offline_id, 'failed');
        }
      }
    } catch (e) {
      console.error('Service Worker: Failed to update order statuses', e);
    }

    throw error; // Re-throw to trigger retry
  }
}

// =============================================================================
// Push Notifications
// =============================================================================

self.addEventListener('push', (event) => {
  const options = {
    body: event.data?.text() || 'New notification',
    icon: '/static/images/icon-192.png',
    badge: '/static/images/icon-192.png',
    vibrate: [100, 50, 100],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1,
    },
    actions: [
      { action: 'view', title: 'View' },
      { action: 'close', title: 'Close' },
    ],
  };

  event.waitUntil(self.registration.showNotification('Kaffero', options));
});

// Notification click handler
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (event.action === 'view') {
    event.waitUntil(clients.openWindow('/waiter/orders/'));
  }
});

// =============================================================================
// Message Handler (for manual sync triggers)
// =============================================================================

self.addEventListener('message', (event) => {
  console.log('Service Worker: Message received', event.data);

  if (event.data && event.data.type === 'SYNC_ORDERS') {
    event.waitUntil(syncOrders());
  }

  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
