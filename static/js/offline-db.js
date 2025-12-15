/**
 * IndexedDB wrapper for offline ordering support.
 * Stores menu items, tables, and pending orders for offline use.
 */

const DB_NAME = 'kaffero-offline';
const DB_VERSION = 1;

const STORES = {
  MENU: 'menu',
  TABLES: 'tables',
  PENDING_ORDERS: 'pending_orders',
  CART: 'cart',
};

class OfflineDB {
  constructor() {
    this.db = null;
    this.isReady = false;
  }

  /**
   * Initialize the database
   */
  async init() {
    if (this.db) return this.db;

    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onerror = () => {
        console.error('Failed to open IndexedDB:', request.error);
        reject(request.error);
      };

      request.onsuccess = () => {
        this.db = request.result;
        this.isReady = true;
        console.log('IndexedDB initialized');
        resolve(this.db);
      };

      request.onupgradeneeded = (event) => {
        const db = event.target.result;

        // Menu store - stores categories with their items
        if (!db.objectStoreNames.contains(STORES.MENU)) {
          db.createObjectStore(STORES.MENU, { keyPath: 'id' });
        }

        // Tables store - stores floors with their tables
        if (!db.objectStoreNames.contains(STORES.TABLES)) {
          db.createObjectStore(STORES.TABLES, { keyPath: 'id' });
        }

        // Pending orders store - orders created offline
        if (!db.objectStoreNames.contains(STORES.PENDING_ORDERS)) {
          const orderStore = db.createObjectStore(STORES.PENDING_ORDERS, {
            keyPath: 'offline_id',
            autoIncrement: false,
          });
          orderStore.createIndex('table_seat', ['table_id', 'seat'], { unique: false });
          orderStore.createIndex('created_at', 'created_at', { unique: false });
        }

        // Cart store - current cart state per table/seat
        if (!db.objectStoreNames.contains(STORES.CART)) {
          db.createObjectStore(STORES.CART, { keyPath: 'key' });
        }
      };
    });
  }

  /**
   * Get a transaction and object store
   */
  getStore(storeName, mode = 'readonly') {
    const tx = this.db.transaction(storeName, mode);
    return tx.objectStore(storeName);
  }

  // ==========================================================================
  // Menu Methods
  // ==========================================================================

  /**
   * Save menu data (categories with items)
   */
  async saveMenu(menuData) {
    await this.init();
    const store = this.getStore(STORES.MENU, 'readwrite');

    // Clear existing data
    store.clear();

    // Save each category
    for (const category of menuData.categories) {
      store.put(category);
    }

    // Save timestamp
    store.put({ id: '_meta', timestamp: menuData.timestamp });

    return new Promise((resolve, reject) => {
      store.transaction.oncomplete = () => resolve();
      store.transaction.onerror = () => reject(store.transaction.error);
    });
  }

  /**
   * Get all menu categories with items
   */
  async getMenu() {
    await this.init();
    const store = this.getStore(STORES.MENU);

    return new Promise((resolve, reject) => {
      const request = store.getAll();
      request.onsuccess = () => {
        const results = request.result.filter((item) => item.id !== '_meta');
        resolve(results);
      };
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Get a specific menu item by ID
   */
  async getMenuItem(categoryId, itemId) {
    const categories = await this.getMenu();
    for (const category of categories) {
      const item = category.items.find((i) => i.id === itemId);
      if (item) {
        return { ...item, category_name: category.name };
      }
    }
    return null;
  }

  // ==========================================================================
  // Tables Methods
  // ==========================================================================

  /**
   * Save tables data (floors with tables)
   */
  async saveTables(tablesData) {
    await this.init();
    const store = this.getStore(STORES.TABLES, 'readwrite');

    // Clear existing data
    store.clear();

    // Save each floor
    for (const floor of tablesData.floors) {
      store.put(floor);
    }

    // Save timestamp
    store.put({ id: '_meta', timestamp: tablesData.timestamp });

    return new Promise((resolve, reject) => {
      store.transaction.oncomplete = () => resolve();
      store.transaction.onerror = () => reject(store.transaction.error);
    });
  }

  /**
   * Get all floors with tables
   */
  async getTables() {
    await this.init();
    const store = this.getStore(STORES.TABLES);

    return new Promise((resolve, reject) => {
      const request = store.getAll();
      request.onsuccess = () => {
        const results = request.result.filter((item) => item.id !== '_meta');
        resolve(results);
      };
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Get a specific table by ID
   */
  async getTable(tableId) {
    const floors = await this.getTables();
    for (const floor of floors) {
      const table = floor.tables.find((t) => t.id === tableId);
      if (table) {
        return { ...table, floor_name: floor.name };
      }
    }
    return null;
  }

  // ==========================================================================
  // Cart Methods (temporary order state)
  // ==========================================================================

  /**
   * Get cart key for table/seat
   */
  _cartKey(tableId, seat) {
    return `${tableId}_${seat}`;
  }

  /**
   * Get cart items for a table/seat
   */
  async getCart(tableId, seat) {
    await this.init();
    const store = this.getStore(STORES.CART);
    const key = this._cartKey(tableId, seat);

    return new Promise((resolve, reject) => {
      const request = store.get(key);
      request.onsuccess = () => {
        resolve(request.result?.items || []);
      };
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Add item to cart
   */
  async addToCart(tableId, seat, item) {
    await this.init();
    const store = this.getStore(STORES.CART, 'readwrite');
    const key = this._cartKey(tableId, seat);

    const existing = await this.getCart(tableId, seat);

    // Check if item already exists
    const existingIndex = existing.findIndex((i) => i.menu_item_id === item.menu_item_id);
    if (existingIndex >= 0) {
      existing[existingIndex].quantity += item.quantity || 1;
    } else {
      existing.push({
        menu_item_id: item.menu_item_id,
        name: item.name,
        price: item.price,
        quantity: item.quantity || 1,
        special_instructions: item.special_instructions || '',
      });
    }

    return new Promise((resolve, reject) => {
      const request = store.put({ key, items: existing, updated_at: new Date().toISOString() });
      request.onsuccess = () => resolve(existing);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Remove item from cart
   */
  async removeFromCart(tableId, seat, menuItemId) {
    await this.init();
    const store = this.getStore(STORES.CART, 'readwrite');
    const key = this._cartKey(tableId, seat);

    const existing = await this.getCart(tableId, seat);
    const filtered = existing.filter((i) => i.menu_item_id !== menuItemId);

    return new Promise((resolve, reject) => {
      const request = store.put({ key, items: filtered, updated_at: new Date().toISOString() });
      request.onsuccess = () => resolve(filtered);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Clear cart for a table/seat
   */
  async clearCart(tableId, seat) {
    await this.init();
    const store = this.getStore(STORES.CART, 'readwrite');
    const key = this._cartKey(tableId, seat);

    return new Promise((resolve, reject) => {
      const request = store.delete(key);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  // ==========================================================================
  // Pending Orders Methods
  // ==========================================================================

  /**
   * Generate unique offline ID
   */
  _generateOfflineId() {
    return `offline_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Save a pending order (created offline)
   */
  async savePendingOrder(tableId, seat, items, autoConfirm = true) {
    await this.init();
    const store = this.getStore(STORES.PENDING_ORDERS, 'readwrite');

    const order = {
      offline_id: this._generateOfflineId(),
      table_id: tableId,
      seat: seat,
      items: items.map((item) => ({
        menu_item_id: item.menu_item_id,
        quantity: item.quantity,
        special_instructions: item.special_instructions || '',
      })),
      auto_confirm: autoConfirm,
      created_at: new Date().toISOString(),
      status: 'pending', // pending, syncing, synced, failed
    };

    return new Promise((resolve, reject) => {
      const request = store.add(order);
      request.onsuccess = () => resolve(order);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Get all pending orders
   */
  async getPendingOrders() {
    await this.init();
    const store = this.getStore(STORES.PENDING_ORDERS);

    return new Promise((resolve, reject) => {
      const request = store.getAll();
      request.onsuccess = () => {
        // Return only orders that need syncing
        const pending = request.result.filter((o) => o.status === 'pending' || o.status === 'failed');
        resolve(pending);
      };
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Get pending orders count
   */
  async getPendingOrdersCount() {
    const orders = await this.getPendingOrders();
    return orders.length;
  }

  /**
   * Update pending order status
   */
  async updatePendingOrderStatus(offlineId, status, serverOrderNumber = null) {
    await this.init();
    const store = this.getStore(STORES.PENDING_ORDERS, 'readwrite');

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

  /**
   * Delete synced orders (cleanup)
   */
  async deleteSyncedOrders() {
    await this.init();
    const store = this.getStore(STORES.PENDING_ORDERS, 'readwrite');

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

  // ==========================================================================
  // Sync Methods
  // ==========================================================================

  /**
   * Sync all pending orders to server
   */
  async syncPendingOrders() {
    const pendingOrders = await this.getPendingOrders();

    if (pendingOrders.length === 0) {
      console.log('No pending orders to sync');
      return { synced: 0, failed: 0 };
    }

    console.log(`Syncing ${pendingOrders.length} pending orders...`);

    // Mark as syncing
    for (const order of pendingOrders) {
      await this.updatePendingOrderStatus(order.offline_id, 'syncing');
    }

    try {
      const response = await fetch('/waiter/api/orders/sync/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ orders: pendingOrders }),
      });

      if (!response.ok) {
        throw new Error(`Sync failed: ${response.status}`);
      }

      const result = await response.json();

      // Update order statuses based on results
      for (const orderResult of result.results) {
        if (orderResult.success) {
          await this.updatePendingOrderStatus(
            orderResult.offline_id,
            'synced',
            orderResult.order_number
          );
        } else {
          await this.updatePendingOrderStatus(orderResult.offline_id, 'failed');
        }
      }

      // Clean up synced orders
      await this.deleteSyncedOrders();

      console.log(`Sync complete: ${result.synced} synced, ${result.failed} failed`);
      return result;
    } catch (error) {
      console.error('Sync failed:', error);

      // Mark orders as failed
      for (const order of pendingOrders) {
        await this.updatePendingOrderStatus(order.offline_id, 'failed');
      }

      throw error;
    }
  }

  /**
   * Fetch and cache menu data from server
   */
  async refreshMenu() {
    try {
      const response = await fetch('/waiter/api/menu/', {
        credentials: 'same-origin',
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch menu: ${response.status}`);
      }

      const data = await response.json();
      await this.saveMenu(data);
      console.log('Menu cached successfully');
      return data;
    } catch (error) {
      console.error('Failed to refresh menu:', error);
      throw error;
    }
  }

  /**
   * Fetch and cache tables data from server
   */
  async refreshTables() {
    try {
      const response = await fetch('/waiter/api/tables/', {
        credentials: 'same-origin',
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch tables: ${response.status}`);
      }

      const data = await response.json();
      await this.saveTables(data);
      console.log('Tables cached successfully');
      return data;
    } catch (error) {
      console.error('Failed to refresh tables:', error);
      throw error;
    }
  }

  /**
   * Refresh all cached data
   */
  async refreshAll() {
    await Promise.all([this.refreshMenu(), this.refreshTables()]);
  }
}

// Export singleton instance
const offlineDB = new OfflineDB();

// Initialize on load
if (typeof window !== 'undefined') {
  window.offlineDB = offlineDB;
  offlineDB.init().catch(console.error);
}
