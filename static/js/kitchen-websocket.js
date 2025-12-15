/**
 * Kitchen Display System WebSocket Client
 * Handles real-time updates for the kitchen display
 */

class KitchenWebSocket {
    constructor(options = {}) {
        this.wsUrl = options.wsUrl || this.getWebSocketUrl();
        this.reconnectInterval = options.reconnectInterval || 3000;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
        this.reconnectAttempts = 0;
        this.ws = null;
        this.isConnected = false;
        this.pingInterval = null;
        this.audioEnabled = options.audioEnabled !== false;

        // Audio for notifications
        this.notificationSound = null;
        this.initAudio();

        // Event callbacks
        this.onConnect = options.onConnect || (() => {});
        this.onDisconnect = options.onDisconnect || (() => {});
        this.onNewOrder = options.onNewOrder || (() => {});
        this.onOrderUpdated = options.onOrderUpdated || (() => {});
        this.onOrderStatusChanged = options.onOrderStatusChanged || (() => {});
        this.onOrderBumped = options.onOrderBumped || (() => {});
        this.onPriorityChanged = options.onPriorityChanged || (() => {});
        this.onOrdersList = options.onOrdersList || (() => {});
        this.onError = options.onError || (() => {});
    }

    getWebSocketUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws/kitchen/`;
    }

    initAudio() {
        // Create audio context for notification sounds
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        } catch (e) {
            console.warn('Audio context not available:', e);
        }
    }

    playNotificationSound() {
        if (!this.audioEnabled || !this.audioContext) return;

        try {
            // Create a simple beep sound
            const oscillator = this.audioContext.createOscillator();
            const gainNode = this.audioContext.createGain();

            oscillator.connect(gainNode);
            gainNode.connect(this.audioContext.destination);

            oscillator.frequency.value = 800;
            oscillator.type = 'sine';

            gainNode.gain.setValueAtTime(0.3, this.audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, this.audioContext.currentTime + 0.5);

            oscillator.start(this.audioContext.currentTime);
            oscillator.stop(this.audioContext.currentTime + 0.5);
        } catch (e) {
            console.warn('Could not play notification sound:', e);
        }
    }

    connect() {
        if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
            return;
        }

        console.log('Connecting to Kitchen WebSocket...');

        try {
            this.ws = new WebSocket(this.wsUrl);

            this.ws.onopen = () => {
                console.log('Kitchen WebSocket connected');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.startPingInterval();
                this.onConnect();

                // Request current orders on connect
                this.requestOrders();
            };

            this.ws.onclose = (event) => {
                console.log('Kitchen WebSocket closed:', event.code, event.reason);
                this.isConnected = false;
                this.stopPingInterval();
                this.onDisconnect();
                this.scheduleReconnect();
            };

            this.ws.onerror = (error) => {
                console.error('Kitchen WebSocket error:', error);
                this.onError(error);
            };

            this.ws.onmessage = (event) => {
                this.handleMessage(event);
            };
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.scheduleReconnect();
        }
    }

    disconnect() {
        this.stopPingInterval();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.isConnected = false;
    }

    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnect attempts reached');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectInterval * Math.pow(1.5, this.reconnectAttempts - 1);

        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

        setTimeout(() => {
            this.connect();
        }, delay);
    }

    startPingInterval() {
        this.pingInterval = setInterval(() => {
            if (this.isConnected) {
                this.send({ command: 'ping' });
            }
        }, 30000);
    }

    stopPingInterval() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket not connected, cannot send:', data);
        }
    }

    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'connection_established':
                    console.log('Connection confirmed:', data.message);
                    break;

                case 'pong':
                    // Ping response received
                    break;

                case 'new_order':
                    this.playNotificationSound();
                    this.onNewOrder(data);
                    break;

                case 'order_updated':
                    this.onOrderUpdated(data);
                    break;

                case 'order_status_changed':
                    this.onOrderStatusChanged(data);
                    break;

                case 'order_bumped':
                    this.onOrderBumped(data);
                    break;

                case 'priority_changed':
                    this.onPriorityChanged(data);
                    break;

                case 'orders_list':
                    this.onOrdersList(data.orders);
                    break;

                case 'command_result':
                    console.log('Command result:', data);
                    break;

                case 'error':
                    console.error('Server error:', data.message);
                    this.onError(data);
                    break;

                default:
                    console.log('Unknown message type:', data.type, data);
            }
        } catch (error) {
            console.error('Error parsing WebSocket message:', error, event.data);
        }
    }

    // Commands
    requestOrders() {
        this.send({ command: 'request_orders' });
    }

    bumpOrder(orderId) {
        this.send({ command: 'bump', order_id: orderId });
    }

    recallOrder(orderId) {
        this.send({ command: 'recall', order_id: orderId });
    }

    startPreparing(orderId) {
        this.send({ command: 'start_preparing', order_id: orderId });
    }

    setPriority(orderId, priority) {
        this.send({ command: 'set_priority', order_id: orderId, priority: priority });
    }

    setAudioEnabled(enabled) {
        this.audioEnabled = enabled;
        // Resume audio context if needed (required after user interaction)
        if (enabled && this.audioContext && this.audioContext.state === 'suspended') {
            this.audioContext.resume();
        }
    }
}

/**
 * Kitchen Display UI Manager
 * Manages the UI updates for the kitchen display
 */
class KitchenDisplayManager {
    constructor(wsClient) {
        this.ws = wsClient;
        this.orders = {
            pending: [],
            preparing: [],
            ready: []
        };

        // Bind WebSocket events
        this.ws.onOrdersList = (orders) => this.handleOrdersList(orders);
        this.ws.onNewOrder = (data) => this.handleNewOrder(data);
        this.ws.onOrderStatusChanged = (data) => this.handleOrderStatusChanged(data);
        this.ws.onOrderBumped = (data) => this.handleOrderBumped(data);
        this.ws.onPriorityChanged = (data) => this.handlePriorityChanged(data);
        this.ws.onConnect = () => this.handleConnect();
        this.ws.onDisconnect = () => this.handleDisconnect();
    }

    handleConnect() {
        this.updateConnectionStatus(true);
    }

    handleDisconnect() {
        this.updateConnectionStatus(false);
    }

    updateConnectionStatus(connected) {
        const indicator = document.getElementById('connection-status');
        if (indicator) {
            if (connected) {
                indicator.classList.remove('bg-red-500');
                indicator.classList.add('bg-green-500');
                indicator.title = 'Connected';
            } else {
                indicator.classList.remove('bg-green-500');
                indicator.classList.add('bg-red-500');
                indicator.title = 'Disconnected - Reconnecting...';
            }
        }
    }

    handleOrdersList(orders) {
        this.orders = orders;
        this.renderAllColumns();
    }

    handleNewOrder(data) {
        const order = data.order;

        // Add to pending if status is confirmed
        if (order.status === 'confirmed') {
            this.orders.pending.unshift(order);
            this.renderColumn('pending');
            this.flashColumn('pending');
        }
    }

    handleOrderStatusChanged(data) {
        const order = data.order;
        const oldStatus = data.old_status;
        const newStatus = data.new_status;

        // Remove from old column
        this.removeOrderFromColumn(order.id, oldStatus);

        // Add to new column
        const columnMap = {
            'confirmed': 'pending',
            'preparing': 'preparing',
            'ready': 'ready'
        };

        const targetColumn = columnMap[newStatus];
        if (targetColumn && this.orders[targetColumn]) {
            if (newStatus === 'ready') {
                this.orders[targetColumn].unshift(order);
            } else {
                this.orders[targetColumn].push(order);
            }
            this.renderColumn(targetColumn);
        }

        // Also re-render the old column
        const oldColumn = columnMap[oldStatus];
        if (oldColumn) {
            this.renderColumn(oldColumn);
        }
    }

    handleOrderBumped(data) {
        const order = data.order;

        // Remove from preparing
        this.removeOrderFromColumn(order.id, 'preparing');
        this.renderColumn('preparing');

        // Add to ready
        this.orders.ready.unshift(order);
        this.renderColumn('ready');
        this.flashColumn('ready');
    }

    handlePriorityChanged(data) {
        const order = data.order;

        // Update order in appropriate column
        for (const column of ['pending', 'preparing', 'ready']) {
            const index = this.orders[column].findIndex(o => o.id === order.id);
            if (index !== -1) {
                this.orders[column][index] = order;
                this.renderColumn(column);
                break;
            }
        }
    }

    removeOrderFromColumn(orderId, status) {
        const columnMap = {
            'confirmed': 'pending',
            'preparing': 'preparing',
            'ready': 'ready'
        };

        const column = columnMap[status];
        if (column && this.orders[column]) {
            this.orders[column] = this.orders[column].filter(o => o.id !== orderId);
        }
    }

    renderAllColumns() {
        this.renderColumn('pending');
        this.renderColumn('preparing');
        this.renderColumn('ready');
        this.updateCounts();
    }

    renderColumn(columnName) {
        const container = document.getElementById(`${columnName}-orders`);
        if (!container) return;

        const orders = this.orders[columnName] || [];

        if (orders.length === 0) {
            container.innerHTML = this.getEmptyStateHtml(columnName);
        } else {
            container.innerHTML = orders.map(order => this.getOrderCardHtml(order, columnName)).join('');
        }

        this.updateCounts();
    }

    flashColumn(columnName) {
        const header = document.querySelector(`[data-column="${columnName}"]`);
        if (header) {
            header.classList.add('animate-pulse');
            setTimeout(() => {
                header.classList.remove('animate-pulse');
            }, 2000);
        }
    }

    updateCounts() {
        for (const column of ['pending', 'preparing', 'ready']) {
            const countEl = document.getElementById(`${column}-count`);
            if (countEl) {
                countEl.textContent = this.orders[column]?.length || 0;
            }
        }
    }

    getElapsedTime(createdAt) {
        const created = new Date(createdAt);
        const now = new Date();
        const diffMs = now - created;
        const diffMins = Math.floor(diffMs / 60000);

        if (diffMins < 1) return 'Just now';
        if (diffMins === 1) return '1 min';
        return `${diffMins} mins`;
    }

    getPriorityColor(priority) {
        const colors = {
            'low': 'bg-slate-100 text-slate-700',
            'normal': 'bg-blue-100 text-blue-700',
            'high': 'bg-orange-100 text-orange-700',
            'rush': 'bg-red-100 text-red-700 animate-pulse'
        };
        return colors[priority] || colors['normal'];
    }

    getOrderCardHtml(order, column) {
        const priorityClass = order.ticket ? this.getPriorityColor(order.ticket.priority) : '';
        const priorityLabel = order.ticket?.priority?.toUpperCase() || 'NORMAL';
        const elapsed = this.getElapsedTime(order.created_at);

        const itemsHtml = order.items.map(item => `
            <div class="flex justify-between items-start py-1 border-b border-slate-100 last:border-0">
                <div class="flex-1">
                    <span class="font-medium">${item.quantity}x</span>
                    <span class="ml-1">${item.name}</span>
                    ${item.variant ? `<span class="text-slate-500 text-sm ml-1">(${item.variant})</span>` : ''}
                    ${item.special_instructions ? `<p class="text-xs text-orange-600 mt-0.5">${item.special_instructions}</p>` : ''}
                </div>
            </div>
        `).join('');

        const actionsHtml = this.getActionsHtml(order, column);

        return `
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden order-card" data-order-id="${order.id}">
                <div class="px-4 py-3 border-b border-slate-100 flex justify-between items-center">
                    <div>
                        <span class="font-bold text-lg">#${order.order_number}</span>
                        ${order.table_name ? `<span class="ml-2 text-slate-500">Table ${order.table_number || order.table_name}</span>` : ''}
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="text-sm text-slate-500">${elapsed}</span>
                        ${order.ticket ? `<span class="px-2 py-0.5 rounded text-xs font-medium ${priorityClass}">${priorityLabel}</span>` : ''}
                    </div>
                </div>

                <div class="px-4 py-3">
                    ${itemsHtml}
                </div>

                ${order.kitchen_notes ? `
                    <div class="px-4 py-2 bg-amber-50 border-t border-amber-100">
                        <p class="text-sm text-amber-800"><strong>Note:</strong> ${order.kitchen_notes}</p>
                    </div>
                ` : ''}

                <div class="px-4 py-3 bg-slate-50 border-t border-slate-100 flex gap-2">
                    ${actionsHtml}
                </div>
            </div>
        `;
    }

    getActionsHtml(order, column) {
        if (column === 'pending') {
            return `
                <button onclick="kitchenManager.startPreparing(${order.id})"
                        class="flex-1 px-4 py-2 bg-cyan-500 hover:bg-cyan-600 text-white rounded-lg font-medium transition-colors">
                    Start Preparing
                </button>
                <button onclick="kitchenManager.showPriorityMenu(${order.id})"
                        class="px-3 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg transition-colors">
                    Priority
                </button>
            `;
        } else if (column === 'preparing') {
            return `
                <button onclick="kitchenManager.bumpOrder(${order.id})"
                        class="flex-1 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-medium transition-colors">
                    Bump (Ready)
                </button>
                <button onclick="kitchenManager.showPriorityMenu(${order.id})"
                        class="px-3 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg transition-colors">
                    Priority
                </button>
            `;
        } else if (column === 'ready') {
            return `
                <button onclick="kitchenManager.recallOrder(${order.id})"
                        class="flex-1 px-4 py-2 bg-slate-500 hover:bg-slate-600 text-white rounded-lg font-medium transition-colors">
                    Recall
                </button>
            `;
        }
        return '';
    }

    getEmptyStateHtml(column) {
        const messages = {
            pending: 'No pending orders',
            preparing: 'No orders being prepared',
            ready: 'No orders ready'
        };

        return `
            <div class="flex flex-col items-center justify-center py-12 text-slate-400">
                <svg class="w-16 h-16 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
                </svg>
                <p class="text-lg">${messages[column]}</p>
            </div>
        `;
    }

    // Actions
    startPreparing(orderId) {
        this.ws.startPreparing(orderId);
    }

    bumpOrder(orderId) {
        this.ws.bumpOrder(orderId);
    }

    recallOrder(orderId) {
        this.ws.recallOrder(orderId);
    }

    showPriorityMenu(orderId) {
        const priorities = ['low', 'normal', 'high', 'rush'];
        const selected = prompt('Set priority (low, normal, high, rush):');
        if (selected && priorities.includes(selected.toLowerCase())) {
            this.ws.setPriority(orderId, selected.toLowerCase());
        }
    }

    toggleAudio() {
        const btn = document.getElementById('audio-toggle');
        const isEnabled = btn?.dataset.enabled === 'true';

        this.ws.setAudioEnabled(!isEnabled);

        if (btn) {
            btn.dataset.enabled = !isEnabled;
            btn.innerHTML = !isEnabled ?
                '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"/></svg>' :
                '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2"/></svg>';
        }
    }

    refresh() {
        this.ws.requestOrders();
    }
}

// Global instances
let kitchenWs = null;
let kitchenManager = null;

// Initialize on page load
function initKitchenDisplay() {
    kitchenWs = new KitchenWebSocket({
        audioEnabled: true
    });

    kitchenManager = new KitchenDisplayManager(kitchenWs);

    // Connect
    kitchenWs.connect();

    // Make available globally
    window.kitchenWs = kitchenWs;
    window.kitchenManager = kitchenManager;
}

// Auto-initialize if DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initKitchenDisplay);
} else {
    initKitchenDisplay();
}
