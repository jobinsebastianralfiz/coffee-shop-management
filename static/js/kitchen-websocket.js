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
        // Use shared notification sound module if available
        if (window.notificationSound) {
            this.soundModule = window.notificationSound;
            this.soundModule.setEnabled(this.audioEnabled);
        } else {
            // Fallback: Create audio context for notification sounds
            try {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            } catch (e) {
                console.warn('Audio context not available:', e);
            }
        }
    }

    playNotificationSound(soundType = 'newOrder') {
        if (!this.audioEnabled) return;

        // Use shared sound module if available
        if (this.soundModule) {
            this.soundModule.playSound(soundType);
            return;
        }

        // Fallback to inline audio
        if (!this.audioContext) return;

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

    playRushOrderSound() {
        this.playNotificationSound('rushOrder');
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
        } else if (this.httpFallback && data.command !== 'ping') {
            // No socket (e.g. WSGI server without websockets): use the HTTP endpoint
            this.httpFallback(data);
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
                    // Play different sound for rush orders
                    if (data.is_rush || data.priority === 'rush') {
                        this.playNotificationSound('rushOrder');
                    } else {
                        this.playNotificationSound('newOrder');
                    }
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
                    // Play rush sound when order is marked as rush
                    if (data.is_rush || data.priority === 'rush') {
                        this.playNotificationSound('rushOrder');
                    }
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

    // stationId (optional): act only on that station's items
    bumpOrder(orderId, stationId) {
        this.send(this.withStation({ command: 'bump', order_id: orderId }, stationId));
    }

    recallOrder(orderId, stationId) {
        this.send(this.withStation({ command: 'recall', order_id: orderId }, stationId));
    }

    startPreparing(orderId, stationId) {
        this.send(this.withStation({ command: 'start_preparing', order_id: orderId }, stationId));
    }

    withStation(message, stationId) {
        if (stationId) message.station_id = stationId;
        return message;
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

        // Station filter (set by the template on #kitchen-display)
        const root = document.getElementById('kitchen-display');
        const stationAttr = root?.dataset.stationId || '';
        this.stationId = /^\d+$/.test(stationAttr) ? parseInt(stationAttr, 10) : null;
        this.hasStations = !!(root?.dataset.hasStations);
        this.actionUrl = root?.dataset.actionUrl || '';
        this.csrfToken = root?.dataset.csrf || '';
        this.pollTimer = null;
        this.pollInterval = 5000;
        this.pollFailed = false;
        if (this.actionUrl) {
            this.ws.httpFallback = (message) => this.sendViaHttp(message);
        }

        // Bind WebSocket events
        this.ws.onOrdersList = (orders) => this.handleOrdersList(orders);
        this.ws.onNewOrder = (data) => this.handleNewOrder(data);
        this.ws.onOrderStatusChanged = (data) => this.handleOrderStatusChanged(data);
        this.ws.onOrderBumped = (data) => this.handleOrderBumped(data);
        this.ws.onPriorityChanged = (data) => this.handlePriorityChanged(data);
        this.ws.onOrderUpdated = (data) => this.handleOrderUpdated(data);
        this.ws.onConnect = () => this.handleConnect();
        this.ws.onDisconnect = () => this.handleDisconnect();
    }

    handleConnect() {
        this.stopPolling();
        this.updateConnectionStatus(true);
    }

    handleDisconnect() {
        this.startPolling();
        this.updateConnectionStatus(false);
    }

    // state: true = live socket; false = no socket (polling over HTTP when available)
    updateConnectionStatus(connected) {
        const indicator = document.getElementById('connection-status');
        const label = document.getElementById('connection-label');
        let color = 'bg-green-500', text = 'Live', title = 'Connected';
        if (!connected) {
            if (this.actionUrl && !this.pollFailed) {
                color = 'bg-amber-400'; text = 'Polling'; title = 'Live updates unavailable - refreshing every few seconds';
            } else {
                color = 'bg-red-500'; text = 'Offline'; title = 'Disconnected - Reconnecting...';
            }
        }
        if (indicator) {
            indicator.classList.remove('bg-green-500', 'bg-red-500', 'bg-amber-400');
            indicator.classList.add(color);
            indicator.title = title;
        }
        if (label) label.textContent = text;
    }

    // --- HTTP fallback (no websocket) -----------------------------------
    startPolling() {
        if (!this.actionUrl || this.pollTimer) return;
        this.pollTimer = setInterval(() => this.pollOnce(), this.pollInterval);
        this.pollOnce();
    }

    stopPolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    }

    stationQuery() {
        return this.stationId ? `?station_id=${this.stationId}` : '';
    }

    async pollOnce() {
        if (this.ws.isConnected) return this.stopPolling();
        try {
            const res = await fetch(this.actionUrl + this.stationQuery(), {
                headers: { 'Accept': 'application/json' },
                credentials: 'same-origin',
                cache: 'no-store',
            });
            const data = await res.json();
            if (!res.ok || !data.ok) throw new Error(data.message || `HTTP ${res.status}`);
            if (this.ws.isConnected) return;
            this.pollFailed = false;
            this.handleOrdersList(data.orders);
        } catch (e) {
            console.warn('Kitchen board refresh failed:', e);
            this.pollFailed = true;
        }
        if (!this.ws.isConnected) this.updateConnectionStatus(false);
    }

    async sendViaHttp(message) {
        const actions = { start_preparing: 'start', bump: 'bump', recall: 'recall', set_priority: 'priority' };
        if (message.command === 'request_orders') return this.pollOnce();
        const action = actions[message.command];
        if (!action) return;

        const body = new URLSearchParams({ action, order_id: message.order_id });
        if (message.priority) body.set('priority', message.priority);
        if (message.station_id) body.set('station_id', message.station_id);
        try {
            const res = await fetch(this.actionUrl, {
                method: 'POST',
                headers: { 'X-CSRFToken': this.csrfToken, 'Accept': 'application/json' },
                credentials: 'same-origin',
                body,
            });
            let data = {};
            try { data = await res.json(); } catch (e) { /* non-JSON error page */ }
            if (data.orders) this.handleOrdersList(data.orders);
            if (!res.ok || !data.ok) {
                this.showToast(data.message || `Action failed (HTTP ${res.status})`, 'error');
            }
        } catch (e) {
            this.showToast('Could not reach the server. Check the connection and try again.', 'error');
        }
    }

    showToast(text, type = 'info') {
        const container = document.getElementById('toast-container');
        const styles = {
            error: 'bg-red-50 border-red-200 text-red-800',
            success: 'bg-emerald-50 border-emerald-200 text-emerald-800',
            info: 'bg-blue-50 border-blue-200 text-blue-800',
        };
        const toast = document.createElement('div');
        toast.className = `toast-item fade-in flex items-center gap-3 px-5 py-4 rounded-xl shadow-lg border ${styles[type] || styles.info}`;
        toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
        const msg = document.createElement('p');
        msg.className = 'text-sm font-medium';
        msg.textContent = text;
        toast.appendChild(msg);
        if (container) {
            container.appendChild(toast);
        } else {
            toast.classList.add('fixed', 'top-6', 'right-6', 'z-50');
            document.body.appendChild(toast);
        }
        setTimeout(() => toast.remove(), 4000);
    }

    handleOrdersList(orders) {
        if (this.stationId) {
            // Re-bucket every order by this station's progress
            this.orders = { pending: [], preparing: [], ready: [] };
            const all = [...(orders.pending || []), ...(orders.preparing || []), ...(orders.ready || [])];
            all.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
            all.forEach(order => {
                const column = this.stationColumn(order);
                if (column) this.orders[column].push(order);
            });
            this.orders.ready.reverse();
            this.renderAllColumns();
            return;
        }
        this.orders = orders;
        this.renderAllColumns();
    }

    // --- Station mode helpers -------------------------------------------
    // Mirrors station_column() in apps/kitchen/services.py
    stationColumn(order) {
        if (!['confirmed', 'preparing', 'ready'].includes(order.status)) return null;
        // Items served in an earlier round are done with; only this round counts
        const items = (order.items || []).filter(i => i.status !== 'cancelled' && i.status !== 'served');
        const mine = items.filter(i => i.station_id === this.stationId);
        if (!mine.length) return null;
        const done = s => s === 'ready' || s === 'served';
        if (order.status === 'ready' || mine.every(i => done(i.status))) return 'ready';
        if (mine.some(i => i.status === 'preparing')) return 'preparing';
        if (order.status === 'preparing' && items.every(i => i.status === 'pending')) return 'preparing';
        if (mine.some(i => done(i.status))) return 'preparing';
        return 'pending';
    }

    upsertStationOrder(order, flash = false) {
        for (const column of ['pending', 'preparing', 'ready']) {
            this.orders[column] = (this.orders[column] || []).filter(o => o.id !== order.id);
        }
        const column = this.stationColumn(order);
        if (column) {
            if (column === 'ready') {
                this.orders.ready.unshift(order);
            } else {
                this.orders[column].push(order);
                this.orders[column].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
            }
        }
        this.renderAllColumns();
        if (column && flash) this.flashColumn(column);
    }

    handleOrderUpdated(data) {
        const order = data.order;
        if (!order) return;
        if (this.stationId) {
            const wasShown = ['pending', 'preparing', 'ready'].some(c => (this.orders[c] || []).some(o => o.id === order.id));
            this.upsertStationOrder(order, !wasShown);
            return;
        }
        // All stations: refresh the card in place (item ready/station tags)
        for (const column of ['pending', 'preparing', 'ready']) {
            const index = (this.orders[column] || []).findIndex(o => o.id === order.id);
            if (index !== -1) {
                this.orders[column][index] = order;
                this.renderColumn(column);
                break;
            }
        }
    }

    handleNewOrder(data) {
        const order = data.order;

        if (this.stationId) {
            this.upsertStationOrder(order, true);
            return;
        }

        // Add to pending if status is confirmed
        if (order.status === 'confirmed') {
            this.orders.pending.unshift(order);
            this.renderColumn('pending');
            this.flashColumn('pending');
        }
    }

    handleOrderStatusChanged(data) {
        const order = data.order;
        if (this.stationId) {
            this.upsertStationOrder(order);
            return;
        }
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
        if (this.stationId) {
            this.upsertStationOrder(order, true);
            return;
        }

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
        // kf-tag variants from static/css/theme.css
        const colors = {
            'low': 'o',
            'normal': 's',
            'high': 'y',
            'rush': 'r animate-pulse'
        };
        return colors[priority] || colors['normal'];
    }

    escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    getOrderCardHtml(order, column) {
        const priorityClass = order.ticket ? this.getPriorityColor(order.ticket.priority) : '';
        const priorityLabel = order.ticket?.priority?.toUpperCase() || 'NORMAL';
        const elapsed = this.getElapsedTime(order.created_at);

        // Station view: only this station's items; All view: station tag per item.
        // Items served in an earlier round are summarised, voided ones crossed out.
        let items = order.items || [];
        if (this.stationId) items = items.filter(i => i.station_id === this.stationId);
        const earlierCount = items.filter(i => i.status === 'served').length;
        items = items.filter(i => i.status !== 'served');
        let otherCount = 0;
        if (this.stationId) {
            otherCount = (order.items || []).filter(i => i.station_id !== this.stationId && i.status !== 'cancelled' && i.status !== 'served').length;
        }
        const showStationTags = this.hasStations && !this.stationId;

        const itemsHtml = items.map(item => `
            <li class="${item.status === 'cancelled' ? 'opacity-60' : ''}">
                <span class="q">${item.quantity}×</span>
                <span class="flex-1 min-w-0 ${item.status === 'cancelled' ? 'line-through' : ''}">
                    ${item.status === 'cancelled' ? '<span class="kf-tag r !py-0 !px-2 !text-[11px] no-underline mr-1">VOID</span>' : ''}${item.name}
                    ${item.variant ? `<small>(${item.variant})</small>` : ''}
                    ${item.special_instructions ? `<em>${item.special_instructions}</em>` : ''}
                </span>
                ${showStationTags && item.station_name ? `<span class="kf-tag ${item.status === 'ready' || item.status === 'served' ? 'g' : 's'} !py-0 !px-2 !text-[11px] flex-none self-start">${this.escapeHtml(item.station_name)}</span>` : ''}
            </li>
        `).join('');
        const otherHtml = (otherCount
            ? `<p class="text-xs text-slate-500 px-1 -mt-1">+${otherCount} item${otherCount === 1 ? '' : 's'} at other stations</p>`
            : '') + (earlierCount
            ? `<p class="text-xs text-slate-500 px-1 -mt-1">${earlierCount} item${earlierCount === 1 ? '' : 's'} served earlier</p>`
            : '');
        const waitingHtml = this.stationId && column === 'ready' && order.status !== 'ready'
            ? '<p class="text-xs text-slate-500 px-1 -mt-1">Waiting on other stations</p>'
            : '';

        const actionsHtml = this.getActionsHtml(order, column);
        const badgeHtml = column === 'ready'
            ? '<span class="kf-tag g">Ready</span>'
            : (order.ticket ? `<span class="kf-tag ${priorityClass}">${priorityLabel}</span>` : '');

        return `
            <div class="kf-kcard order-card" data-order-id="${order.id}">
                <div class="kf-kcard-head">
                    <div>
                        <b>#${order.order_number}</b>
                        <small>${order.table_number ? `Table ${order.table_number}` : 'Takeaway'} · ${elapsed}</small>
                    </div>
                    ${badgeHtml}
                </div>

                <ul class="kf-kcard-items">
                    ${itemsHtml}
                </ul>
                ${otherHtml}

                ${order.kitchen_notes ? `<div class="kf-kcard-note"><strong class="font-medium">Note:</strong> ${order.kitchen_notes}</div>` : ''}
                ${waitingHtml}

                <div class="kf-kcard-actions">
                    ${actionsHtml}
                </div>
            </div>
        `;
    }

    getActionsHtml(order, column) {
        if (column === 'pending') {
            return `
                <button onclick="kitchenManager.startPreparing(${order.id})" class="btn-yellow">
                    Start Preparing
                </button>
                <button onclick="kitchenManager.showPriorityMenu(${order.id})" class="btn-secondary is-narrow">
                    Priority
                </button>
            `;
        } else if (column === 'preparing') {
            return `
                <button onclick="kitchenManager.bumpOrder(${order.id})" class="btn-primary">
                    Bump (Ready)
                </button>
                <button onclick="kitchenManager.showPriorityMenu(${order.id})" class="btn-secondary is-narrow">
                    Priority
                </button>
            `;
        } else if (column === 'ready') {
            // Mark Served posts to the kitchen page itself (same as the server-rendered card)
            const servedHtml = order.status === 'ready' && this.csrfToken ? `
                <form method="POST" action="${window.location.pathname}">
                    <input type="hidden" name="csrfmiddlewaretoken" value="${this.escapeHtml(this.csrfToken)}">
                    <input type="hidden" name="order_id" value="${order.id}">
                    <input type="hidden" name="status" value="served">
                    ${this.stationId ? `<input type="hidden" name="station" value="${this.stationId}">` : ''}
                    <button type="submit" class="btn-primary">
                        Mark Served
                    </button>
                </form>
            ` : '';
            return `
                <button onclick="kitchenManager.recallOrder(${order.id})" class="btn-secondary">
                    Recall
                </button>
                ${servedHtml}
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
            <div class="kf-empty">
                <span class="kf-ic is-soft is-lg">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"
                              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
                    </svg>
                </span>
                <span>${messages[column]}</span>
            </div>
        `;
    }

    // Actions
    startPreparing(orderId) {
        this.ws.startPreparing(orderId, this.stationId);
    }

    bumpOrder(orderId) {
        this.ws.bumpOrder(orderId, this.stationId);
    }

    recallOrder(orderId) {
        this.ws.recallOrder(orderId, this.stationId);
    }

    showPriorityMenu(orderId) {
        const options = [
            { value: 'low', label: 'Low', hint: 'Can wait', tag: 'o' },
            { value: 'normal', label: 'Normal', hint: 'Usual order', tag: 's' },
            { value: 'high', label: 'High', hint: 'Do this next', tag: 'y' },
            { value: 'rush', label: 'Rush', hint: 'Drop everything', tag: 'r' },
        ];
        const card = document.querySelector(`.order-card[data-order-id="${orderId}"]`);
        const orderNo = card?.querySelector('.kf-kcard-head b')?.textContent || '';
        const current = (card?.querySelector('.kf-kcard-head .kf-tag')?.textContent || 'normal').trim().toLowerCase();

        let sheet = document.getElementById('kfPrioritySheet');
        if (!sheet) {
            sheet = document.createElement('div');
            sheet.id = 'kfPrioritySheet';
            sheet.className = 'fixed inset-0 z-50';
            sheet.setAttribute('role', 'dialog');
            sheet.setAttribute('aria-modal', 'true');
            sheet.setAttribute('aria-labelledby', 'kfPriorityTitle');
            sheet.innerHTML = `
                <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" data-close></div>
                <div class="absolute inset-x-0 bottom-0 sm:inset-x-auto sm:bottom-auto sm:left-1/2 sm:top-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:w-[400px] bg-white rounded-t-[28px] sm:rounded-[28px] p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-xl">
                    <h3 id="kfPriorityTitle" class="kf-h">Set priority</h3>
                    <p class="text-sm text-slate-600 mt-1" data-subtitle></p>
                    <div class="grid grid-cols-2 gap-2 mt-4" data-options></div>
                    <button type="button" class="btn-secondary w-full mt-3" data-close>Cancel</button>
                </div>`;
            document.body.appendChild(sheet);
            sheet.querySelectorAll('[data-close]').forEach(el => el.addEventListener('click', () => sheet.classList.add('hidden')));
            document.addEventListener('keydown', e => { if (e.key === 'Escape') sheet.classList.add('hidden'); });
        }

        sheet.querySelector('[data-subtitle]').textContent = orderNo ? `Order ${orderNo}` : '';
        const grid = sheet.querySelector('[data-options]');
        grid.replaceChildren();
        options.forEach(opt => {
            const btn = document.createElement('button');
            btn.type = 'button';
            const isCurrent = opt.value === current;
            btn.className = 'flex flex-col items-start gap-1.5 rounded-2xl p-3 min-h-[76px] text-left transition-colors '
                + (isCurrent ? 'bg-slate-800 text-white' : 'bg-slate-50 hover:bg-slate-100 text-slate-900');
            btn.setAttribute('aria-pressed', isCurrent ? 'true' : 'false');
            const tag = document.createElement('span');
            tag.className = `kf-tag ${opt.tag}`;
            tag.textContent = opt.label;
            const hint = document.createElement('span');
            hint.className = 'text-xs ' + (isCurrent ? 'text-slate-300' : 'text-slate-500');
            hint.textContent = isCurrent ? 'Current' : opt.hint;
            btn.append(tag, hint);
            btn.addEventListener('click', () => {
                sheet.classList.add('hidden');
                if (!isCurrent) this.ws.setPriority(orderId, opt.value);
            });
            grid.appendChild(btn);
        });
        sheet.classList.remove('hidden');
        grid.querySelector('[aria-pressed="true"]')?.focus();
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
