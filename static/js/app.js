/**
 * Apex Global Trust Bank - Client Application Logic
 */

// Application State
const state = {
  token: null,
  user: null,
  role: "user", // 'admin' or 'user'
  bankInfo: null,
  userAccount: null,
  userTransactions: [],
  userTxFilter: "all",
  adminAccounts: [],
  adminTransactions: [],
  adminTxFilter: "all",
};

// Animated Themes
const THEMES = [
  { id: "cyber", name: "Cyber Midnight", icon: "🌌" },
  { id: "aurora", name: "Emerald Aurora", icon: "💎" },
  { id: "neon", name: "Neon Royale", icon: "🔮" },
  { id: "gold", name: "Imperial Gold", icon: "✨" },
];
let currentThemeIdx = 0;

function applyAnimationTheme(themeId) {
  const theme = THEMES.find((t) => t.id === themeId) || THEMES[0];
  currentThemeIdx = THEMES.indexOf(theme);
  if (theme.id === "cyber") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", theme.id);
  }
  const label = document.getElementById("current-theme-name");
  const icon = document.querySelector(".theme-icon");
  if (label) label.textContent = theme.name;
  if (icon) icon.textContent = theme.icon;
  localStorage.setItem("apex_animated_theme", theme.id);
}

function cycleAnimationTheme() {
  currentThemeIdx = (currentThemeIdx + 1) % THEMES.length;
  const nextTheme = THEMES[currentThemeIdx];
  applyAnimationTheme(nextTheme.id);
  showToast(`Switched Theme: ${nextTheme.name}`, "info");
}

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", async () => {
  await fetchBankInfo();

  // Always open on the login authentication screen first
  localStorage.removeItem("apex_token");
  state.token = null;
  state.user = null;
  updateNavUser();
  showView("auth");

  // Load and apply saved animated theme
  const savedTheme = localStorage.getItem("apex_animated_theme") || "cyber";
  applyAnimationTheme(savedTheme);

  // Attach logout listener
  document.getElementById("logout-btn").addEventListener("click", handleLogout);

  // Brand click returns to appropriate view or login
  document.getElementById("nav-brand-btn").addEventListener("click", () => {
    if (!state.user) {
      showView("auth");
    } else if (state.role === "admin") {
      showView("admin");
    } else {
      showView("user");
    }
  });

  // Close modals on clicking outside modal dialog
  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) {
        backdrop.classList.remove("active");
      }
    });
  });
});

// --- API HELPER ---
async function apiRequest(endpoint, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }

  try {
    const res = await fetch(endpoint, { credentials: "include", ...options, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "Request failed");
    }
    return data;
  } catch (err) {
    throw err;
  }
}

// --- AUTHENTICATION LOGIC ---
async function checkExistingSession() {
  if (!state.token) {
    showView("auth");
    return;
  }

  try {
    const res = await apiRequest("/api/auth/me");
    state.user = res.user;
    state.role = res.user.role;
    updateNavUser();
    if (state.role === "admin") {
      showView("admin");
      loadAdminDashboard();
    } else {
      showView("user");
      loadUserDashboard();
    }
  } catch (err) {
    // Invalid/expired token
    state.token = null;
    localStorage.removeItem("apex_token");
    showView("auth");
  }
}

function switchLoginRole(role) {
  const userTab = document.getElementById("tab-login-user");
  const adminTab = document.getElementById("tab-login-admin");
  const title = document.getElementById("login-role-title");
  const sub = document.getElementById("login-role-subtitle");
  const usernameInput = document.getElementById("login-username");

  if (role === "admin") {
    userTab.classList.remove("active");
    adminTab.classList.add("active");
    title.textContent = "Administrative Gateway";
    sub.textContent = "Vault reserve management, customer audits & node parameters";
    usernameInput.placeholder = "e.g. admin";
  } else {
    adminTab.classList.remove("active");
    userTab.classList.add("active");
    title.textContent = "Customer Sign In";
    sub.textContent = "Access your digital accounts, transactions and transfers";
    usernameInput.placeholder = "e.g. john_doe or sarah_smith";
  }
}

async function handleLoginSubmit(event) {
  event.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  const submitBtn = document.getElementById("login-submit-btn");

  if (!username || !password) {
    showToast("Please enter username and password", "error");
    return;
  }

  submitBtn.disabled = true;
  submitBtn.innerHTML = "Authenticating...";

  try {
    const res = await apiRequest("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });

    state.token = res.token;
    localStorage.setItem("apex_token", res.token);
    state.user = res.user;
    state.role = res.user.role;

    showToast(`Welcome back, ${res.user.full_name}`, "success");
    updateNavUser();

    if (state.role === "admin") {
      showView("admin");
      loadAdminDashboard();
    } else {
      showView("user");
      loadUserDashboard();
    }
  } catch (err) {
    showToast(err.message || "Authentication failed", "error");
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>Sign In Securely</span>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
      </svg>`;
  }
}

async function quickLogin(username, password) {
  document.getElementById("login-username").value = username;
  document.getElementById("login-password").value = password;
  if (username === "admin") {
    switchLoginRole("admin");
  } else {
    switchLoginRole("user");
  }
  const fakeEvent = { preventDefault: () => {} };
  await handleLoginSubmit(fakeEvent);
}

async function handleLogout() {
  try {
    await apiRequest("/api/auth/logout", { method: "POST" });
  } catch (e) {
    // Continue cleanup even if server error
  }
  state.token = null;
  state.user = null;
  localStorage.removeItem("apex_token");
  updateNavUser();
  showView("auth");
  showToast("You have been signed out successfully", "info");
}

function updateNavUser() {
  const profilePill = document.getElementById("user-profile-pill");
  if (!state.user) {
    profilePill.classList.add("hidden");
    return;
  }

  profilePill.classList.remove("hidden");
  document.getElementById("nav-user-name").textContent = state.user.full_name;
  document.getElementById("nav-user-role").textContent = state.user.role.toUpperCase();

  // Initials
  const parts = state.user.full_name.split(" ");
  const initials = parts.length > 1 ? (parts[0][0] + parts[1][0]).toUpperCase() : parts[0].substring(0, 2).toUpperCase();
  document.getElementById("nav-user-avatar").textContent = initials;
}

function showView(viewName) {
  document.querySelectorAll(".view-section").forEach((sec) => sec.classList.remove("active"));
  const target = document.getElementById(`view-${viewName}`);
  if (target) {
    target.classList.add("active");
  }
}

function togglePasswordVisibility(inputId) {
  const input = document.getElementById(inputId);
  if (input.type === "password") {
    input.type = "text";
  } else {
    input.type = "password";
  }
}

// --- BANK DETAILS ---
async function fetchBankInfo() {
  try {
    const data = await apiRequest("/api/bank/info");
    state.bankInfo = data;

    // Update navigation and public specs
    document.getElementById("nav-branch-name").textContent = data.branch_name;
    document.getElementById("auth-spec-ifsc").textContent = data.ifsc_code;
    document.getElementById("auth-spec-swift").textContent = data.swift_code;
    document.getElementById("auth-spec-routing").textContent = data.routing_number;
    document.getElementById("auth-spec-reserve").textContent = `${data.reserve_ratio}%`;

    // Populate in Admin Bank profile
    document.getElementById("metric-branch-code").textContent = data.ifsc_code;
    document.getElementById("metric-branch-name").textContent = data.branch_name;
    document.getElementById("b-detail-name").textContent = data.bank_name;
    document.getElementById("b-detail-branch").textContent = data.branch_name;
    document.getElementById("b-detail-ifsc").textContent = data.ifsc_code;
    document.getElementById("b-detail-swift").textContent = data.swift_code;
    document.getElementById("b-detail-routing").textContent = data.routing_number;
    document.getElementById("b-detail-reserve").textContent = `${data.reserve_ratio}%`;
    document.getElementById("b-detail-phone").textContent = data.support_phone;
    document.getElementById("b-detail-email").textContent = data.support_email;
    document.getElementById("b-detail-address").textContent = data.address;

    // Populate edit form fields
    document.getElementById("edit-bank-name").value = data.bank_name;
    document.getElementById("edit-branch-name").value = data.branch_name;
    document.getElementById("edit-ifsc-code").value = data.ifsc_code;
    document.getElementById("edit-swift-code").value = data.swift_code;
    document.getElementById("edit-routing-num").value = data.routing_number;
    document.getElementById("edit-support-phone").value = data.support_phone;
    document.getElementById("edit-support-email").value = data.support_email;
    document.getElementById("edit-reserve-ratio").value = data.reserve_ratio;
    document.getElementById("edit-bank-address").value = data.address;

    // Populate in Customer view
    document.getElementById("u-bank-fullname").textContent = `${data.bank_name} • ${data.branch_name}`;
    document.getElementById("u-bank-ifsc").textContent = data.ifsc_code;
    document.getElementById("u-bank-swift").textContent = data.swift_code;
    document.getElementById("u-bank-phone").textContent = data.support_phone;
    document.getElementById("u-bank-email").textContent = data.support_email;
  } catch (err) {
    console.error("Could not fetch bank info:", err);
  }
}

async function handleBankInfoSubmit(event) {
  event.preventDefault();
  const btn = document.getElementById("save-bank-submit-btn");
  btn.disabled = true;

  const payload = {
    bank_name: document.getElementById("edit-bank-name").value.trim(),
    branch_name: document.getElementById("edit-branch-name").value.trim(),
    ifsc_code: document.getElementById("edit-ifsc-code").value.trim(),
    swift_code: document.getElementById("edit-swift-code").value.trim(),
    routing_number: document.getElementById("edit-routing-num").value.trim(),
    support_phone: document.getElementById("edit-support-phone").value.trim(),
    support_email: document.getElementById("edit-support-email").value.trim(),
    reserve_ratio: parseFloat(document.getElementById("edit-reserve-ratio").value) || 12.5,
    address: document.getElementById("edit-bank-address").value.trim(),
  };

  try {
    await apiRequest("/api/bank/info", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    showToast("Bank details successfully updated", "success");
    closeModal("modal-bank-info");
    await fetchBankInfo();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

// --- ADMIN PORTAL LOGIC ---
async function loadAdminDashboard() {
  await Promise.all([fetchAdminMetrics(), fetchAdminAccounts(), fetchAdminTransactions()]);
}

async function fetchAdminMetrics() {
  try {
    const m = await apiRequest("/api/admin/metrics");
    document.getElementById("metric-vault-total").textContent = formatCurrency(m.total_vault_deposits);
    document.getElementById("metric-active-accounts").textContent = m.active_accounts;
    document.getElementById("metric-frozen-note").textContent = `${m.frozen_accounts} frozen accounts`;
    document.getElementById("metric-trans-volume").textContent = formatCurrency(m.total_volume);
    document.getElementById("metric-trans-count").textContent = `${m.total_transactions} total transactions`;
  } catch (err) {
    console.error("Admin metrics error:", err);
  }
}

async function fetchAdminAccounts() {
  try {
    const accounts = await apiRequest("/api/admin/accounts");
    state.adminAccounts = accounts;
    renderAdminAccounts(accounts);
  } catch (err) {
    showToast(err.message, "error");
  }
}

function renderAdminAccounts(accounts) {
  const tbody = document.getElementById("admin-accounts-tbody");
  document.getElementById("admin-accounts-count").textContent = `${accounts.length} Accounts`;
  tbody.innerHTML = "";

  if (accounts.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 2rem;">No accounts found.</td></tr>`;
    return;
  }

  accounts.forEach((acc) => {
    const tr = document.createElement("tr");
    const isFrozen = acc.status === "frozen";

    tr.innerHTML = `
      <td class="font-mono" style="font-weight: 600; color: #a5b4fc;">${acc.account_number}</td>
      <td>
        <strong>${escapeHtml(acc.full_name)}</strong>
        <div style="font-size: 0.75rem; color: var(--text-muted);">${escapeHtml(acc.username)}</div>
      </td>
      <td><span class="badge-pill">${acc.account_type}</span></td>
      <td style="font-weight: 700; font-size: 0.95rem;">${formatCurrency(acc.balance)}</td>
      <td>
        <span class="status-pill ${acc.status}">
          <span style="font-size: 0.6rem;">●</span> ${acc.status}
        </span>
      </td>
      <td style="font-size: 0.8rem; color: var(--text-muted);">
        <div>${escapeHtml(acc.email)}</div>
        <div>${escapeHtml(acc.phone || "--")}</div>
      </td>
      <td>
        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.78rem;" onclick="toggleAccountStatus('${acc.account_number}', '${isFrozen ? "active" : "frozen"}')">
          ${isFrozen ? "Reactivate" : "Freeze"}
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function filterAdminAccounts() {
  const query = document.getElementById("admin-account-search").value.toLowerCase();
  const filtered = state.adminAccounts.filter(
    (a) =>
      a.account_number.toLowerCase().includes(query) ||
      a.full_name.toLowerCase().includes(query) ||
      a.email.toLowerCase().includes(query) ||
      a.username.toLowerCase().includes(query)
  );
  renderAdminAccounts(filtered);
}

async function toggleAccountStatus(accountNumber, newStatus) {
  try {
    await apiRequest(`/api/admin/accounts/${accountNumber}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: newStatus }),
    });
    showToast(`Account ${accountNumber} set to ${newStatus}`, "success");
    await fetchAdminAccounts();
    await fetchAdminMetrics();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function handleCreateAccountSubmit(event) {
  event.preventDefault();
  const btn = document.getElementById("create-acc-submit-btn");
  btn.disabled = true;

  const payload = {
    full_name: document.getElementById("new-user-fullname").value.trim(),
    username: document.getElementById("new-user-username").value.trim(),
    email: document.getElementById("new-user-email").value.trim(),
    phone: document.getElementById("new-user-phone").value.trim(),
    password: document.getElementById("new-user-password").value,
    account_type: document.getElementById("new-user-type").value,
    initial_deposit: parseFloat(document.getElementById("new-user-deposit").value) || 0.0,
  };

  try {
    const res = await apiRequest("/api/admin/accounts", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showToast(`Account ${res.account_number} created!`, "success");
    closeModal("modal-create-account");
    event.target.reset();
    await fetchAdminAccounts();
    await fetchAdminMetrics();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

async function fetchAdminTransactions() {
  try {
    const txs = await apiRequest("/api/admin/transactions");
    state.adminTransactions = txs;
    renderAdminTransactions(txs);
  } catch (err) {
    console.error("Admin tx fetch error:", err);
  }
}

function renderAdminTransactions(txs) {
  const tbody = document.getElementById("admin-tx-tbody");
  tbody.innerHTML = "";

  if (txs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-dim); padding: 2rem;">No transaction records found.</td></tr>`;
    return;
  }

  txs.forEach((tx) => {
    const tr = document.createElement("tr");
    const dateFormatted = formatDateTime(tx.timestamp);

    tr.innerHTML = `
      <td class="font-mono" style="color: var(--cyan); font-weight: 600;">${tx.reference_id}</td>
      <td style="font-size: 0.8rem; color: var(--text-muted);">${dateFormatted}</td>
      <td>
        <span class="badge-pill" style="text-transform: capitalize;">${tx.transaction_type}</span>
      </td>
      <td style="font-size: 0.85rem;">
        ${tx.from_account_number ? `<strong class="font-mono">${tx.from_account_number}</strong><div style="font-size: 0.72rem; color: var(--text-muted);">${escapeHtml(tx.from_user_name || "")}</div>` : '<span style="color: var(--text-dim);">Central Treasury</span>'}
      </td>
      <td style="font-size: 0.85rem;">
        ${tx.to_account_number ? `<strong class="font-mono">${tx.to_account_number}</strong><div style="font-size: 0.72rem; color: var(--text-muted);">${escapeHtml(tx.to_user_name || "")}</div>` : '<span style="color: var(--text-dim);">Cash Outflow / ATM</span>'}
      </td>
      <td style="font-weight: 700; color: #fff;">${formatCurrency(tx.amount)}</td>
      <td style="font-size: 0.82rem; color: var(--text-muted); max-width: 200px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">
        ${escapeHtml(tx.description || "--")}
      </td>
      <td>
        <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" onclick='openReceiptModal(${JSON.stringify(tx).replace(/'/g, "&#39;")})'>
          View
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function filterAdminTransactions() {
  const typeFilter = document.getElementById("admin-tx-filter").value;
  const search = document.getElementById("admin-tx-search").value.toLowerCase();

  const filtered = state.adminTransactions.filter((tx) => {
    const matchesType = typeFilter === "all" || tx.transaction_type === typeFilter;
    const matchesSearch =
      tx.reference_id.toLowerCase().includes(search) ||
      (tx.from_account_number && tx.from_account_number.toLowerCase().includes(search)) ||
      (tx.to_account_number && tx.to_account_number.toLowerCase().includes(search)) ||
      (tx.description && tx.description.toLowerCase().includes(search));
    return matchesType && matchesSearch;
  });

  renderAdminTransactions(filtered);
}

function switchAdminSection(secName) {
  document.querySelectorAll(".section-tab").forEach((btn) => btn.classList.remove("active"));
  document.querySelectorAll(".admin-tab-content").forEach((tab) => tab.classList.remove("active"));

  document.getElementById(`btn-admin-tab-${secName}`).classList.add("active");
  document.getElementById(`admin-sec-${secName}`).classList.add("active");
}

// --- USER PORTAL LOGIC ---
async function loadUserDashboard() {
  await Promise.all([fetchUserAccount(), fetchUserTransactions()]);
}

async function fetchUserAccount() {
  try {
    const acc = await apiRequest("/api/user/account");
    state.userAccount = acc;

    // Update Greeting & Chips
    document.getElementById("user-display-name").textContent = acc.user_full_name;
    document.getElementById("user-acc-type-chip").textContent = `${acc.account_type} Account`;
    const statusChip = document.getElementById("user-acc-status-chip");
    const statusText = document.getElementById("user-acc-status-text");

    if (acc.status === "active") {
      statusChip.className = "status-chip active";
      statusText.textContent = "Active Account";
    } else {
      statusChip.className = "status-chip";
      statusChip.style.borderColor = "var(--ruby)";
      statusChip.style.color = "var(--ruby)";
      statusText.textContent = "Frozen / Inactive";
    }

    // Update 3D Bank Card
    document.getElementById("card-holder-name").textContent = acc.user_full_name.toUpperCase();
    document.getElementById("card-number-display").textContent = acc.card_number;
    document.getElementById("card-tier-label").textContent = acc.account_type.toUpperCase();

    // Update Balance Display
    document.getElementById("user-balance-display").textContent = formatNumber(acc.balance);
    document.getElementById("user-acc-number").textContent = acc.account_number;
    document.getElementById("user-ifsc-code").textContent = acc.ifsc_code;

    // Preset limits in withdrawal modal
    document.getElementById("withdraw-max-balance").textContent = formatCurrency(acc.balance);
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function fetchUserTransactions() {
  try {
    const txs = await apiRequest("/api/user/transactions");
    state.userTransactions = txs;
    renderUserTransactions(txs);
  } catch (err) {
    console.error("User tx fetch error:", err);
  }
}

function renderUserTransactions(txs) {
  const tbody = document.getElementById("user-tx-tbody");
  tbody.innerHTML = "";

  const filtered = txs.filter((tx) => {
    if (state.userTxFilter === "all") return true;
    return tx.transaction_type === state.userTxFilter;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-dim); padding: 2rem;">No transaction entries recorded.</td></tr>`;
    return;
  }

  filtered.forEach((tx) => {
    const tr = document.createElement("tr");
    const isCredit = tx.flow === "credit";
    const flowSign = isCredit ? "+" : "-";
    const flowClass = isCredit ? "credit" : "debit";

    // Counterparty label
    let counterparty = tx.description || "Banking Operation";
    if (tx.transaction_type === "transfer") {
      if (isCredit) {
        counterparty = `Received from: ${tx.from_user_name || tx.from_account_number || "Bank Member"}`;
      } else {
        counterparty = `Transferred to: ${tx.to_user_name || tx.to_account_number || "Bank Member"}`;
      }
    }

    tr.innerHTML = `
      <td>
        <strong style="text-transform: capitalize;">${tx.transaction_type}</strong>
        <div class="font-mono" style="font-size: 0.72rem; color: var(--text-dim);">${tx.reference_id}</div>
      </td>
      <td style="font-size: 0.85rem;">
        <div>${escapeHtml(counterparty)}</div>
        <small style="color: var(--text-dim);">${escapeHtml(tx.description || "")}</small>
      </td>
      <td style="font-size: 0.8rem; color: var(--text-muted);">${formatDateTime(tx.timestamp)}</td>
      <td>
        <span class="tx-flow-badge ${flowClass}">
          ${isCredit ? "↓ Credit" : "↑ Debit"}
        </span>
      </td>
      <td style="font-size: 1rem; font-weight: 700; color: ${isCredit ? "var(--emerald)" : "var(--ruby)"};">
        ${flowSign}${formatCurrency(tx.amount)}
      </td>
      <td>
        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.75rem;" onclick='openReceiptModal(${JSON.stringify(tx).replace(/'/g, "&#39;")})'>
          Receipt
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function setUserTxFilter(type, btnElement) {
  state.userTxFilter = type;
  document.querySelectorAll("#user-tx-filters .filter-pill").forEach((b) => b.classList.remove("active"));
  if (btnElement) btnElement.classList.add("active");
  renderUserTransactions(state.userTransactions);
}

// Deposit Handlers
function setDepositAmount(amt) {
  document.getElementById("deposit-amount").value = amt;
}

async function handleDepositSubmit(event) {
  event.preventDefault();
  const amt = parseFloat(document.getElementById("deposit-amount").value);
  const memo = document.getElementById("deposit-memo").value.trim();
  const btn = document.getElementById("deposit-submit-btn");

  if (!amt || amt <= 0) {
    showToast("Please enter a valid deposit amount", "error");
    return;
  }

  btn.disabled = true;
  try {
    const res = await apiRequest("/api/user/deposit", {
      method: "POST",
      body: JSON.stringify({ amount: amt, description: memo }),
    });
    showToast(res.message, "success");
    closeModal("modal-deposit");
    document.getElementById("deposit-amount").value = "";
    await fetchUserAccount();
    await fetchUserTransactions();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

// Withdrawal Handlers
function setWithdrawAmount(amt) {
  document.getElementById("withdraw-amount").value = amt;
}

async function handleWithdrawSubmit(event) {
  event.preventDefault();
  const amt = parseFloat(document.getElementById("withdraw-amount").value);
  const memo = document.getElementById("withdraw-memo").value.trim();
  const btn = document.getElementById("withdraw-submit-btn");

  if (!amt || amt <= 0) {
    showToast("Please enter a valid withdrawal amount", "error");
    return;
  }

  btn.disabled = true;
  try {
    const res = await apiRequest("/api/user/withdraw", {
      method: "POST",
      body: JSON.stringify({ amount: amt, description: memo }),
    });
    showToast(res.message, "success");
    closeModal("modal-withdraw");
    document.getElementById("withdraw-amount").value = "";
    await fetchUserAccount();
    await fetchUserTransactions();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

// Transfer Handlers
let recipientLookupTimer = null;
function validateRecipientAccount(accNum) {
  clearTimeout(recipientLookupTimer);
  const badge = document.getElementById("transfer-recipient-badge");
  const nameSpan = document.getElementById("transfer-recipient-name");

  if (!accNum || accNum.trim().length < 5) {
    badge.classList.add("hidden");
    return;
  }

  recipientLookupTimer = setTimeout(async () => {
    try {
      const data = await apiRequest(`/api/user/lookup-account/${accNum.trim()}`);
      badge.classList.remove("hidden");
      badge.style.background = "rgba(16, 185, 129, 0.15)";
      badge.style.borderColor = "rgba(16, 185, 129, 0.3)";
      badge.style.color = "#34d399";
      nameSpan.textContent = `Verified: ${data.recipient_name}`;
    } catch (e) {
      badge.classList.remove("hidden");
      badge.style.background = "rgba(244, 63, 94, 0.15)";
      badge.style.borderColor = "rgba(244, 63, 94, 0.3)";
      badge.style.color = "#fb7185";
      nameSpan.textContent = "Account not found or inactive";
    }
  }, 400);
}

async function handleTransferSubmit(event) {
  event.preventDefault();
  const targetAcc = document.getElementById("transfer-acc-number").value.trim();
  const amt = parseFloat(document.getElementById("transfer-amount").value);
  const memo = document.getElementById("transfer-memo").value.trim();
  const btn = document.getElementById("transfer-submit-btn");

  if (!targetAcc) {
    showToast("Please enter destination account number", "error");
    return;
  }
  if (!amt || amt <= 0) {
    showToast("Please enter a valid transfer amount", "error");
    return;
  }

  btn.disabled = true;
  try {
    const res = await apiRequest("/api/user/transfer", {
      method: "POST",
      body: JSON.stringify({
        to_account_number: targetAcc,
        amount: amt,
        description: memo,
      }),
    });
    showToast(res.message, "success");
    closeModal("modal-transfer");
    document.getElementById("transfer-acc-number").value = "";
    document.getElementById("transfer-amount").value = "";
    document.getElementById("transfer-recipient-badge").classList.add("hidden");
    await fetchUserAccount();
    await fetchUserTransactions();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

// Receipt Modal Handler
function openReceiptModal(tx) {
  document.getElementById("receipt-ref").textContent = tx.reference_id;
  document.getElementById("receipt-timestamp").textContent = formatDateTime(tx.timestamp);
  document.getElementById("receipt-type").textContent = tx.transaction_type.toUpperCase();
  document.getElementById("receipt-amount").textContent = formatCurrency(tx.amount);
  document.getElementById("receipt-memo").textContent = tx.description || "Core Banking Settlement";

  const fromRow = document.getElementById("receipt-from-row");
  const toRow = document.getElementById("receipt-to-row");

  if (tx.from_account_number) {
    fromRow.style.display = "flex";
    document.getElementById("receipt-from-acc").textContent = `${tx.from_account_number} (${tx.from_user_name || ""})`;
  } else {
    document.getElementById("receipt-from-acc").textContent = "Bank Core Vault Deposit";
  }

  if (tx.to_account_number) {
    toRow.style.display = "flex";
    document.getElementById("receipt-to-acc").textContent = `${tx.to_account_number} (${tx.to_user_name || ""})`;
  } else {
    document.getElementById("receipt-to-acc").textContent = "Cash Withdrawal Outflow";
  }

  openModal("modal-receipt");
}

// Modal Open / Close Helpers
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.add("active");
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.remove("active");
}

// --- UTILITIES ---
function formatCurrency(val) {
  const num = parseFloat(val) || 0;
  return "₹" + num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatNumber(val) {
  const num = parseFloat(val) || 0;
  return num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatDateTime(isoString) {
  if (!isoString) return "--";
  try {
    const d = new Date(isoString);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (e) {
    return isoString;
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// Toast Notifications
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  let icon = "ℹ️";
  if (type === "success") icon = "✓";
  if (type === "error") icon = "⚠️";

  toast.innerHTML = `<span style="font-weight: 700;">${icon}</span><span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.transition = "all 0.3s ease";
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
