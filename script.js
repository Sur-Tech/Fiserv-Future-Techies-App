/* =============================================
   Fiserv CFO — Main Script
   Behavior Tracker + AI Chat Widget + SPA Navigation
   ============================================= */

'use strict';

// =============================================
// BEHAVIOR TRACKER
// =============================================

const Tracker = {
    KEY: 'fiserv_behavior',

    get() {
        try { return JSON.parse(localStorage.getItem(this.KEY) || '{}'); }
        catch { return {}; }
    },

    save(d) {
        try { localStorage.setItem(this.KEY, JSON.stringify(d)); }
        catch { /* storage full or unavailable */ }
    },

    recordVisit(page) {
        const d = this.get();
        d.pageVisits  = d.pageVisits  || {};
        d.timeSpent   = d.timeSpent   || {};
        d.hourlyHits  = d.hourlyHits  || {};
        d.weekdayHits = d.weekdayHits || {};

        d.pageVisits[page] = (d.pageVisits[page] || 0) + 1;
        d.lastPage         = page;
        d.pageEnterTime    = Date.now();

        const now  = new Date();
        const hour = String(now.getHours());
        const wday = String(now.getDay());
        d.hourlyHits[hour]  = (d.hourlyHits[hour]  || 0) + 1;
        d.weekdayHits[wday] = (d.weekdayHits[wday] || 0) + 1;

        if (!d.firstSeen) d.firstSeen = now.toISOString().slice(0, 10);
        d.lastSeen = now.toISOString().slice(0, 10);

        this.save(d);
        this.updateTabBadges(d);
    },

    recordLeave(page) {
        if (!page || page === 'home') return;
        const d = this.get();
        if (d.pageEnterTime) {
            d.timeSpent = d.timeSpent || {};
            d.timeSpent[page] = (d.timeSpent[page] || 0) + (Date.now() - d.pageEnterTime);
            delete d.pageEnterTime;
            this.save(d);
        }
    },

    recordAction(action) {
        const d = this.get();
        d.actions = d.actions || {};
        d.actions[action] = (d.actions[action] || 0) + 1;
        this.save(d);
    },

    getTopPage() {
        const d = this.get();
        if (!d.pageVisits) return null;
        const entries = Object.entries(d.pageVisits).filter(([p]) => p !== 'home');
        if (!entries.length) return null;
        return entries.sort(([, a], [, b]) => b - a)[0][0];
    },

    /* Short context string injected into AI chat for personalization */
    getContext() {
        const d = this.get();
        if (!d.pageVisits) return '';
        const top   = this.getTopPage();
        const total = Object.values(d.pageVisits).reduce((a, b) => a + b, 0);
        const parts = [];
        if (top)        parts.push(`most visited section: ${top} (${d.pageVisits[top]}x)`);
        if (total)      parts.push(`${total} total page views`);
        if (d.firstSeen) parts.push(`active since ${d.firstSeen}`);
        return parts.length ? `[User context: ${parts.join(', ')}]` : '';
    },

    updateGreeting() {
        const greetingEl = document.getElementById('personalized-greeting');
        if (!greetingEl) return;

        const d = this.get();
        if (!d.sessions || d.sessions < 2) { greetingEl.style.display = 'none'; return; }

        const top  = this.getTopPage();
        const hour = new Date().getHours();
        const timeGreeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

        const textEl   = document.getElementById('greeting-text');
        const actionEl = document.getElementById('greeting-action');

        if (top && textEl && actionEl) {
            const label = top.charAt(0).toUpperCase() + top.slice(1);
            textEl.textContent = `${timeGreeting}! Your top section is ${label}.`;
            actionEl.textContent = `Open ${label} \u2192`;
            actionEl.onclick = (e) => { e.preventDefault(); loadPage(top); };
            greetingEl.style.display = 'flex';
        } else {
            greetingEl.style.display = 'none';
        }
    },

    updateTabBadges(d) {
        if (!d || !d.pageVisits) return;
        document.querySelectorAll('.tab[id]').forEach(tab => {
            const visits = d.pageVisits[tab.id];
            if (visits && visits > 1) {
                tab.dataset.visits = visits;
            } else {
                delete tab.dataset.visits;
            }
        });
    },

    init() {
        const d = this.get();
        d.sessions = (d.sessions || 0) + 1;
        d.lastSeen = new Date().toISOString().slice(0, 10);
        if (!d.firstSeen) d.firstSeen = d.lastSeen;
        this.save(d);
        this.updateGreeting();
        this.updateTabBadges(d);
    }
};


// =============================================
// AI CHAT WIDGET
// =============================================

const ChatWidget = {
    API: (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
        ? 'http://localhost:5000'
        : '',
    HISTORY_KEY: 'chat_history',
    MAX_HISTORY: 50,
    isOpen:      false,
    history:     [],

    init() {
        try {
            this.history = JSON.parse(localStorage.getItem(this.HISTORY_KEY) || '[]');
        } catch { this.history = []; }
        this.renderMessages();
    },

    toggle() {
        this.isOpen = !this.isOpen;
        const panel   = document.getElementById('chat-panel');
        const overlay = document.getElementById('chat-overlay');
        const btn     = document.querySelector('.header-chat-btn');
        if (!panel) return;
        panel.classList.toggle('open', this.isOpen);
        if (overlay) overlay.classList.toggle('open', this.isOpen);
        if (btn)     btn.classList.toggle('active', this.isOpen);

        if (this.isOpen) {
            const input = document.getElementById('chat-input');
            if (input) input.focus();
            this.scrollToBottom();
            if (this.history.length > 0) {
                const chips = document.getElementById('chat-suggestions');
                if (chips) chips.style.display = 'none';
            }
        }
    },

    escHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/\n/g, '<br>');
    },

    addMessage(role, text) {
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        this.history.push({ role, text, time });
        if (this.history.length > this.MAX_HISTORY) this.history.shift();
        try { localStorage.setItem(this.HISTORY_KEY, JSON.stringify(this.history)); }
        catch { /* quota */ }
        this.renderMessages();
    },

    renderMessages() {
        const container = document.getElementById('chat-messages');
        if (!container) return;

        if (!this.history.length) {
            container.innerHTML = `
                <div class="chat-bubble ai">
                    <div class="chat-avatar">🤖</div>
                    <div class="chat-content">
                        <div class="chat-text">Hi! I'm <strong>Domus</strong>, your personal finance assistant.<br><br>
                        Ask me anything about budgeting, spending habits, or saving goals. Use the quick prompts below to get started!</div>
                    </div>
                </div>`;
        } else {
            container.innerHTML = this.history.map(m => {
                const cls    = m.role === 'user' ? 'user' : 'ai';
                const avatar = m.role === 'user' ? '👤' : '🤖';
                return `<div class="chat-bubble ${cls}">
                    <div class="chat-avatar">${avatar}</div>
                    <div class="chat-content">
                        <div class="chat-text">${this.escHtml(m.text)}</div>
                        <div class="chat-time">${m.time || ''}</div>
                    </div>
                </div>`;
            }).join('');
        }

        this.scrollToBottom();
    },

    scrollToBottom() {
        const c = document.getElementById('chat-messages');
        if (c) setTimeout(() => { c.scrollTop = c.scrollHeight; }, 50);
    },

    setTyping(show) {
        const typingEl = document.getElementById('chat-typing');
        const sendBtn  = document.getElementById('chat-send-btn');
        const statusEl = document.getElementById('chat-status');

        if (typingEl) typingEl.style.display = show ? 'flex' : 'none';
        if (sendBtn)  sendBtn.disabled = show;
        if (statusEl) statusEl.textContent = show ? '\u25cf Thinking\u2026' : '\u25cf Ready';
    },

    async send() {
        const input = document.getElementById('chat-input');
        if (!input) return;
        const msg = input.value.trim();
        if (!msg) return;
        input.value = '';

        const chips = document.getElementById('chat-suggestions');
        if (chips) chips.style.display = 'none';

        this.addMessage('user', msg);
        this.setTyping(true);

        try {
            const ctx     = Tracker.getContext();
            const payload = { message: ctx ? `${msg}\n\n${ctx}` : msg };

            const res = await fetch(`${this.API}/chat`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(payload)
            });

            this.setTyping(false);

            const json = await res.json().catch(() => ({}));
            if (res.ok && json.success) {
                this.addMessage('ai', (json.data && json.data.reply) || 'I received an empty response. Please try again.');
            } else if (res.status === 400) {
                this.addMessage('ai', json.error || 'Your message could not be processed. Try rephrasing it.');
            } else {
                this.addMessage('ai', json.error || `Server error (${res.status}). The backend may need attention.`);
            }
        } catch {
            this.setTyping(false);
            this.addMessage('ai',
                'Could not reach the AI backend.\n\nMake sure the backend server is running:\npython transactions.py'
            );
        }
    },

    quickSend(prompt) {
        const input = document.getElementById('chat-input');
        if (input) {
            input.value = prompt;
            this.send();
        }
    },

    clearHistory() {
        this.history = [];
        try { localStorage.removeItem(this.HISTORY_KEY); } catch { /* */ }
        this.renderMessages();
        const chips = document.getElementById('chat-suggestions');
        if (chips) chips.style.display = 'flex';
    }
};


// =============================================
// SPA NAVIGATION
// =============================================

let _currentPage = 'home';

function loadPage(page) {
    // Record time spent on the page being left
    Tracker.recordLeave(_currentPage);

    // Update active tab highlight
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    const activeTab = document.getElementById(page);
    if (activeTab) activeTab.classList.add('active');

    // spending-analyzer has its own Plaid scripts — navigate directly
    if (page === 'spending-analyzer') {
        Tracker.recordVisit(page);
        _currentPage = page;
        window.location.href = 'spending-analyzer.html';
        return;
    }

    const main = document.querySelector('main');
    if (!main) return;

    // Hide home-only sections (mission + features) when on a sub-page
    document.querySelectorAll('.home-only').forEach(el => {
        el.style.display = (page === 'home') ? '' : 'none';
    });

    const routes = {
        home:      'index.html',
        banks:     'banks.html',
        groceries: 'groceries.html',
        school:    'school.html',
        utilities: 'utilities.html',
        work:      'work.html'
    };

    const target = routes[page];
    if (!target) {
        main.innerHTML = "<p style='padding:60px;text-align:center;color:var(--gray-500);font-size:16px'>Page not found.</p>";
        return;
    }

    // Fade out
    main.style.transition = 'opacity 0.18s ease';
    main.style.opacity = '0.35';

    fetch(target)
        .then(res => {
            if (!res.ok) throw new Error('Fetch failed: ' + res.status);
            return res.text();
        })
        .then(html => {
            const doc       = new DOMParser().parseFromString(html, 'text/html');
            const innerMain = doc.querySelector('main');
            main.innerHTML  = innerMain ? innerMain.innerHTML : html;

            if (page === 'home') Tracker.updateGreeting();

            requestAnimationFrame(() => { main.style.opacity = '1'; });

            const titleEl = doc.querySelector('title');
            if (titleEl) document.title = titleEl.textContent;

            window.scrollTo({ top: 0, behavior: 'smooth' });

            _currentPage = page;
            Tracker.recordVisit(page);
            VoiceReminder.onPageLoad(page);
        })
        .catch(err => {
            console.error('loadPage error:', err);
            main.style.opacity = '1';
            main.innerHTML = `
                <div style="padding:60px;text-align:center">
                    <div style="font-size:48px;margin-bottom:16px">&#128533;</div>
                    <p style="color:#DC2626;font-size:16px;font-weight:600">Failed to load page.</p>
                    <p style="color:var(--gray-500);margin-top:8px">Please check the server is running and try again.</p>
                </div>`;
        });
}


// =============================================
// VOICE REMINDER (Web Speech API)
// =============================================

const VoiceReminder = {
    KEY: 'domus_voice',

    isEnabled() {
        return localStorage.getItem(this.KEY) !== 'off';
    },

    toggle() {
        const nowEnabled = !this.isEnabled();
        localStorage.setItem(this.KEY, nowEnabled ? 'on' : 'off');
        this.updateUI();
        if (nowEnabled) {
            this.speak('Voice reminders enabled. I will keep you updated.');
        }
    },

    speak(text, rate, pitch) {
        if (!this.isEnabled() || !window.speechSynthesis) return;
        window.speechSynthesis.cancel();
        const utt = new SpeechSynthesisUtterance(text);
        utt.rate   = rate  || 0.93;
        utt.pitch  = pitch || 1.0;
        utt.volume = 0.88;

        const setVoice = () => {
            const voices = speechSynthesis.getVoices();
            const v = voices.find(v =>
                /Samantha|Google US English|Google UK English Female/i.test(v.name)
            ) || voices.find(v => v.lang && v.lang.startsWith('en')) || null;
            if (v) utt.voice = v;
            speechSynthesis.speak(utt);
        };

        // Chrome loads voices asynchronously
        if (speechSynthesis.getVoices().length > 0) {
            setVoice();
        } else {
            speechSynthesis.onvoiceschanged = () => { setVoice(); speechSynthesis.onvoiceschanged = null; };
        }
    },

    greet() {
        if (!this.isEnabled()) return;
        const hour = new Date().getHours();
        const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
        const top = Tracker.getTopPage();
        const msg = top
            ? `${greeting}! Welcome to Domus. Your most visited section is ${top}.`
            : `${greeting}! Welcome to Domus, your personal finance assistant.`;
        this.speak(msg);
    },

    remindBills() {
        // Read bill cards already rendered in the DOM
        const bills = document.querySelectorAll('.bill-card');
        const dueSoon = [];
        bills.forEach(card => {
            const badge = card.querySelector('.badge-red, .badge-orange');
            if (!badge) return;
            const name   = card.querySelector('.bill-name')?.textContent?.trim() || 'a bill';
            const amount = card.querySelector('.bill-amount')?.textContent?.trim() || '';
            dueSoon.push(`${name}${amount ? ' for ' + amount : ''}`);
        });

        if (!dueSoon.length) {
            this.speak('Your bills are all up to date. No urgent payments this week.');
        } else if (dueSoon.length === 1) {
            this.speak(`Reminder: ${dueSoon[0]} is due soon.`);
        } else {
            this.speak(`You have ${dueSoon.length} bills due soon: ${dueSoon.join(', ')}.`);
        }
    },

    onPageLoad(page) {
        if (!this.isEnabled()) return;
        const msgs = {
            banks:     "You're viewing your bank accounts. Total balance is sixty-nine thousand dollars.",
            groceries: "Grocery budget check. You have two hundred and thirteen dollars remaining this month.",
            school:    "Education update. Your next tuition payment of six thousand dollars is due soon.",
            work:      "Work finances. Monthly income is eighty-five hundred dollars. Net after expenses is seventy-two fifty-three."
        };
        if (page === 'utilities') {
            setTimeout(() => this.remindBills(), 700);
        } else if (msgs[page]) {
            this.speak(msgs[page]);
        }
    },

    updateUI() {
        const btn = document.getElementById('voice-btn');
        if (!btn) return;
        const on = this.isEnabled();
        btn.textContent = on ? '\uD83D\uDD0A' : '\uD83D\uDD07';
        btn.title       = on ? 'Voice ON \u2014 click to mute' : 'Voice OFF \u2014 click to enable';
        btn.classList.toggle('muted', !on);
    },

    init() {
        this.updateUI();
    }
};


// =============================================
// TOAST NOTIFICATIONS
// =============================================

function showToast(msg, type = 'info', duration = 3200) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const icons = { success: '✅', info: 'ℹ️', error: '❌', warning: '⚠️' };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span class="toast-icon">${icons[type] || '💬'}</span><span class="toast-text">${msg}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'toastOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}


// =============================================
// TRANSFER MODAL (placeholder)
// =============================================

const TransferModal = {
    open() {
        const modal = document.getElementById('transfer-modal');
        if (!modal) return;
        this.reset();
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
        const firstInput = modal.querySelector('input, select');
        if (firstInput) setTimeout(() => firstInput.focus(), 300);
    },

    close() {
        const modal = document.getElementById('transfer-modal');
        if (!modal) return;
        modal.classList.remove('open');
        document.body.style.overflow = '';
    },

    submit() {
        const from   = document.getElementById('transfer-from')?.value;
        const to     = document.getElementById('transfer-to')?.value?.trim();
        const amount = document.getElementById('transfer-amount')?.value;

        if (!from || !to || !amount || parseFloat(amount) <= 0) {
            // Shake the submit button visually
            const btn = document.querySelector('.modal-submit');
            if (btn) {
                btn.style.animation = 'shake 0.4s ease';
                setTimeout(() => { btn.style.animation = ''; }, 500);
            }
            return;
        }

        // Show success state
        const form    = document.getElementById('transfer-form');
        const success = document.getElementById('transfer-success');
        const amt     = parseFloat(amount).toFixed(2);
        if (form)    form.style.display    = 'none';
        if (success) success.style.display = 'flex';

        const successAmt = document.getElementById('transfer-success-amount');
        if (successAmt) successAmt.textContent = `$${amt} to ${to}`;

        VoiceReminder.speak(`Transfer of ${amt} dollars to ${to} submitted successfully.`);

        setTimeout(() => this.close(), 2800);
    },

    reset() {
        const form    = document.getElementById('transfer-form');
        const success = document.getElementById('transfer-success');
        if (form)    form.style.display    = '';
        if (success) success.style.display = 'none';
        ['transfer-to', 'transfer-amount', 'transfer-note'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        const sel = document.getElementById('transfer-from');
        if (sel) sel.selectedIndex = 0;
    }
};


// =============================================
// INIT ON DOM READY
// =============================================

function injectChatWidget() {
    if (document.getElementById('chat-panel')) return; // already in HTML
    const wrap = document.createElement('div');
    wrap.id = 'chat-widget';
    wrap.innerHTML = `
        <div class="chat-overlay" id="chat-overlay" onclick="ChatWidget.toggle()"></div>
        <div class="chat-panel" id="chat-panel">
            <div class="chat-panel-header">
                <div class="chat-panel-title">
                    <div class="chat-bot-avatar">🤖</div>
                    <div>
                        <div class="chat-panel-name">Domus</div>
                        <div class="chat-panel-status" id="chat-status">● Ready</div>
                    </div>
                </div>
                <div class="chat-header-actions">
                    <button class="chat-clear-btn" onclick="ChatWidget.clearHistory()" title="Clear">🗑</button>
                    <button class="chat-close-btn" onclick="ChatWidget.toggle()" title="Close">✕</button>
                </div>
            </div>
            <div class="chat-messages" id="chat-messages"></div>
            <div id="chat-typing" class="chat-typing" style="display:none">
                <div class="chat-typing-bubble"><span></span><span></span><span></span></div>
                <div class="chat-typing-label">Domus is thinking…</div>
            </div>
            <div class="chat-suggestions" id="chat-suggestions">
                <button class="chat-chip" onclick="ChatWidget.quickSend('How am I doing with my budget?')">📊 Budget</button>
                <button class="chat-chip" onclick="ChatWidget.quickSend('Where am I spending the most?')">💸 Top spending</button>
                <button class="chat-chip" onclick="ChatWidget.quickSend('Give me savings tips')">💡 Tips</button>
            </div>
            <div class="chat-input-row">
                <input id="chat-input" class="chat-input" type="text" placeholder="Ask about your finances…" maxlength="500"
                    onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();ChatWidget.send();}">
                <button class="chat-send-btn" id="chat-send-btn" onclick="ChatWidget.send()">➤</button>
            </div>
        </div>`;
    document.body.appendChild(wrap);
}

// =============================================
// THEME TOGGLE (dark / light mode)
// =============================================

const ThemeToggle = {
    KEY: 'domus_theme',

    init() {
        const saved = localStorage.getItem(this.KEY) || 'light';
        document.documentElement.setAttribute('data-theme', saved);
        this._updateBtn(saved);
    },

    toggle() {
        const current = document.documentElement.getAttribute('data-theme') || 'light';
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem(this.KEY, next);
        this._updateBtn(next);
    },

    _updateBtn(theme) {
        const btn = document.getElementById('theme-btn');
        if (!btn) return;
        if (theme === 'dark') {
            btn.textContent = '☀️';
            btn.title = 'Switch to light mode';
        } else {
            btn.textContent = '🌙';
            btn.title = 'Switch to dark mode';
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    injectChatWidget();
    ThemeToggle.init();
    Tracker.init();
    ChatWidget.init();
    VoiceReminder.init();
    setTimeout(() => VoiceReminder.greet(), 1200);
});
