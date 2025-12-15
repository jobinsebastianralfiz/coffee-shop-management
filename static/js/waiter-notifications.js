/**
 * Waiter Notifications WebSocket Client
 * Handles real-time notifications for waiters (order ready, table assignments, etc.)
 */

class WaiterNotifications {
    constructor(userId, options = {}) {
        this.userId = userId;
        this.wsUrl = options.wsUrl || this.getWebSocketUrl();
        this.reconnectInterval = options.reconnectInterval || 3000;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
        this.reconnectAttempts = 0;
        this.ws = null;
        this.isConnected = false;
        this.audioEnabled = options.audioEnabled !== false;

        // Use shared sound module if available
        this.soundModule = window.notificationSound || null;
        if (this.soundModule) {
            this.soundModule.setEnabled(this.audioEnabled);
        }

        // Event callbacks
        this.onConnect = options.onConnect || (() => {});
        this.onDisconnect = options.onDisconnect || (() => {});
        this.onOrderReady = options.onOrderReady || (() => {});
        this.onTableAssigned = options.onTableAssigned || (() => {});
        this.onNotification = options.onNotification || (() => {});
        this.onError = options.onError || (() => {});
    }

    getWebSocketUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws/waiter/${this.userId}/`;
    }

    connect() {
        if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
            return;
        }

        console.log('Connecting to Waiter WebSocket...');

        try {
            this.ws = new WebSocket(this.wsUrl);

            this.ws.onopen = () => {
                console.log('Waiter WebSocket connected');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.onConnect();
            };

            this.ws.onclose = (event) => {
                console.log('Waiter WebSocket closed:', event.code, event.reason);
                this.isConnected = false;
                this.onDisconnect();
                this.scheduleReconnect();
            };

            this.ws.onerror = (error) => {
                console.error('Waiter WebSocket error:', error);
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

    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);
            console.log('Waiter WebSocket message:', data);

            switch (data.type) {
                case 'connection_established':
                    console.log('Connection confirmed:', data.message);
                    break;

                case 'order_ready':
                    this.handleOrderReady(data);
                    break;

                case 'table_assigned':
                    this.handleTableAssigned(data);
                    break;

                case 'notification':
                    this.handleNotification(data);
                    break;

                default:
                    console.log('Unknown message type:', data.type);
            }
        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    }

    handleOrderReady(data) {
        // Play order ready sound
        this.playSound('orderReady');

        // Show visual notification
        this.showToast({
            title: 'Order Ready!',
            message: data.message || `Order #${data.order_id} for ${data.table || 'Takeaway'} is ready`,
            type: 'success'
        });

        // Browser notification if permitted
        this.showBrowserNotification('Order Ready', data.message || `Order #${data.order_id} is ready for pickup`);

        // Callback
        this.onOrderReady(data);
    }

    handleTableAssigned(data) {
        // Play notification sound
        this.playSound('notification');

        // Show visual notification
        this.showToast({
            title: 'Table Assigned',
            message: data.message || `Table ${data.table} has been assigned to you`,
            type: 'info'
        });

        // Callback
        this.onTableAssigned(data);
    }

    handleNotification(data) {
        // Play sound based on priority
        if (data.priority === 'urgent' || data.priority === 'high') {
            this.playSound('alert');
        } else {
            this.playSound('notification');
        }

        // Show visual notification
        this.showToast({
            title: data.title || 'Notification',
            message: data.message,
            type: data.type || 'info'
        });

        // Browser notification
        this.showBrowserNotification(data.title || 'Notification', data.message);

        // Callback
        this.onNotification(data);
    }

    playSound(soundType) {
        if (!this.audioEnabled) return;

        if (this.soundModule) {
            this.soundModule.playSound(soundType);
        }
    }

    toggleAudio() {
        this.audioEnabled = !this.audioEnabled;
        if (this.soundModule) {
            this.soundModule.setEnabled(this.audioEnabled);
        }
        return this.audioEnabled;
    }

    showToast(options) {
        const { title, message, type = 'info', duration = 5000 } = options;

        // Check if Alpine.js Toast component is available
        if (window.Alpine && window.dispatchEvent) {
            window.dispatchEvent(new CustomEvent('show-toast', {
                detail: { title, message, type, duration }
            }));
            return;
        }

        // Fallback: Create simple toast element
        const toast = document.createElement('div');
        toast.className = `fixed bottom-4 right-4 z-50 p-4 rounded-xl shadow-lg max-w-sm transform translate-y-full transition-transform duration-300`;

        // Set background color based on type
        const colors = {
            success: 'bg-green-500 text-white',
            error: 'bg-red-500 text-white',
            warning: 'bg-amber-500 text-white',
            info: 'bg-blue-500 text-white'
        };
        toast.className += ` ${colors[type] || colors.info}`;

        toast.innerHTML = `
            <div class="font-semibold">${title}</div>
            <div class="text-sm opacity-90 mt-1">${message}</div>
        `;

        document.body.appendChild(toast);

        // Animate in
        requestAnimationFrame(() => {
            toast.classList.remove('translate-y-full');
        });

        // Remove after duration
        setTimeout(() => {
            toast.classList.add('translate-y-full');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    async showBrowserNotification(title, body) {
        if (!('Notification' in window)) return;

        if (Notification.permission === 'granted') {
            new Notification(title, {
                body,
                icon: '/static/images/icon-192x192.png',
                badge: '/static/images/icon-72x72.png',
                vibrate: [200, 100, 200]
            });
        } else if (Notification.permission !== 'denied') {
            const permission = await Notification.requestPermission();
            if (permission === 'granted') {
                this.showBrowserNotification(title, body);
            }
        }
    }

    async requestNotificationPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            return await Notification.requestPermission();
        }
        return Notification.permission;
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WaiterNotifications;
}
