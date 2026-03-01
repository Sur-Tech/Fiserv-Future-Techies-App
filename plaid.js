/**
 * plaid.js — CashLens AI frontend
 * Connects spending-analyzer.html to the Flask backend (transactions.py).
 *
 * Requires: https://cdn.plaid.com/link/v2/stable/link-initialize.js (loaded by the page)
 * Backend must be running at API_BASE (default: http://localhost:5000)
 */

const API_BASE = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? "http://localhost:5000"
  : "";

// State kept in memory for the session
const state = {
  connected: false,
  currentDays: 30,
  offset: 0,
  pageSize: 20,
  totalTransactions: 0,
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function $(id) { return document.getElementById(id); }

function showError(msg) {
  const box = $("error-box");
  if (!box) return;
  box.textContent = msg;
  box.style.display = "block";
}

function clearError() {
  const box = $("error-box");
  if (box) box.style.display = "none";
}

function setStatus(msg, color) {
  const el = $("connect-status");
  if (!el) return;
  el.textContent = msg;
  el.style.color = color || "rgba(250,250,250,0.55)";
}

function show(id)    { const el = $(id); if (el) el.style.display = ""; }
function hide(id)    { const el = $(id); if (el) el.style.display = "none"; }
function showFlex(id){ const el = $(id); if (el) el.style.display = "flex"; }

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function apiFetch(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || "Unknown API error");
  return json.data;          // all backend responses wrap payload in .data
}

// ─── Plaid Link Flow ──────────────────────────────────────────────────────────

async function startPlaidLink() {
  clearError();
  const btn = $("connect-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Connecting…"; }
  setStatus("Getting link token…");

  try {
    const data = await apiFetch("/create_link_token", { method: "POST" });

    // Simulation mode: skip Plaid Link UI entirely
    if (data.simulation_mode) {
      setStatus("Simulation mode — using demo bank data.", "#f59e0b");
      await exchangeToken("fake-public-token");
      return;
    }

    // Real Plaid Link
    const handler = Plaid.create({
      token: data.link_token,
      onSuccess: async (public_token) => {
        setStatus("Authorising…");
        await exchangeToken(public_token);
      },
      onExit: (err) => {
        if (err) {
          showError("Plaid Link closed with error: " + (err.display_message || err.error_message || JSON.stringify(err)));
        } else {
          setStatus("Connection cancelled.", "#888");
        }
        if (btn) { btn.disabled = false; btn.textContent = "Connect Bank via Plaid"; }
      },
    });
    handler.open();

  } catch (err) {
    showError("Could not start Plaid Link: " + err.message);
    setStatus("Failed to connect.", "#ef4444");
    if (btn) { btn.disabled = false; btn.textContent = "Connect Bank via Plaid"; }
  }
}

async function exchangeToken(publicToken) {
  try {
    await apiFetch("/exchange_token", {
      method: "POST",
      body: JSON.stringify({ public_token: publicToken }),
    });
    state.connected = true;
    setStatus("✅ Bank connected!", "#22c55e");

    const btn = $("connect-btn");
    if (btn) { btn.textContent = "✅ Connected"; btn.disabled = true; }

    // Show the full dashboard (filter-section is now inside dashboard)
    show("dashboard");
    hide("connect-area");

    loadTransactions(30);
  } catch (err) {
    showError("Token exchange failed: " + err.message);
    setStatus("Connection failed.", "#ef4444");
    const btn = $("connect-btn");
    if (btn) { btn.disabled = false; btn.textContent = "Connect Bank via Plaid"; }
  }
}

// ─── Sandbox Auto-Connect ─────────────────────────────────────────────────────

async function sandboxInit() {
  try {
    await apiFetch("/sandbox/init", { method: "POST" });
  } catch (_) {
    // silently fall back to demo data
  }
}

// ─── Load Transactions ────────────────────────────────────────────────────────

async function loadTransactions(days) {
  clearError();
  state.currentDays = days;
  state.offset = 0;

  const txList = $("tx-list");
  if (txList) txList.innerHTML = '<p class="sa-loading">Loading transactions…</p>';

  const breakdownBars = $("breakdown-bars");
  if (breakdownBars) breakdownBars.innerHTML = '<p class="sa-loading">Loading categories…</p>';

  try {
    // Auto-connect Plaid sandbox on first load
    if (!state.connected) {
      await sandboxInit();
      state.connected = true;
    }

    const data = await apiFetch(`/transactions?days=${days}&page_size=${state.pageSize}&offset=0`);

    state.totalTransactions = data.total_transactions;
    state.offset = data.transactions.length;

    renderCards(data.stats);
    renderBreakdown(data.stats);
    renderTransactions(data.transactions, false);

    const txTotal = $("tx-total");
    if (txTotal) txTotal.textContent = `${data.total_transactions} total`;

    const loadMoreBtn = $("load-more-btn");
    if (loadMoreBtn) {
      loadMoreBtn.style.display = data.has_more ? "block" : "none";
    }

    // Load AI report and CFO features in the background
    loadReport(days);
    loadRecurring(days);
    loadAnomalies(days);

  } catch (err) {
    showError("Failed to load transactions: " + err.message);
  }
}

async function loadMore() {
  try {
    const data = await apiFetch(
      `/transactions?days=${state.currentDays}&page_size=${state.pageSize}&offset=${state.offset}`
    );
    state.offset += data.transactions.length;
    renderTransactions(data.transactions, true);  // append = true

    const loadMoreBtn = $("load-more-btn");
    if (loadMoreBtn) {
      loadMoreBtn.style.display = data.has_more ? "block" : "none";
    }
  } catch (err) {
    showError("Failed to load more: " + err.message);
  }
}

// ─── Render: Summary Cards ────────────────────────────────────────────────────

function renderCards(stats) {
  if (!stats) return;
  const spent = $("card-spent");
  const avg   = $("card-avg");
  const cat   = $("card-cat");
  const count = $("card-count");

  if (spent) spent.textContent = `$${stats.total_spent.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
  if (avg)   avg.textContent   = `$${stats.avg_daily_spend.toFixed(2)}`;
  if (cat)   cat.textContent   = stats.top_category || "—";
  if (count) count.textContent = stats.transaction_count;
}

// ─── Render: Category Breakdown Bars ─────────────────────────────────────────

function renderBreakdown(stats) {
  if (!stats || !stats.category_breakdown) return;
  const container = $("breakdown-bars");
  if (!container) return;

  const entries = Object.entries(stats.category_breakdown).filter(([, v]) => v > 0);
  if (!entries.length) {
    container.innerHTML = '<p class="sa-loading">No category data available.</p>';
    return;
  }

  const max    = Math.max(...entries.map(([, v]) => v));
  const colors = ["#f43f5e", "#f59e0b", "#0ea5e9", "#a78bfa", "#22c55e", "#fb923c", "#38bdf8", "#e879f9"];

  container.innerHTML = entries.map(([cat, amt], i) => {
    const pct   = max > 0 ? Math.round((amt / max) * 100) : 0;
    const color = colors[i % colors.length];
    return `
      <div class="cat-bar-row">
        <div class="cat-bar-header">
          <span>${escHtml(cat)}</span>
          <span class="cat-bar-amount" style="color:${color};">$${amt.toFixed(2)}</span>
        </div>
        <div class="cat-bar-track">
          <div class="cat-bar-fill" style="width:${pct}%; background:${color};"></div>
        </div>
      </div>`;
  }).join("");
}

// ─── Render: Transactions ─────────────────────────────────────────────────────

function renderTransactions(transactions, append) {
  const container = $("tx-list");
  if (!container) return;

  if (!transactions.length && !append) {
    container.innerHTML = '<p class="sa-loading">No transactions found.</p>';
    return;
  }

  const rows = transactions.map(tx => {
    const amount  = parseFloat(tx.amount || 0);
    const isDebit = amount > 0;
    const sign    = isDebit ? "-" : "+";
    const cls     = isDebit ? "tx-debit" : "tx-credit";
    const cat     = Array.isArray(tx.category) ? tx.category[0] : (tx.category || "Other");
    const pending = tx.pending
      ? '<span class="tx-pending">Pending</span>'
      : "";

    return `
      <div class="tx-row">
        <div class="tx-info">
          <div class="tx-merchant">${escHtml(tx.merchant_name || tx.name || "Unknown")}${pending}</div>
          <div class="tx-meta">${escHtml(cat)} &middot; ${escHtml(tx.date)}</div>
        </div>
        <div class="tx-amount ${cls}">${sign}$${Math.abs(amount).toFixed(2)}</div>
      </div>`;
  }).join("");

  if (append) {
    container.insertAdjacentHTML("beforeend", rows);
  } else {
    container.innerHTML = rows;
  }
}

// ─── AI Report ───────────────────────────────────────────────────────────────

async function loadReport(days) {
  const list = $("recs-list");
  if (!list) return;

  list.innerHTML = '<p class="sa-loading">Generating AI report…</p>';

  try {
    const data = await apiFetch(`/report?days=${days}`);
    list.innerHTML = `<div class="ai-report-text">${escHtml(data.report)}</div>`;
  } catch (err) {
    list.innerHTML = `<p style="color:#f43f5e;font-size:13px;">Could not load AI report: ${escHtml(err.message)}</p>`;
  }
}

// ─── Recurring Transactions ───────────────────────────────────────────────────

async function loadRecurring(days) {
  const list = $("recurring-list");
  if (!list) return;

  list.innerHTML = '<p class="sa-loading">Detecting recurring transactions…</p>';

  try {
    const data = await apiFetch(`/recurring?days=${Math.max(days, 60)}`);
    if (!data.recurring.length) {
      list.innerHTML = '<p class="sa-loading">No recurring transactions detected.</p>';
      return;
    }
    list.innerHTML = data.recurring.map(r => `
      <div class="recurring-row">
        <div class="rec-info">
          <div class="rec-name">
            ${escHtml(r.merchant)}
            ${r.is_subscription ? '<span class="rec-badge-sub">Subscription</span>' : ""}
          </div>
          <div class="rec-meta">${escHtml(r.category)} &middot; ${r.count}× seen &middot; ${r.months_seen.join(", ")}</div>
        </div>
        <div class="rec-amount">~$${r.avg_amount.toFixed(2)}/mo</div>
      </div>`).join("");
  } catch (err) {
    list.innerHTML = `<p style="color:#f43f5e;font-size:13px;">Could not load recurring: ${escHtml(err.message)}</p>`;
  }
}

// ─── Anomalies ────────────────────────────────────────────────────────────────

async function loadAnomalies(days) {
  const list = $("anomalies-list");
  if (!list) return;

  list.innerHTML = '<p class="sa-loading">Scanning for anomalies…</p>';

  try {
    const data = await apiFetch(`/anomalies?days=${days}`);
    if (!data.anomalies.length) {
      list.innerHTML = '<p class="sa-loading">No spending anomalies detected. 🎉</p>';
      return;
    }
    list.innerHTML = data.anomalies.map(a => `
      <div class="anomaly-row">
        <div class="anomaly-info">
          <div class="anomaly-name">${escHtml(a.merchant)} — $${a.amount.toFixed(2)}</div>
          <div class="anomaly-flag">${escHtml(a.flag)} &middot; ${escHtml(a.date)}</div>
        </div>
        <div class="anomaly-ratio">${a.ratio}×</div>
      </div>`).join("");
  } catch (err) {
    list.innerHTML = `<p style="color:#f43f5e;font-size:13px;">Could not load anomalies: ${escHtml(err.message)}</p>`;
  }
}

// ─── AI Chat ──────────────────────────────────────────────────────────────────

async function sendChat() {
  const input  = $("chat-input");
  const output = $("chat-output");
  if (!input || !output) return;

  const message = input.value.trim();
  if (!message) return;

  input.disabled = true;

  // User bubble
  output.insertAdjacentHTML("beforeend", `
    <div class="chat-msg-user">${escHtml(message)}</div>`);

  // Thinking indicator
  output.insertAdjacentHTML("beforeend", `
    <div class="chat-msg-thinking" id="chat-thinking">Domus is thinking…</div>`);

  input.value = "";
  output.scrollTop = output.scrollHeight;

  try {
    const data = await apiFetch("/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    $("chat-thinking")?.remove();
    output.insertAdjacentHTML("beforeend", `
      <div class="chat-msg-ai">${escHtml(data.reply)}</div>`);
  } catch (err) {
    $("chat-thinking")?.remove();
    output.insertAdjacentHTML("beforeend", `
      <div class="chat-msg-ai" style="color:#f87171;">Error: ${escHtml(err.message)}</div>`);
  } finally {
    input.disabled = false;
    input.focus();
    output.scrollTop = output.scrollHeight;
  }
}

// Allow pressing Enter to send chat
document.addEventListener("DOMContentLoaded", () => {
  const input = $("chat-input");
  if (input) {
    input.addEventListener("keydown", e => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
  }
});
