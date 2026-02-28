/**
 * plaid.js — CashLens AI frontend
 * Connects spending-analyzer.html to the Flask backend (transactions.py).
 *
 * Requires: https://cdn.plaid.com/link/v2/stable/link-initialize.js (loaded by the page)
 * Backend must be running at API_BASE (default: http://localhost:5000)
 */

const API_BASE = "http://localhost:5000";

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
  el.style.color = color || "#888";
}

function show(id)    { const el = $(id); if (el) el.style.display = ""; }
function hide(id)    { const el = $(id); if (el) el.style.display = "none"; }
function showFlex(id){ const el = $(id); if (el) el.style.display = "flex"; }

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
      setStatus("Simulation mode — using fake bank data.", "#f59e0b");
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
        if (err) showError("Plaid Link closed with error: " + (err.display_message || err.error_message || JSON.stringify(err)));
        else setStatus("Connection cancelled.", "#888");
        if (btn) { btn.disabled = false; btn.textContent = "🏦 Connect Bank via Plaid"; }
      },
    });
    handler.open();

  } catch (err) {
    showError("Could not start Plaid Link: " + err.message);
    setStatus("Failed.", "#ef4444");
    if (btn) { btn.disabled = false; btn.textContent = "🏦 Connect Bank via Plaid"; }
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
    show("filter-section");
    loadTransactions(30);
  } catch (err) {
    showError("Token exchange failed: " + err.message);
    setStatus("Connection failed.", "#ef4444");
    const btn = $("connect-btn");
    if (btn) { btn.disabled = false; btn.textContent = "🏦 Connect Bank via Plaid"; }
  }
}

// ─── Load Transactions ────────────────────────────────────────────────────────

async function loadTransactions(days) {
  clearError();
  state.currentDays = days;
  state.offset = 0;

  const txList = $("tx-list");
  if (txList) txList.innerHTML = "<p style='color:#888;font-size:14px;'>Loading…</p>";

  try {
    const data = await apiFetch(`/transactions?days=${days}&page_size=${state.pageSize}&offset=0`);

    state.totalTransactions = data.total_transactions;
    state.offset = data.transactions.length;

    renderCards(data.stats);
    renderBreakdown(data.stats);
    renderTransactions(data.transactions, false);

    $("tx-total").textContent = `(${data.total_transactions} total)`;
    show("tx-section");
    showFlex("summary-cards");
    show("breakdown-section");

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
  $("card-spent").textContent  = `$${stats.total_spent.toLocaleString("en-US", {minimumFractionDigits:2})}`;
  $("card-avg").textContent    = `$${stats.avg_daily_spend.toFixed(2)}`;
  $("card-cat").textContent    = stats.top_category || "—";
  $("card-count").textContent  = stats.transaction_count;
}

// ─── Render: Category Breakdown Bars ─────────────────────────────────────────

function renderBreakdown(stats) {
  if (!stats || !stats.category_breakdown) return;
  const container = $("breakdown-bars");
  if (!container) return;

  const entries = Object.entries(stats.category_breakdown).filter(([, v]) => v > 0);
  if (!entries.length) { container.innerHTML = "<p style='color:#888'>No data.</p>"; return; }

  const max = Math.max(...entries.map(([, v]) => v));
  const colors = ["#f43f5e","#f59e0b","#0ea5e9","#a78bfa","#22c55e","#fb923c","#38bdf8","#e879f9"];

  container.innerHTML = entries.map(([cat, amt], i) => {
    const pct = max > 0 ? Math.round((amt / max) * 100) : 0;
    const color = colors[i % colors.length];
    return `
      <div style="margin-bottom:10px;">
        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px;">
          <span>${cat}</span>
          <span style="color:${color};font-weight:600;">$${amt.toFixed(2)}</span>
        </div>
        <div style="background:#1e293b;border-radius:4px;height:8px;overflow:hidden;">
          <div style="width:${pct}%;background:${color};height:100%;border-radius:4px;transition:width 0.4s;"></div>
        </div>
      </div>`;
  }).join("");
}

// ─── Render: Transactions Table ───────────────────────────────────────────────

function renderTransactions(transactions, append) {
  const container = $("tx-list");
  if (!container) return;

  const rows = transactions.map(tx => {
    const amount  = parseFloat(tx.amount || 0);
    const color   = amount > 0 ? "#f43f5e" : "#22c55e";
    const sign    = amount > 0 ? "-" : "+";
    const cat     = Array.isArray(tx.category) ? tx.category[0] : (tx.category || "Other");
    const pending = tx.pending ? " <span style='font-size:10px;color:#f59e0b;'>(pending)</span>" : "";
    return `
      <div style="display:flex;justify-content:space-between;align-items:center;
                  padding:10px 14px;border-bottom:1px solid #1e293b;font-size:13px;">
        <div>
          <div style="font-weight:600;">${escHtml(tx.merchant_name || tx.name || "Unknown")}${pending}</div>
          <div style="color:#64748b;font-size:12px;">${escHtml(cat)} · ${tx.date}</div>
        </div>
        <div style="font-weight:700;color:${color};">${sign}$${Math.abs(amount).toFixed(2)}</div>
      </div>`;
  }).join("");

  if (append) {
    container.insertAdjacentHTML("beforeend", rows);
  } else {
    container.innerHTML = rows || "<p style='color:#888;padding:12px;'>No transactions found.</p>";
  }
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ─── AI Report ───────────────────────────────────────────────────────────────

async function loadReport(days) {
  const section = $("recs-section");
  const list    = $("recs-list");
  if (!section || !list) return;

  list.innerHTML = "<p style='color:#888;font-size:13px;'>Generating AI report…</p>";
  show("recs-section");

  try {
    const data = await apiFetch(`/report?days=${days}`);
    list.innerHTML = `
      <div style="background:#0f172a;border:1px solid #1e293b;border-radius:8px;
                  padding:16px;font-size:13px;line-height:1.7;white-space:pre-wrap;">${escHtml(data.report)}</div>`;
  } catch (err) {
    list.innerHTML = `<p style="color:#f43f5e;font-size:13px;">Could not load AI report: ${escHtml(err.message)}</p>`;
  }
}

// ─── Recurring Transactions ───────────────────────────────────────────────────

async function loadRecurring(days) {
  const section = $("recurring-section");
  const list    = $("recurring-list");
  if (!section || !list) return;

  show("recurring-section");
  list.innerHTML = "<p style='color:#888;font-size:13px;'>Detecting recurring transactions…</p>";

  try {
    const data = await apiFetch(`/recurring?days=${Math.max(days, 60)}`);
    if (!data.recurring.length) {
      list.innerHTML = "<p style='color:#888;font-size:13px;'>No recurring transactions detected.</p>";
      return;
    }
    list.innerHTML = data.recurring.map(r => `
      <div style="display:flex;justify-content:space-between;align-items:center;
                  padding:10px 14px;border-bottom:1px solid #1e293b;font-size:13px;">
        <div>
          <div style="font-weight:600;">${escHtml(r.merchant)}
            ${r.is_subscription ? " <span style='font-size:10px;background:#1e3a5f;color:#38bdf8;padding:1px 6px;border-radius:4px;'>SUBSCRIPTION</span>" : ""}
          </div>
          <div style="color:#64748b;font-size:12px;">${escHtml(r.category)} · ${r.count}× seen · months: ${r.months_seen.join(", ")}</div>
        </div>
        <div style="font-weight:700;color:#f59e0b;">~$${r.avg_amount.toFixed(2)}/mo</div>
      </div>`).join("");
  } catch (err) {
    list.innerHTML = `<p style="color:#f43f5e;font-size:13px;">Could not load recurring: ${escHtml(err.message)}</p>`;
  }
}

// ─── Anomalies ────────────────────────────────────────────────────────────────

async function loadAnomalies(days) {
  const section = $("anomalies-section");
  const list    = $("anomalies-list");
  if (!section || !list) return;

  show("anomalies-section");
  list.innerHTML = "<p style='color:#888;font-size:13px;'>Scanning for anomalies…</p>";

  try {
    const data = await apiFetch(`/anomalies?days=${days}`);
    if (!data.anomalies.length) {
      list.innerHTML = "<p style='color:#888;font-size:13px;'>No spending anomalies detected. 🎉</p>";
      return;
    }
    list.innerHTML = data.anomalies.map(a => `
      <div style="display:flex;justify-content:space-between;align-items:center;
                  padding:10px 14px;border-bottom:1px solid #1e293b;font-size:13px;">
        <div>
          <div style="font-weight:600;color:#f43f5e;">${escHtml(a.merchant)} — $${a.amount.toFixed(2)}</div>
          <div style="color:#64748b;font-size:12px;">${escHtml(a.flag)} · ${a.date}</div>
        </div>
        <div style="font-weight:700;color:#ef4444;">${a.ratio}×</div>
      </div>`).join("");
  } catch (err) {
    list.innerHTML = `<p style="color:#f43f5e;font-size:13px;">Could not load anomalies: ${escHtml(err.message)}</p>`;
  }
}

// ─── AI Chat ──────────────────────────────────────────────────────────────────

async function sendChat() {
  const input = $("chat-input");
  const output = $("chat-output");
  if (!input || !output) return;

  const message = input.value.trim();
  if (!message) return;

  input.disabled = true;
  output.insertAdjacentHTML("beforeend", `
    <div style="text-align:right;margin-bottom:8px;">
      <span style="background:#1e3a5f;padding:6px 12px;border-radius:12px;font-size:13px;">${escHtml(message)}</span>
    </div>`);
  output.insertAdjacentHTML("beforeend", `<div id="chat-thinking" style="color:#888;font-size:13px;padding:4px 0;">CashLens AI is thinking…</div>`);
  input.value = "";
  output.scrollTop = output.scrollHeight;

  try {
    const data = await apiFetch("/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    $("chat-thinking")?.remove();
    output.insertAdjacentHTML("beforeend", `
      <div style="margin-bottom:8px;">
        <span style="background:#0f172a;border:1px solid #1e293b;padding:6px 12px;border-radius:12px;font-size:13px;display:inline-block;">${escHtml(data.reply)}</span>
      </div>`);
  } catch (err) {
    $("chat-thinking")?.remove();
    output.insertAdjacentHTML("beforeend", `<div style="color:#f43f5e;font-size:13px;">Error: ${escHtml(err.message)}</div>`);
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
