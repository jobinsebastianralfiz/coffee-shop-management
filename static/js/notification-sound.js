/**
 * Notification Sound Module
 * Reusable sound notification system for the Coffee Shop app
 *
 * Sound Types:
 * - newOrder: Standard beep (800Hz, 0.5s) - For new orders in kitchen
 * - orderReady: Double beep (600Hz, 0.3s x2) - For waiter when order is ready
 * - rushOrder: Triple beep (1000Hz, 0.2s x3) - Urgent orders
 */

class NotificationSound {
    constructor(options = {}) {
        this.enabled = options.enabled !== false;
        this.volume = options.volume || 0.3;
        this.audioContext = null;

        // Sound definitions
        this.sounds = {
            newOrder: {
                frequency: 800,
                duration: 0.5,
                repeat: 1,
                interval: 0,
                type: 'sine'
            },
            orderReady: {
                frequency: 600,
                duration: 0.3,
                repeat: 2,
                interval: 0.2,
                type: 'sine'
            },
            rushOrder: {
                frequency: 1000,
                duration: 0.2,
                repeat: 3,
                interval: 0.15,
                type: 'square'
            },
            notification: {
                frequency: 700,
                duration: 0.3,
                repeat: 1,
                interval: 0,
                type: 'sine'
            },
            alert: {
                frequency: 900,
                duration: 0.4,
                repeat: 2,
                interval: 0.1,
                type: 'triangle'
            }
        };

        this.initAudio();
    }

    initAudio() {
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        } catch (e) {
            console.warn('NotificationSound: Audio context not available:', e);
            this.enabled = false;
        }
    }

    /**
     * Resume audio context (required after user interaction)
     */
    async resume() {
        if (this.audioContext && this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
        }
    }

    /**
     * Play a single beep
     * @param {number} frequency - Frequency in Hz
     * @param {number} duration - Duration in seconds
     * @param {string} type - Oscillator type (sine, square, triangle, sawtooth)
     */
    playBeep(frequency, duration, type = 'sine') {
        if (!this.enabled || !this.audioContext) return Promise.resolve();

        return new Promise((resolve) => {
            try {
                const oscillator = this.audioContext.createOscillator();
                const gainNode = this.audioContext.createGain();

                oscillator.connect(gainNode);
                gainNode.connect(this.audioContext.destination);

                oscillator.frequency.value = frequency;
                oscillator.type = type;

                const currentTime = this.audioContext.currentTime;
                gainNode.gain.setValueAtTime(this.volume, currentTime);
                gainNode.gain.exponentialRampToValueAtTime(0.01, currentTime + duration);

                oscillator.start(currentTime);
                oscillator.stop(currentTime + duration);

                oscillator.onended = resolve;
            } catch (e) {
                console.warn('NotificationSound: Could not play beep:', e);
                resolve();
            }
        });
    }

    /**
     * Play a notification sound by type
     * @param {string} soundType - Type of sound (newOrder, orderReady, rushOrder, notification, alert)
     */
    async playSound(soundType) {
        if (!this.enabled || !this.audioContext) return;

        // Resume context if suspended (browser autoplay policy)
        await this.resume();

        const sound = this.sounds[soundType] || this.sounds.notification;

        for (let i = 0; i < sound.repeat; i++) {
            await this.playBeep(sound.frequency, sound.duration, sound.type);

            // Wait for interval between repeats
            if (i < sound.repeat - 1 && sound.interval > 0) {
                await new Promise(resolve => setTimeout(resolve, sound.interval * 1000));
            }
        }
    }

    /**
     * Play new order sound (single beep)
     */
    playNewOrder() {
        return this.playSound('newOrder');
    }

    /**
     * Play order ready sound (double beep)
     */
    playOrderReady() {
        return this.playSound('orderReady');
    }

    /**
     * Play rush order sound (triple beep, higher pitch)
     */
    playRushOrder() {
        return this.playSound('rushOrder');
    }

    /**
     * Play general notification sound
     */
    playNotification() {
        return this.playSound('notification');
    }

    /**
     * Play alert sound
     */
    playAlert() {
        return this.playSound('alert');
    }

    /**
     * Enable or disable sound
     * @param {boolean} enabled
     */
    setEnabled(enabled) {
        this.enabled = enabled;
    }

    /**
     * Set volume (0-1)
     * @param {number} volume
     */
    setVolume(volume) {
        this.volume = Math.max(0, Math.min(1, volume));
    }

    /**
     * Check if sound is enabled
     */
    isEnabled() {
        return this.enabled && this.audioContext !== null;
    }

    /**
     * Add a custom sound type
     * @param {string} name - Sound name
     * @param {object} config - Sound configuration
     */
    addSound(name, config) {
        this.sounds[name] = {
            frequency: config.frequency || 800,
            duration: config.duration || 0.5,
            repeat: config.repeat || 1,
            interval: config.interval || 0,
            type: config.type || 'sine'
        };
    }
}

// Create global instance
window.notificationSound = new NotificationSound();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = NotificationSound;
}
