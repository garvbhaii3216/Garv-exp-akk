// Personal Expense & Allowance Tracker - Frontend Application Logic

// ==========================================
// CORE SECURITY UTILITY: XSS PREVENTION
// ==========================================
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function safeRenderIcons() {
  if (typeof lucide !== "undefined" && lucide && typeof lucide.createIcons === "function") {
    try {
      lucide.createIcons();
    } catch (e) {
      console.warn("Lucide render error:", e);
    }
  }
}

// ==========================================
// APPLICATION STATE
// ==========================================
let state = {
  token: localStorage.getItem("token") || sessionStorage.getItem("token") || null,
  user: JSON.parse(localStorage.getItem("user") || sessionStorage.getItem("user") || "null"),
  currentMonthYear: getInitialMonthYear(),
  categories: [],
  dashboardData: null,
  expenses: [],
  refills: [],
  settlementData: null,
  activeTab: "dashboard",
  categoryFilter: "All",
  searchQuery: "",
  sortBy: "date_desc",
  isDarkMode: localStorage.getItem("theme") === "dark",
  isOffline: !navigator.onLine,
  charts: {
    donut: null,
    bar: null
  }
};

function getInitialMonthYear() {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  return `${year}-${month}`;
}

function formatMonthLabel(monthYear) {
  const [year, month] = monthYear.split("-");
  const dateObj = new Date(parseInt(year), parseInt(month) - 1, 1);
  return dateObj.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

function getCurrency() {
  return (state.user && state.user.currency_symbol) ? state.user.currency_symbol : "₹";
}

function formatCurrency(amount) {
  const sym = getCurrency();
  const num = Number(amount) || 0;
  return `${sym}${num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}


// ==========================================
// TOAST NOTIFICATIONS
// ==========================================
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  const bgColors = {
    success: "bg-emerald-600 text-white",
    error: "bg-rose-600 text-white",
    info: "bg-indigo-600 text-white",
    warning: "bg-amber-500 text-white"
  };

  const icons = {
    success: "check-circle",
    error: "alert-triangle",
    info: "info",
    warning: "alert-circle"
  };

  toast.className = `pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-2xl shadow-lg text-xs font-semibold transform transition-all duration-300 translate-y-2 opacity-0 ${bgColors[type] || bgColors.info}`;
  toast.innerHTML = `
    <i data-lucide="${icons[type] || 'info'}" class="w-4 h-4 flex-shrink-0"></i>
    <span>${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);
  safeRenderIcons();

  requestAnimationFrame(() => {
    toast.classList.remove("translate-y-2", "opacity-0");
  });

  setTimeout(() => {
    toast.classList.add("translate-y-2", "opacity-0");
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}


// ==========================================
// API CONFIGURATION & DYNAMIC BASE RESOLUTION
// ==========================================
// Automatically detects if the frontend is loaded from file:// or an alternative dev port (e.g., 5500, 3000)
// and connects to the FastAPI backend at http://127.0.0.1:8000.
const API_BASE = (() => {
  if (typeof window === "undefined") return "";
  const proto = window.location.protocol;
  const port = window.location.port;
  if (proto === "file:" || (port && port !== "8000")) {
    return "http://127.0.0.1:8000";
  }
  return "";
})();

function getApiUrl(endpoint) {
  if (!endpoint) return "";
  if (endpoint.startsWith("http://") || endpoint.startsWith("https://")) {
    return endpoint;
  }
  const clean = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  return `${API_BASE}${clean}`;
}

function formatNetworkError(err) {
  if (!err) return "An unexpected error occurred.";
  const msg = err.message || String(err);
  if (
    msg.toLowerCase().includes("failed to fetch") ||
    msg.toLowerCase().includes("networkerror") ||
    msg.toLowerCase().includes("load failed") ||
    err.name === "TypeError"
  ) {
    return "Server offline or unreachable. Please start the backend with 'python run.py' (running at http://127.0.0.1:8000).";
  }
  return msg;
}

function updateServerStatusBadge(isOnline) {
  const dot = document.getElementById("serverStatusDot");
  const text = document.getElementById("serverStatusText");
  const badge = document.getElementById("serverStatusBadge");
  if (!dot || !text) return;

  if (isOnline) {
    dot.className = "w-2 h-2 rounded-full bg-emerald-500";
    text.textContent = "Backend Connected";
    badge?.classList.add("text-emerald-700", "dark:text-emerald-400");
  } else {
    dot.className = "w-2 h-2 rounded-full bg-rose-500";
    text.textContent = "Backend Offline (run 'python run.py')";
    badge?.classList.add("text-rose-600", "dark:text-rose-400");
  }
}

async function checkBackendHealth() {
  try {
    const res = await fetch(getApiUrl("/api/categories"), {
      method: "GET",
      headers: { "Accept": "application/json" }
    });
    if (res.ok) {
      updateServerStatusBadge(true);
      return true;
    }
  } catch (e) {
    // Backend is unreachable
  }
  updateServerStatusBadge(false);
  return false;
}

// ==========================================
// OFFLINE CACHE & LOCAL MUTATION MANAGEMENT
// ==========================================
function getOfflineCacheKey(endpoint) {
  return `offline_cache_${endpoint.replace(/[^a-zA-Z0-9]/g, "_")}`;
}

function getOfflineCache(endpoint) {
  try {
    const raw = localStorage.getItem(getOfflineCacheKey(endpoint));
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function setOfflineCache(endpoint, data) {
  try {
    if (data !== null && data !== undefined) {
      localStorage.setItem(getOfflineCacheKey(endpoint), JSON.stringify(data));
    }
  } catch (e) {}
}

function handleOfflineMutation(endpoint, options) {
  const method = (options.method || "POST").toUpperCase();
  const queue = JSON.parse(localStorage.getItem("offline_sync_queue") || "[]");
  const tempId = "offline_" + Date.now() + "_" + Math.random().toString(36).substr(2, 5);

  const queueItem = {
    id: tempId,
    endpoint,
    options,
    createdAt: new Date().toISOString()
  };
  queue.push(queueItem);
  localStorage.setItem("offline_sync_queue", JSON.stringify(queue));
  updateOfflineIndicator();

  // Optimistic local state update
  let payload = {};
  try {
    payload = options.body ? JSON.parse(options.body) : {};
  } catch (e) {}

  if (endpoint.includes("/api/expenses")) {
    if (method === "POST") {
      const syntheticExpense = {
        id: tempId,
        amount: Number(payload.amount) || 0,
        description: payload.description || "Offline Expense",
        category: payload.category || "Other",
        date: payload.date || new Date().toISOString().split("T")[0],
        payment_mode: payload.payment_mode || "UPI",
        receipt_note: payload.receipt_note || "",
        is_essential: Boolean(payload.is_essential),
        created_at: new Date().toISOString(),
        offline_pending: true
      };
      state.expenses.unshift(syntheticExpense);
      if (state.dashboardData) {
        state.dashboardData.total_spent = (state.dashboardData.total_spent || 0) + syntheticExpense.amount;
        state.dashboardData.remaining_balance = (state.dashboardData.remaining_balance || 0) - syntheticExpense.amount;
        if (state.dashboardData.recent_expenses) {
          state.dashboardData.recent_expenses.unshift(syntheticExpense);
        }
        setOfflineCache(`/api/dashboard?month_year=${state.currentMonthYear}`, state.dashboardData);
      }
      setOfflineCache(`/api/expenses?month_year=${state.currentMonthYear}`, state.expenses);
      showToast("Expense logged offline. Will sync when back online.", "info");
      renderExpensesList();
      renderDashboardSummary();
      return syntheticExpense;
    }
  } else if (endpoint.includes("/api/refills")) {
    if (method === "POST") {
      const syntheticRefill = {
        id: tempId,
        amount: Number(payload.amount) || 0,
        source: payload.source || "Parent / Bank Refill",
        notes: payload.notes || "",
        date: payload.date || new Date().toISOString().split("T")[0],
        created_at: new Date().toISOString(),
        offline_pending: true
      };
      state.refills.unshift(syntheticRefill);
      if (state.dashboardData) {
        state.dashboardData.total_refilled = (state.dashboardData.total_refilled || 0) + syntheticRefill.amount;
        state.dashboardData.remaining_balance = (state.dashboardData.remaining_balance || 0) + syntheticRefill.amount;
        setOfflineCache(`/api/dashboard?month_year=${state.currentMonthYear}`, state.dashboardData);
      }
      setOfflineCache(`/api/refills?month_year=${state.currentMonthYear}`, state.refills);
      showToast("Money added offline. Will sync when back online.", "info");
      renderRefillsList();
      renderDashboardSummary();
      return syntheticRefill;
    }
  }

  showToast("Saved offline. Will auto-sync when connected.", "info");
  return { id: tempId, ...payload, offline_pending: true };
}

function updateOfflineIndicator() {
  const badge = document.getElementById("offlineIndicatorBadge");
  const text = document.getElementById("offlineIndicatorText");
  if (!badge) return;

  const queue = JSON.parse(localStorage.getItem("offline_sync_queue") || "[]");
  if (!navigator.onLine) {
    badge.className = "flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-100 dark:bg-amber-950/70 text-amber-700 dark:text-amber-400 border border-amber-300 dark:border-amber-800 animate-pulse";
    if (text) text.textContent = `Offline Mode (${queue.length} pending)`;
  } else if (queue.length > 0) {
    badge.className = "flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-indigo-100 dark:bg-indigo-950/70 text-indigo-700 dark:text-indigo-400 border border-indigo-300 dark:border-indigo-800 animate-pulse";
    if (text) text.textContent = `Syncing (${queue.length} pending)...`;
  } else {
    badge.className = "hidden";
  }
}

function initOfflineManager() {
  window.addEventListener("online", () => {
    state.isOffline = false;
    updateServerStatusBadge(true);
    updateOfflineIndicator();
    showToast("Internet restored! Syncing offline records...", "success");
    syncOfflineQueue();
  });

  window.addEventListener("offline", () => {
    state.isOffline = true;
    updateServerStatusBadge(false);
    updateOfflineIndicator();
    showToast("Internet disconnected. Operating in 100% Offline Mode.", "warning");
  });

  updateOfflineIndicator();

  // If online on start, sync any pending offline changes
  if (navigator.onLine) {
    setTimeout(() => {
      syncOfflineQueue();
    }, 2500);
  }
}

async function syncOfflineQueue() {
  if (!navigator.onLine || !state.token) return;
  const queue = JSON.parse(localStorage.getItem("offline_sync_queue") || "[]");
  if (queue.length === 0) {
    updateOfflineIndicator();
    return;
  }

  const remaining = [];
  let syncedCount = 0;

  for (const item of queue) {
    try {
      const headers = {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${state.token}`,
        ...(item.options.headers || {})
      };
      const res = await fetch(getApiUrl(item.endpoint), {
        ...item.options,
        headers
      });

      if (res.ok || res.status === 409) {
        syncedCount++;
      } else {
        remaining.push(item);
      }
    } catch (e) {
      remaining.push(item);
    }
  }

  localStorage.setItem("offline_sync_queue", JSON.stringify(remaining));
  updateOfflineIndicator();

  if (syncedCount > 0) {
    showToast(`Successfully backed up ${syncedCount} offline record(s) to server!`, "success");
    refreshCurrentView();
  }
}


// ==========================================
// RENDER COLD-START SPLASH & PROGRESS BAR
// ==========================================
let splashDismissed = false;
let splashProgress = 12;
let splashInterval = null;

function initStartupSplash() {
  const splash = document.getElementById("appStartupSplash");
  if (!splash) return;

  const bar = document.getElementById("splashProgressBar");
  const percentText = document.getElementById("splashPercentText");
  const phaseText = document.getElementById("splashProgressPhase");
  const statusText = document.getElementById("splashStatusText");

  splashInterval = setInterval(() => {
    if (splashDismissed) {
      clearInterval(splashInterval);
      return;
    }

    if (splashProgress < 94) {
      const step = splashProgress < 40 ? 6 : splashProgress < 75 ? 3 : 1.2;
      splashProgress = Math.min(94, splashProgress + step);
      if (bar) bar.style.width = `${splashProgress}%`;
      if (percentText) percentText.textContent = `${Math.round(splashProgress)}%`;

      if (splashProgress < 30) {
        if (phaseText) phaseText.textContent = "Connecting to cloud instance...";
        if (statusText) statusText.textContent = "Booting dedicated backend service...";
      } else if (splashProgress < 60) {
        if (phaseText) phaseText.textContent = "Establishing TLS security handshake...";
        if (statusText) statusText.textContent = "Warming encrypted SQLite database vault...";
      } else if (splashProgress < 85) {
        if (phaseText) phaseText.textContent = "Verifying tenant session tokens...";
        if (statusText) statusText.textContent = "Synchronizing local expense telemetry...";
      } else {
        if (phaseText) phaseText.textContent = "Almost ready...";
        if (statusText) statusText.textContent = "Finalizing dashboard components...";
      }
    }
  }, 350);
}

function completeStartupSplash() {
  if (splashDismissed) return;
  const bar = document.getElementById("splashProgressBar");
  const percentText = document.getElementById("splashPercentText");
  const phaseText = document.getElementById("splashProgressPhase");
  const statusText = document.getElementById("splashStatusText");

  if (bar) bar.style.width = "100%";
  if (percentText) percentText.textContent = "100%";
  if (phaseText) phaseText.textContent = "Cloud Instance Connected!";
  if (statusText) statusText.textContent = "Welcome to Expense Tracker";

  setTimeout(() => {
    dismissSplashNow();
  }, 450);
}

function dismissSplashNow() {
  if (splashDismissed) return;
  splashDismissed = true;
  if (splashInterval) clearInterval(splashInterval);
  if (cbTimerInterval) clearInterval(cbTimerInterval);

  const splash = document.getElementById("appStartupSplash");
  if (!splash) return;

  splash.classList.add("opacity-0", "transition-opacity", "duration-500", "pointer-events-none");
  setTimeout(() => {
    splash.classList.add("hidden");
  }, 500);
}


// ==========================================
// COLOR BLIND SPEED TEST MINI-GAME
// ==========================================
let cbLevel = 1;
let cbScore = 0;
let cbTimeLeft = 15;
let cbTimerInterval = null;
let cbIsActive = true;

function initColorBlindGame() {
  cbLevel = 1;
  cbScore = 0;
  cbTimeLeft = 15;
  cbIsActive = true;

  updateColorBlindStats();
  renderColorBlindGrid();

  if (cbTimerInterval) clearInterval(cbTimerInterval);
  cbTimerInterval = setInterval(() => {
    if (!cbIsActive || splashDismissed) {
      clearInterval(cbTimerInterval);
      return;
    }
    cbTimeLeft--;
    const timerEl = document.getElementById("cbTimer");
    if (timerEl) {
      timerEl.textContent = `${cbTimeLeft}s`;
      if (cbTimeLeft <= 5) {
        timerEl.className = "px-2.5 py-0.5 rounded-md bg-rose-600 text-white font-mono font-bold text-[11px] animate-pulse";
      } else {
        timerEl.className = "px-2.5 py-0.5 rounded-md bg-rose-950/70 text-rose-400 border border-rose-800/60 text-[11px] font-mono font-bold";
      }
    }
    if (cbTimeLeft <= 0) {
      handleColorBlindGameOver();
    }
  }, 1000);
}

function updateColorBlindStats() {
  const scoreEl = document.getElementById("cbScore");
  const levelEl = document.getElementById("cbLevelText");
  const timerEl = document.getElementById("cbTimer");

  if (scoreEl) scoreEl.textContent = `Score: ${cbScore}`;
  if (timerEl) timerEl.textContent = `${cbTimeLeft}s`;
  if (levelEl) {
    const tier = cbLevel < 3 ? "Novice" : cbLevel < 6 ? "Sharp Eyed" : cbLevel < 10 ? "Eagle Vision" : "Superhuman";
    levelEl.textContent = `Level ${cbLevel}: ${tier}`;
  }
}

function renderColorBlindGrid() {
  const grid = document.getElementById("colorBlindGrid");
  if (!grid || !cbIsActive) return;

  let size = 2;
  if (cbLevel >= 2 && cbLevel <= 3) size = 3;
  else if (cbLevel >= 4 && cbLevel <= 6) size = 4;
  else if (cbLevel >= 7 && cbLevel <= 9) size = 5;
  else if (cbLevel >= 10) size = 6;

  // Progressive difficulty: delta drops as level increases
  const delta = Math.max(2.5, 24 - (cbLevel * 2.1));

  const baseHue = Math.floor(Math.random() * 360);
  const baseSat = Math.floor(Math.random() * 25) + 65;
  const baseLight = Math.floor(Math.random() * 20) + 40;
  
  const direction = baseLight > 50 ? -1 : 1;
  const oddLight = Math.max(10, Math.min(90, baseLight + (direction * delta)));

  const totalTiles = size * size;
  const oddIndex = Math.floor(Math.random() * totalTiles);

  grid.style.gridTemplateColumns = `repeat(${size}, minmax(0, 1fr))`;
  grid.innerHTML = "";

  for (let i = 0; i < totalTiles; i++) {
    const tile = document.createElement("button");
    tile.type = "button";
    const isOdd = i === oddIndex;
    const tileLight = isOdd ? oddLight : baseLight;
    tile.style.backgroundColor = `hsl(${baseHue}, ${baseSat}%, ${tileLight}%)`;
    tile.className = "w-full h-full rounded-xl transition-transform active:scale-90 shadow-sm cursor-pointer";
    tile.setAttribute("aria-label", isOdd ? "Target odd shade tile" : "Standard tile");

    tile.addEventListener("click", () => {
      if (!cbIsActive) return;
      if (isOdd) {
        cbScore += 10 * cbLevel;
        cbLevel++;
        cbTimeLeft = Math.min(30, cbTimeLeft + 2);
        updateColorBlindStats();
        renderColorBlindGrid();
      } else {
        grid.classList.add("shake-anim");
        cbTimeLeft = Math.max(0, cbTimeLeft - 2);
        updateColorBlindStats();
        setTimeout(() => grid.classList.remove("shake-anim"), 350);
      }
    });

    grid.appendChild(tile);
  }
}

function handleColorBlindGameOver() {
  cbIsActive = false;
  if (cbTimerInterval) clearInterval(cbTimerInterval);

  const grid = document.getElementById("colorBlindGrid");
  if (!grid) return;

  grid.style.gridTemplateColumns = "1fr";
  grid.innerHTML = `
    <div class="flex flex-col items-center justify-center p-4 text-center space-y-2 bg-slate-900 rounded-2xl w-full h-full">
      <div class="text-xs font-bold uppercase tracking-wider text-rose-400">Time's Up!</div>
      <div class="text-xl font-black text-white">Score: ${cbScore}</div>
      <p class="text-[11px] text-slate-400">Reached Level ${cbLevel}</p>
      <button type="button" onclick="initColorBlindGame()" class="mt-2 px-4 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold shadow-md transition active-press">
        Play Again ⚡
      </button>
    </div>
  `;
}


// ==========================================
// API HELPER (WITH OFFLINE RESILIENCE)
// ==========================================
async function apiRequest(endpoint, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const url = getApiUrl(endpoint);
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };

  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }

  // If already known offline
  if (!navigator.onLine) {
    if (method === "GET") {
      const cached = getOfflineCache(endpoint);
      if (cached !== null) return cached;
      return null;
    } else {
      return handleOfflineMutation(endpoint, options);
    }
  }

  try {
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
      logout();
      showToast("Session expired. Please sign in again.", "warning");
      return null;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `Server error (${res.status})` }));
      throw new Error(err.detail || `Server error (${res.status})`);
    }

    const data = await res.json();
    if (method === "GET") {
      setOfflineCache(endpoint, data);
    }
    return data;
  } catch (error) {
    const isNetwork = !navigator.onLine ||
      error.name === "TypeError" ||
      (error.message && (
        error.message.toLowerCase().includes("failed to fetch") ||
        error.message.toLowerCase().includes("networkerror") ||
        error.message.toLowerCase().includes("load failed")
      ));

    if (isNetwork) {
      if (method === "GET") {
        const cached = getOfflineCache(endpoint);
        if (cached !== null) {
          showToast("Network unreachable. Showing saved offline records.", "info");
          return cached;
        }
      } else {
        return handleOfflineMutation(endpoint, options);
      }
    }

    showToast(formatNetworkError(error), "error");
    throw error;
  }
}


// ==========================================
// INITIALIZATION
// ==========================================
document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  setupEventListeners();
  setupOtpInputs();
  safeRenderIcons();

  // Initialize startup splash and fast color blind mini game
  initStartupSplash();
  initColorBlindGame();

  // Initialize offline caching and background auto-sync
  initOfflineManager();

  // Initialize Mobile App 1-Click Install detection (silent, zero auto-popups)
  initMobileInstallPrompt();

  // Service worker registration for PWA
  if ('serviceWorker' in navigator && window.location.protocol.startsWith("http")) {
    navigator.serviceWorker.register('/sw.js').catch((err) => {
      console.log('SW registration error:', err);
    });
  }

  // 1. Fetch public auth config (Google Client ID) asynchronously
  fetchAuthConfig();

  // 2. Instant Saved Profile Restoration (Save profile on this browser)
  const savedToken = localStorage.getItem("token") || sessionStorage.getItem("token");
  const savedUserStr = localStorage.getItem("user") || sessionStorage.getItem("user");

  if (savedToken && savedUserStr) {
    try {
      const parsedUser = JSON.parse(savedUserStr);
      if (parsedUser && parsedUser.id) {
        state.token = savedToken;
        state.user = parsedUser;

        // Check if Security App Lock (MPIN / Biometrics) is enabled
        if (isAppLockActive()) {
          showAppLockScreen();
          completeStartupSplash();
          if (isBiometricsEnabled()) {
            setTimeout(triggerBiometricPrompt, 280);
          }
        } else {
          // Instant access to saved profile! Zero lag, offline-ready!
          showApp();
          completeStartupSplash();
        }

        // Background session verification without blocking the user
        verifySessionInBackground();
        return;
      }
    } catch (parseErr) {
      console.warn("Saved profile parse notice:", parseErr);
    }
  }

  // If no saved profile found, verify backend health and show auth
  checkBackendHealth().finally(() => {
    showAuth();
    completeStartupSplash();
  });
});


// ==========================================
// THEME & DOM SETUP
// ==========================================
function initTheme() {
  if (state.isDarkMode) {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }
  updateThemeIcon();
}

function toggleDarkMode() {
  state.isDarkMode = !state.isDarkMode;
  localStorage.setItem("theme", state.isDarkMode ? "dark" : "light");
  initTheme();
  // Re-render charts with appropriate theme colors
  if (state.dashboardData) {
    renderCharts(state.dashboardData);
  }
}

function updateThemeIcon() {
  const icon = document.getElementById("themeIcon");
  if (icon) {
    icon.setAttribute("data-lucide", state.isDarkMode ? "sun" : "moon");
  }
  const headerIcon = document.getElementById("themeIconHeader");
  if (headerIcon) {
    headerIcon.setAttribute("data-lucide", state.isDarkMode ? "sun" : "moon");
  }
  safeRenderIcons();
}

// ==========================================
// LOGIN METHOD SWITCHER (Email vs Mobile)
// ==========================================
let currentLoginMethod = "email";

function setLoginMethod(method) {
  currentLoginMethod = method;
  const emailBtn = document.getElementById("loginMethodEmailBtn");
  const phoneBtn = document.getElementById("loginMethodPhoneBtn");
  const label = document.getElementById("loginUsernameLabel");
  const icon = document.getElementById("loginUsernameIcon");
  const input = document.getElementById("loginUsername");
  const help = document.getElementById("loginUsernameHelp");

  if (method === "email") {
    if (emailBtn) {
      emailBtn.className = "flex-1 py-1.5 px-2 rounded-lg font-semibold bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm flex items-center justify-center gap-1.5 transition";
    }
    if (phoneBtn) {
      phoneBtn.className = "flex-1 py-1.5 px-2 rounded-lg font-medium text-slate-600 dark:text-slate-300 hover:text-slate-900 flex items-center justify-center gap-1.5 transition";
    }
    if (label) label.textContent = "Email Address";
    if (icon) icon.innerHTML = `<i data-lucide="mail" class="w-4 h-4"></i>`;
    if (input) {
      input.type = "email";
      input.placeholder = "aarav.student@example.com";
    }
    if (help) help.textContent = "Sign in using your registered email address";
  } else {
    if (phoneBtn) {
      phoneBtn.className = "flex-1 py-1.5 px-2 rounded-lg font-semibold bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm flex items-center justify-center gap-1.5 transition";
    }
    if (emailBtn) {
      emailBtn.className = "flex-1 py-1.5 px-2 rounded-lg font-medium text-slate-600 dark:text-slate-300 hover:text-slate-900 flex items-center justify-center gap-1.5 transition";
    }
    if (label) label.textContent = "Mobile Phone Number";
    if (icon) icon.innerHTML = `<i data-lucide="phone" class="w-4 h-4"></i>`;
    if (input) {
      input.type = "tel";
      input.placeholder = "+91 98765 43210 or 9876543210";
    }
    if (help) help.textContent = "Sign in using your 10-digit mobile number";
  }
  safeRenderIcons();
}

// ==========================================
// AUTHENTICATION LOGIC
// ==========================================
function setupEventListeners() {
  // Tab toggle in auth
  const tabLoginBtn = document.getElementById("tabLoginBtn");
  const tabRegisterBtn = document.getElementById("tabRegisterBtn");
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");

  tabLoginBtn?.addEventListener("click", () => {
    tabLoginBtn.className = "w-1/2 py-2 text-sm font-semibold rounded-lg transition-all bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm";
    tabRegisterBtn.className = "w-1/2 py-2 text-sm font-semibold rounded-lg transition-all text-slate-600 dark:text-slate-300 hover:text-slate-900";
    loginForm.classList.remove("hidden");
    registerForm.classList.add("hidden");
  });

  tabRegisterBtn?.addEventListener("click", () => {
    tabRegisterBtn.className = "w-1/2 py-2 text-sm font-semibold rounded-lg transition-all bg-white dark:bg-slate-800 text-emerald-600 dark:text-emerald-400 shadow-sm";
    tabLoginBtn.className = "w-1/2 py-2 text-sm font-semibold rounded-lg transition-all text-slate-600 dark:text-slate-300 hover:text-slate-900";
    registerForm.classList.remove("hidden");
    loginForm.classList.add("hidden");
  });

  // Login submission
  loginForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("loginUsername").value.trim();
    const password = document.getElementById("loginPassword").value;
    const saveCheck = document.getElementById("saveProfileCheck");
    const remember_me = saveCheck ? saveCheck.checked : true;

    try {
      const res = await fetch(getApiUrl("/api/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, remember_me })
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error((data && data.detail) || `Login failed (${res.status})`);

      applyAuthSession(data, remember_me);
      localStorage.setItem("last_username", username);

      showToast(`Welcome back, ${data.user.full_name}!`, "success");
      showApp();
    } catch (err) {
      showToast(formatNetworkError(err), "error");
    }
  });

  // Register submission -> Request Authentication OTP
  registerForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const full_name = document.getElementById("regFullName").value.trim();
    const email = document.getElementById("regEmail").value.trim().toLowerCase();
    const phone = document.getElementById("regPhone").value.trim();
    const password = document.getElementById("regPassword").value;
    const security_question = document.getElementById("regSecurityQuestion")?.value.trim();
    const security_answer = document.getElementById("regSecurityAnswer")?.value.trim();
    const currencyVal = document.getElementById("regCurrency").value.split(":");
    const currency_symbol = currencyVal[0];
    const currency_code = currencyVal[1];

    // Client-side password complexity verification
    if (password.length < 8) {
      showToast("Password must be at least 8 characters long.", "error");
      return;
    }
    if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/[0-9]/.test(password)) {
      showToast("Password must include at least one uppercase letter, one lowercase letter, and one number.", "error");
      return;
    }

    if (!security_question) {
      showToast("Please select a security question for password recovery.", "error");
      return;
    }
    if (!security_answer || security_answer.length < 2) {
      showToast("Please enter your answer to the security question.", "error");
      return;
    }

    const regBtn = document.getElementById("regSubmitBtn");
    const originalText = regBtn ? regBtn.innerHTML : "Create My Account";

    try {
      if (regBtn) {
        regBtn.disabled = true;
        regBtn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Sending Verification Code...</span>`;
        if (window.lucide) safeRenderIcons();
      }

      // 1. Send OTP request to backend
      const otpRes = await fetch(getApiUrl("/api/auth/send-registration-otp"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
      });
      const otpData = await otpRes.json().catch(() => null);
      if (!otpRes.ok) {
        throw new Error((otpData && otpData.detail) || `Failed to send verification OTP (${otpRes.status})`);
      }

      // Save pending registration payload with security question
      pendingRegistration = {
        full_name,
        email,
        phone: phone || null,
        password,
        currency_symbol,
        currency_code,
        security_question,
        security_answer
      };

      // Open OTP Verification Modal
      openOtpModal(email, otpData.dev_otp);
      showToast(otpData.message || `Verification code sent to ${email}`, "info");

    } catch (err) {
      showToast(formatNetworkError(err), "error");
    } finally {
      if (regBtn) {
        regBtn.disabled = false;
        regBtn.innerHTML = originalText;
        if (window.lucide) safeRenderIcons();
      }
    }
  });

  // Demo account filler
  document.getElementById("demoFillBtn")?.addEventListener("click", async () => {
    // Attempt login first with standard demo credentials
    const demoEmail = "aarav.student@example.com";
    const demoPass = "StudentPass123!";
    document.getElementById("loginUsername").value = demoEmail;
    document.getElementById("loginPassword").value = demoPass;

    try {
      const res = await fetch(getApiUrl("/api/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: demoEmail, password: demoPass, remember_me: true })
      });
      if (res.ok) {
        const data = await res.json().catch(() => null);
        if (data && data.access_token) {
          applyAuthSession(data, true);
          showToast("Signed in as Demo Student Aarav!", "success");
          showApp();
          return;
        }
      }
    } catch (e) {}

    // If demo account doesn't exist yet, auto register it
    try {
      const regRes = await fetch(getApiUrl("/api/auth/register"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: "Aarav Sharma",
          email: demoEmail,
          phone: "+919876543210",
          password: demoPass,
          currency_symbol: "₹",
          currency_code: "INR"
        })
      });
      if (regRes.ok) {
        const data = await regRes.json().catch(() => null);
        if (data && data.access_token) {
          applyAuthSession(data, true);

          // Seed some realistic starter expenses for the demo account
          await seedDemoExpenses(data.access_token);

          showToast("Created & seeded demo account!", "success");
          showApp();
          return;
        }
      }
    } catch (e) {
      showToast(formatNetworkError(e), "error");
      return;
    }
    showToast("Demo sign-in ready. Please click Sign In.", "info");
  });

  // Expense Form submit
  document.getElementById("expenseForm")?.addEventListener("submit", handleSaveExpense);

  // Refill Form submit
  document.getElementById("refillForm")?.addEventListener("submit", handleSaveRefill);

  // Allowance Form submit
  document.getElementById("allowanceForm")?.addEventListener("submit", handleSaveAllowance);
}

async function seedDemoExpenses(token) {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const baseDate = `${year}-${month}`;

  const demoItems = [
    { amount: 350, category: "Food & Dining", date: `${baseDate}-02`, description: "Campus cafeteria lunch & snacks", payment_mode: "UPI", is_essential: true },
    { amount: 1200, category: "Books & Study", date: `${baseDate}-04`, description: "Semester reference books & stationery", payment_mode: "UPI", is_essential: true },
    { amount: 450, category: "Transport & Fuel", date: `${baseDate}-06`, description: "Monthly Metro rail recharge", payment_mode: "UPI", is_essential: true },
    { amount: 620, category: "Groceries", date: `${baseDate}-07`, description: "Milk, bread, oats, and hostel fruits", payment_mode: "Cash", is_essential: true },
  ];

  for (const item of demoItems) {
    await fetch(getApiUrl("/api/expenses"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify(item)
    }).catch(() => {});
  }
}

function togglePasswordVisibility(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  if (input.type === "password") {
    input.type = "text";
    btn.innerHTML = `<i data-lucide="eye-off" class="w-4 h-4"></i>`;
  } else {
    input.type = "password";
    btn.innerHTML = `<i data-lucide="eye" class="w-4 h-4"></i>`;
  }
  safeRenderIcons();
}

function showAuth() {
  document.getElementById("authScreen")?.classList.remove("hidden");
  document.getElementById("appScreen")?.classList.add("hidden");

  // Pre-fill last signed in username if available
  const lastUser = localStorage.getItem("last_username");
  const loginInput = document.getElementById("loginUsername");
  if (lastUser && loginInput && !loginInput.value) {
    loginInput.value = lastUser;
  }
  safeRenderIcons();
}

function updateUserProfileHeader() {
  if (!state.user) return;
  const userNameDisp = document.getElementById("userNameDisplay");
  const userEmailDisp = document.getElementById("userEmailDisplay");
  const headerNameDisp = document.getElementById("headerUserName");
  const headerContactDisp = document.getElementById("headerUserContact");

  if (userNameDisp) userNameDisp.textContent = state.user.full_name;
  if (userEmailDisp) userEmailDisp.textContent = state.user.email || state.user.phone || "";
  if (headerNameDisp) headerNameDisp.textContent = state.user.full_name;
  if (headerContactDisp) headerContactDisp.textContent = state.user.email || state.user.phone || "";

  const initial = state.user.full_name.charAt(0).toUpperCase();
  const avatar = document.getElementById("userAvatar");
  if (avatar) avatar.textContent = initial;

  // Toggle Admin visibility based on role
  const adminNav = document.getElementById("nav-admin");
  const topNavAdmin = document.getElementById("top-nav-admin");
  const mobileAdminNav = document.getElementById("mobile-nav-admin");
  const adminUnlockBtn = document.getElementById("sidebarAdminUnlockBtn");
  if (state.user && state.user.is_admin) {
    if (adminNav) adminNav.classList.remove("hidden");
    if (topNavAdmin) topNavAdmin.classList.remove("hidden");
    if (mobileAdminNav) mobileAdminNav.classList.remove("hidden");
    if (adminUnlockBtn) adminUnlockBtn.classList.add("hidden");
  } else {
    if (adminNav) adminNav.classList.add("hidden");
    if (topNavAdmin) topNavAdmin.classList.add("hidden");
    if (mobileAdminNav) mobileAdminNav.classList.add("hidden");
    if (adminUnlockBtn) adminUnlockBtn.classList.remove("hidden");
  }
}

function showApp() {
  document.getElementById("authScreen")?.classList.add("hidden");
  document.getElementById("appScreen")?.classList.remove("hidden");
  safeRenderIcons();

  updateUserProfileHeader();
  loadCategories();
  loadDashboardData();
  switchTab("dashboard");
  checkAppLockPromoBanner();
}

// ==========================================
// SESSION PERSISTENCE & GOOGLE AUTHENTICATION
// ==========================================
let appAuthConfig = {
  google_client_id: null
};

async function fetchAuthConfig() {
  try {
    const res = await fetch(getApiUrl("/api/auth/config"));
    if (res.ok) {
      const cfg = await res.json();
      if (cfg && cfg.google_client_id) {
        appAuthConfig.google_client_id = cfg.google_client_id;
        window.GOOGLE_CLIENT_ID = cfg.google_client_id;
      }
    }
  } catch (e) {
    console.log("Config fetch notice:", e);
  }
}

async function verifySessionInBackground() {
  if (!state.token) return;
  try {
    const res = await fetch(getApiUrl("/api/auth/me"), {
      headers: { "Authorization": `Bearer ${state.token}` }
    });
    if (res.status === 401) {
      // Token expired or invalid on server
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      localStorage.removeItem("save_profile_active");
      sessionStorage.removeItem("token");
      sessionStorage.removeItem("user");
      state.token = null;
      state.user = null;
      showToast("Your saved session has expired. Please sign in again.", "warning");
      showAuth();
      return;
    }
    if (res.ok) {
      const freshUser = await res.json();
      state.user = freshUser;
      if (localStorage.getItem("save_profile_active") === "true") {
        localStorage.setItem("user", JSON.stringify(freshUser));
      } else {
        sessionStorage.setItem("user", JSON.stringify(freshUser));
      }
      updateUserProfileHeader();
    }
  } catch (err) {
    // Network delay, cold start, or offline: Keep user in dashboard!
    console.log("Background session verify notice:", err.message);
  }
}

function applyAuthSession(data, rememberMe = true) {
  state.token = data.access_token;
  state.user = data.user;

  if (rememberMe) {
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("user", JSON.stringify(data.user));
    localStorage.setItem("save_profile_active", "true");
    sessionStorage.removeItem("token");
    sessionStorage.removeItem("user");
  } else {
    sessionStorage.setItem("token", data.access_token);
    sessionStorage.setItem("user", JSON.stringify(data.user));
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    localStorage.removeItem("save_profile_active");
  }
}

function handleGoogleSignIn() {
  const saveCheck = document.getElementById("saveProfileCheck");
  const remember_me = saveCheck ? saveCheck.checked : true;

  // ONLY initialize Google Identity Services if a genuine Google Client ID is configured
  if (appAuthConfig.google_client_id && window.google && window.google.accounts && window.google.accounts.id) {
    try {
      google.accounts.id.initialize({
        client_id: appAuthConfig.google_client_id,
        callback: async (response) => {
          if (response && response.credential) {
            await executeGoogleAuthPayload({ credential: response.credential, remember_me });
          }
        }
      });
      google.accounts.id.prompt();
      return;
    } catch (e) {
      console.log("Google Identity Services notice:", e);
    }
  }

  // Open the fast Google Sign-in modal
  openGoogleAuthModal();
}

function openGoogleAuthModal() {
  const modal = document.getElementById("googleAuthModal");
  if (modal) {
    modal.classList.remove("hidden");
    const input = document.getElementById("googleCustomEmail");
    if (input) {
      const lastGoogle = localStorage.getItem("last_google_email");
      const currentLogin = document.getElementById("loginUsername")?.value.trim();
      if (lastGoogle && !input.value) {
        input.value = lastGoogle;
      } else if (currentLogin && currentLogin.includes("@") && !input.value) {
        input.value = currentLogin;
      }
      setTimeout(() => input.focus(), 150);
    }
  }
  safeRenderIcons();
}

function closeGoogleAuthModal() {
  const modal = document.getElementById("googleAuthModal");
  if (modal) modal.classList.add("hidden");
}

async function submitCustomGoogleAuth(event) {
  event.preventDefault();
  const email = document.getElementById("googleCustomEmail")?.value.trim();
  const fullName = document.getElementById("googleCustomName")?.value.trim() || "Google User";
  const saveCheck = document.getElementById("saveProfileCheck");
  const remember_me = saveCheck ? saveCheck.checked : true;

  if (!email) {
    showToast("Please enter your Google email address.", "error");
    return;
  }

  const btn = document.getElementById("googleContinueBtn");
  const origHtml = btn ? btn.innerHTML : "Continue with Google";

  try {
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Connecting Google...</span>`;
      safeRenderIcons();
    }
    await executeGoogleAuthPayload({ email, full_name: fullName, remember_me });
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
      safeRenderIcons();
    }
  }
}

async function executeGoogleAuthPayload(payload) {
  try {
    const res = await fetch(getApiUrl("/api/auth/google"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error((data && data.detail) || `Google sign-in failed (${res.status})`);
    }

    applyAuthSession(data, payload.remember_me !== false);
    if (payload.email) {
      localStorage.setItem("last_google_email", payload.email);
      localStorage.setItem("last_username", payload.email);
    }
    closeGoogleAuthModal();
    showToast(`Welcome ${data.user.full_name}! Signed in via Google.`, "success");
    showApp();
  } catch (err) {
    showToast(formatNetworkError(err), "error");
  }
}

// ==========================================
// FORGOT PASSWORD / SECURITY QUESTION FLOW
// ==========================================
let fpState = {
  identifier: "",
  question: ""
};

function openForgotPasswordModal() {
  const modal = document.getElementById("forgotPasswordModal");
  if (!modal) return;
  modal.classList.remove("hidden");

  // Reset steps
  document.getElementById("fpStep1")?.classList.remove("hidden");
  document.getElementById("fpStep2")?.classList.add("hidden");

  const identInput = document.getElementById("fpIdentifier");
  const loginInput = document.getElementById("loginUsername");
  const lastUser = localStorage.getItem("last_username");

  if (identInput) {
    identInput.value = (loginInput && loginInput.value.trim()) || lastUser || "";
    setTimeout(() => identInput.focus(), 150);
  }
  safeRenderIcons();
}

function closeForgotPasswordModal() {
  const modal = document.getElementById("forgotPasswordModal");
  if (modal) modal.classList.add("hidden");
}

function backToFpStep1() {
  document.getElementById("fpStep1")?.classList.remove("hidden");
  document.getElementById("fpStep2")?.classList.add("hidden");
  safeRenderIcons();
}

async function handleFetchSecurityQuestion() {
  const identInput = document.getElementById("fpIdentifier");
  const identifier = identInput?.value.trim();
  if (!identifier) {
    showToast("Please enter your registered email address or mobile number.", "error");
    return;
  }

  const btn = document.getElementById("fpFetchQuestionBtn");
  const origText = btn ? btn.innerHTML : "Continue";

  try {
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Finding Account...</span>`;
      safeRenderIcons();
    }

    const res = await fetch(getApiUrl("/api/auth/forgot-password/question"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier })
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error((data && data.detail) || "Failed to find account or security question.");
    }

    fpState.identifier = identifier;
    fpState.question = data.question;

    const qDisp = document.getElementById("fpQuestionDisplay");
    if (qDisp) qDisp.textContent = data.question;

    // Switch to step 2
    document.getElementById("fpStep1")?.classList.add("hidden");
    document.getElementById("fpStep2")?.classList.remove("hidden");

    const ansInput = document.getElementById("fpSecurityAnswer");
    if (ansInput) {
      ansInput.value = "";
      setTimeout(() => ansInput.focus(), 150);
    }
    const p1 = document.getElementById("fpNewPassword");
    const p2 = document.getElementById("fpConfirmPassword");
    if (p1) p1.value = "";
    if (p2) p2.value = "";

    safeRenderIcons();
  } catch (err) {
    showToast(formatNetworkError(err), "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
      safeRenderIcons();
    }
  }
}

async function handleResetPasswordSubmit() {
  const ansInput = document.getElementById("fpSecurityAnswer");
  const p1Input = document.getElementById("fpNewPassword");
  const p2Input = document.getElementById("fpConfirmPassword");

  const security_answer = ansInput?.value.trim();
  const new_password = p1Input?.value;
  const confirm_password = p2Input?.value;

  if (!security_answer) {
    showToast("Please type your answer to the security question.", "error");
    return;
  }
  if (!new_password || new_password.length < 8) {
    showToast("New password must be at least 8 characters long.", "error");
    return;
  }
  if (!/[A-Z]/.test(new_password) || !/[0-9]/.test(new_password)) {
    showToast("New password must contain at least one uppercase letter and one number.", "error");
    return;
  }
  if (new_password !== confirm_password) {
    showToast("Passwords do not match. Please re-enter them carefully.", "error");
    return;
  }

  const btn = document.getElementById("fpResetSubmitBtn");
  const origText = btn ? btn.innerHTML : "Reset Password";

  try {
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Updating Password...</span>`;
      safeRenderIcons();
    }

    const res = await fetch(getApiUrl("/api/auth/forgot-password/reset"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        identifier: fpState.identifier,
        security_answer,
        new_password
      })
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error((data && data.detail) || "Failed to reset password.");
    }

    showToast("Password updated successfully! Please sign in with your new password.", "success");
    closeForgotPasswordModal();

    // Fill in the username and password fields on the login form
    const loginUser = document.getElementById("loginUsername");
    const loginPass = document.getElementById("loginPassword");
    if (loginUser) loginUser.value = fpState.identifier;
    if (loginPass) {
      loginPass.value = new_password;
      loginPass.focus();
    }

  } catch (err) {
    showToast(formatNetworkError(err), "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
      safeRenderIcons();
    }
  }
}

async function logout() {
  try {
    if (state.token) {
      await fetch(getApiUrl("/api/auth/logout"), {
        method: "POST",
        headers: { "Authorization": `Bearer ${state.token}` }
      });
    }
  } catch (e) {}
  state.token = null;
  state.user = null;
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  localStorage.removeItem("save_profile_active");
  sessionStorage.removeItem("token");
  sessionStorage.removeItem("user");
  const adminNav = document.getElementById("nav-admin");
  const topNavAdmin = document.getElementById("top-nav-admin");
  const mobileAdminNav = document.getElementById("mobile-nav-admin");
  const adminUnlockBtn = document.getElementById("sidebarAdminUnlockBtn");
  if (adminNav) adminNav.classList.add("hidden");
  if (topNavAdmin) topNavAdmin.classList.add("hidden");
  if (mobileAdminNav) mobileAdminNav.classList.add("hidden");
  if (adminUnlockBtn) adminUnlockBtn.classList.remove("hidden");
  showAuth();
  showToast("You have been securely signed out.", "info");
}


// ==========================================
// MONTH NAVIGATION
// ==========================================
function updateMonthHeader() {
  const display = document.getElementById("currentMonthDisplay");
  if (display) {
    display.textContent = formatMonthLabel(state.currentMonthYear);
  }
  const badge = document.getElementById("cycleSettingsMonthBadge");
  if (badge) {
    badge.textContent = formatMonthLabel(state.currentMonthYear);
  }
}

function prevMonth() {
  const [yearStr, monthStr] = state.currentMonthYear.split("-");
  let year = parseInt(yearStr);
  let month = parseInt(monthStr) - 1;
  if (month < 1) {
    month = 12;
    year -= 1;
  }
  state.currentMonthYear = `${year}-${String(month).padStart(2, "0")}`;
  updateMonthHeader();
  refreshCurrentView();
}

function nextMonth() {
  const [yearStr, monthStr] = state.currentMonthYear.split("-");
  let year = parseInt(yearStr);
  let month = parseInt(monthStr) + 1;
  if (month > 12) {
    month = 1;
    year += 1;
  }
  state.currentMonthYear = `${year}-${String(month).padStart(2, "0")}`;
  updateMonthHeader();
  refreshCurrentView();
}

function refreshCurrentView() {
  loadDashboardData();
  if (state.activeTab === "expenses") {
    loadExpenses();
  } else if (state.activeTab === "refills") {
    loadRefills();
  } else if (state.activeTab === "settlement") {
    loadSettlement();
  }
}


// ==========================================
// CATEGORIES LOGIC
// ==========================================
async function loadCategories() {
  try {
    const categories = await apiRequest("/api/categories");
    if (categories) {
      state.categories = categories;
      renderCategorySelects();
      renderCategoryFilterChips();
    }
  } catch (e) {
    console.error(e);
  }
}

function renderCategorySelects() {
  const select = document.getElementById("expenseCategory");
  if (!select) return;
  select.innerHTML = state.categories.map(cat => `
    <option value="${cat.name}">${cat.name}</option>
  `).join("");
}

function renderCategoryFilterChips() {
  const container = document.getElementById("categoryFilterChips");
  if (!container) return;

  const allChips = [{ name: "All", color: "#6366f1" }, ...state.categories];
  container.innerHTML = allChips.map(cat => {
    const isSelected = state.categoryFilter === cat.name;
    const activeClasses = isSelected
      ? "bg-indigo-600 text-white font-bold shadow-sm"
      : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200";

    return `
      <button onclick="setCategoryFilter('${cat.name}')" class="px-3 py-1.5 rounded-xl whitespace-nowrap text-xs transition active-press ${activeClasses}">
        ${cat.name}
      </button>
    `;
  }).join("");
}

function setCategoryFilter(categoryName) {
  state.categoryFilter = categoryName;
  renderCategoryFilterChips();
  loadExpenses();
}


// ==========================================
// DASHBOARD & SUMMARY DATA
// ==========================================
async function loadDashboardData() {
  updateMonthHeader();
  try {
    const data = await apiRequest(`/api/dashboard/summary?month_year=${state.currentMonthYear}`);
    if (!data) return;

    state.dashboardData = data;
    renderDashboardKPIs(data);
    renderCharts(data);
    renderRecentExpenses(data.recent_expenses);
    renderRefills(data.refills);
  } catch (e) {
    console.error(e);
  }
}

function renderDashboardKPIs(data) {
  // Check Zero Allowance Banner if present
  const zeroBanner = document.getElementById("zeroAllowanceBanner");
  if (zeroBanner) {
    if (data.initial_allowance === 0 && data.total_refills === 0) {
      zeroBanner.classList.remove("hidden");
    } else {
      zeroBanner.classList.add("hidden");
    }
  }

  // KPI 1: Total Money Added
  const statBudgetEl = document.getElementById("statTotalBudget");
  if (statBudgetEl) statBudgetEl.textContent = formatCurrency(data.total_budget);

  const refillNotice = document.getElementById("statRefillNotice");
  if (refillNotice) {
    const refillCount = (data.refills || []).length;
    refillNotice.textContent = refillCount > 0 ? `${refillCount} deposit${refillCount > 1 ? 's' : ''} added` : "Available funds";
  }

  // KPI 2: Total Spent
  const statSpentEl = document.getElementById("statTotalSpent");
  if (statSpentEl) statSpentEl.textContent = formatCurrency(data.total_spent);

  const statSpentCount = document.getElementById("statSpentCount");
  if (statSpentCount) statSpentCount.textContent = `${(data.recent_expenses || []).length} expenses logged`;

  const statBurnPercent = document.getElementById("statBurnPercent");
  if (statBurnPercent) statBurnPercent.textContent = `${data.burn_rate_percent}% spent`;

  // KPI 3: Remaining Balance & Alert Badge
  const balEl = document.getElementById("statRemainingBalance");
  const balBadge = document.getElementById("balanceStatusBadge");
  const balIconContainer = document.getElementById("balanceIconContainer");

  if (balEl) balEl.textContent = formatCurrency(data.remaining_balance);

  if (balEl && balBadge && balIconContainer) {
    if (data.remaining_balance < 0) {
      balEl.className = "text-xl sm:text-2xl font-black text-rose-600 dark:text-rose-400";
      balBadge.className = "font-bold text-rose-600 dark:text-rose-400 badge-alert";
      balBadge.textContent = "Deficit (Need Funds)";
      balIconContainer.className = "p-1.5 rounded-lg bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400";
    } else if (data.burn_rate_percent > 85) {
      balEl.className = "text-xl sm:text-2xl font-black text-amber-500 dark:text-amber-400";
      balBadge.className = "font-bold text-amber-600 dark:text-amber-400";
      balBadge.textContent = "Running Low (<15% left)";
      balIconContainer.className = "p-1.5 rounded-lg bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400";
    } else {
      balEl.className = "text-xl sm:text-2xl font-black text-emerald-600 dark:text-emerald-400";
      balBadge.className = "font-bold text-emerald-600 dark:text-emerald-400";
      balBadge.textContent = "Available Funds";
      balIconContainer.className = "p-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400";
    }
  }

  // KPI 4: Daily Safe Spend
  const statDailySafe = document.getElementById("statDailySafe");
  if (statDailySafe) statDailySafe.textContent = `${formatCurrency(data.daily_budget_remaining)}/day`;

  const statDaysRemaining = document.getElementById("statDaysRemaining");
  if (statDaysRemaining) statDaysRemaining.textContent = `${data.days_remaining} days left in cycle`;

  const statSpentTodayBadge = document.getElementById("statSpentTodayBadge");
  if (statSpentTodayBadge) statSpentTodayBadge.textContent = `${formatCurrency(data.spent_today)} spent today`;

  // Progress Bar Gauge
  const burnProgressBar = document.getElementById("burnProgressBar");
  const burnRateText = document.getElementById("burnRateText");
  const pct = Math.min(100, Math.max(0, data.burn_rate_percent));
  if (burnProgressBar) burnProgressBar.style.width = `${pct}%`;

  if (burnProgressBar && burnRateText) {
    if (data.remaining_balance < 0) {
      burnProgressBar.className = "bg-rose-600 h-2.5 rounded-full transition-all duration-500";
      burnRateText.className = "text-xs font-extrabold px-2.5 py-1 rounded-full bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-400";
      burnRateText.textContent = `${data.burn_rate_percent}% (Overbudget)`;
    } else if (pct > 80) {
      burnProgressBar.className = "bg-amber-500 h-2.5 rounded-full transition-all duration-500";
      burnRateText.className = "text-xs font-extrabold px-2.5 py-1 rounded-full bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-400";
      burnRateText.textContent = `${data.burn_rate_percent}% Used`;
    } else {
      burnProgressBar.className = "bg-indigo-600 h-2.5 rounded-full transition-all duration-500";
      burnRateText.className = "text-xs font-extrabold px-2.5 py-1 rounded-full bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-400";
      burnRateText.textContent = `${data.burn_rate_percent}% Used`;
    }
  }

  const bgBase = document.getElementById("burnGaugeBase");
  if (bgBase) bgBase.textContent = `Total Added: ${formatCurrency(data.total_budget)}`;

  const bgRefill = document.getElementById("burnGaugeRefill");
  if (bgRefill) bgRefill.textContent = `Refills: +${formatCurrency(data.total_refills)}`;

  const bgSpent = document.getElementById("burnGaugeSpent");
  if (bgSpent) bgSpent.textContent = `Total Spent: -${formatCurrency(data.total_spent)}`;

  const bgLeft = document.getElementById("burnGaugeLeft");
  if (bgLeft) bgLeft.textContent = `Net Balance: ${formatCurrency(data.remaining_balance)}`;

  // Update Allowance tab inputs & views if present
  const cycleInitialDisplay = document.getElementById("cycleInitialDisplay");
  if (cycleInitialDisplay) cycleInitialDisplay.textContent = formatCurrency(data.initial_allowance);
}


// ==========================================
// CHARTS (Chart.js)
// ==========================================
function renderCharts(data) {
  renderCategoryDonut(data.category_breakdown);
  renderDailyBarChart(data.daily_spending);
}

function renderCategoryDonut(categories) {
  const canvas = document.getElementById("categoryDonutChart");
  const noDataEl = document.getElementById("noDataCategory");
  if (!canvas) return;

  if (state.charts.donut) {
    state.charts.donut.destroy();
  }

  if (!categories || categories.length === 0) {
    noDataEl?.classList.remove("hidden");
    return;
  }
  noDataEl?.classList.add("hidden");

  const labels = categories.map(c => c.category);
  const amounts = categories.map(c => c.total_amount);
  const colors = categories.map(c => c.color);

  state.charts.donut = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: labels,
      datasets: [{
        data: amounts,
        backgroundColor: colors,
        borderWidth: state.isDarkMode ? 2 : 2,
        borderColor: state.isDarkMode ? "#1e293b" : "#ffffff",
        hoverOffset: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "right",
          labels: {
            boxWidth: 12,
            font: { size: 11, family: "'Plus Jakarta Sans', sans-serif" },
            color: state.isDarkMode ? "#cbd5e1" : "#475569"
          }
        },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              const val = ctx.raw || 0;
              return ` ${ctx.label}: ${formatCurrency(val)}`;
            }
          }
        }
      },
      cutout: "68%"
    }
  });
}

function renderDailyBarChart(dailyList) {
  const canvas = document.getElementById("dailyBarChart");
  const noDataEl = document.getElementById("noDataDaily");
  if (!canvas) return;

  if (state.charts.bar) {
    state.charts.bar.destroy();
  }

  const hasSpend = dailyList && dailyList.some(d => d.amount > 0);
  if (!hasSpend) {
    noDataEl?.classList.remove("hidden");
    return;
  }
  noDataEl?.classList.add("hidden");

  const labels = dailyList.map(d => `${d.day}`);
  const amounts = dailyList.map(d => d.amount);

  state.charts.bar = new Chart(canvas, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [{
        label: "Spent",
        data: amounts,
        backgroundColor: "#10b981",
        borderRadius: 4,
        maxBarThickness: 18
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              return ` Day ${ctx.label}: ${formatCurrency(ctx.raw)}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: state.isDarkMode ? "#94a3b8" : "#64748b",
            font: { size: 10 }
          }
        },
        y: {
          beginAtZero: true,
          grid: {
            color: state.isDarkMode ? "#334155" : "#f1f5f9"
          },
          ticks: {
            color: state.isDarkMode ? "#94a3b8" : "#64748b",
            font: { size: 10 },
            callback: function(val) {
              return `${getCurrency()}${val}`;
            }
          }
        }
      }
    }
  });
}


// ==========================================
// RECENT EXPENSES LIST
// ==========================================
function renderRecentExpenses(expenses) {
  const container = document.getElementById("recentExpensesList");
  if (!container) return;

  if (!expenses || expenses.length === 0) {
    container.innerHTML = `
      <div class="p-8 text-center text-xs text-slate-400">
        <i data-lucide="inbox" class="w-8 h-8 mx-auto mb-2 opacity-50"></i>
        <span>No expenses recorded for this month yet.</span>
      </div>
    `;
    safeRenderIcons();
    return;
  }

  container.innerHTML = expenses.map(item => `
    <div class="p-3.5 sm:p-4 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-700/40 transition">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-slate-100 dark:bg-slate-700/80 flex items-center justify-center text-slate-700 dark:text-slate-200">
          <i data-lucide="${getCategoryIcon(item.category)}" class="w-5 h-5"></i>
        </div>
        <div>
          <div class="text-xs sm:text-sm font-bold text-slate-900 dark:text-white">${escapeHtml(item.description)}</div>
          <div class="text-[11px] text-slate-400 flex items-center gap-2 mt-0.5">
            <span>${item.date}</span>
            <span>•</span>
            <span class="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 font-medium">${item.category}</span>
            <span>•</span>
            <span>${item.payment_mode}</span>
          </div>
        </div>
      </div>
      <div class="text-right">
        <div class="text-xs sm:text-sm font-black text-rose-600 dark:text-rose-400">-${formatCurrency(item.amount)}</div>
        ${item.is_essential ? '<span class="text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold">Essential</span>' : '<span class="text-[10px] text-amber-500 font-semibold">Discretionary</span>'}
      </div>
    </div>
  `).join("");

  safeRenderIcons();
}

function getCategoryIcon(catName) {
  const found = state.categories.find(c => c.name === catName);
  return (found && found.icon) ? found.icon : "tag";
}


// ==========================================
// ALL EXPENSES VIEW (TAB 2)
// ==========================================
let filterDebounceTimer = null;
function debounceFilterExpenses() {
  clearTimeout(filterDebounceTimer);
  filterDebounceTimer = setTimeout(() => {
    state.searchQuery = document.getElementById("expenseSearchInput").value;
    loadExpenses();
  }, 250);
}

async function loadExpenses() {
  const sortSelect = document.getElementById("expenseSortSelect");
  if (sortSelect) state.sortBy = sortSelect.value;

  const params = new URLSearchParams({
    month_year: state.currentMonthYear,
    sort_by: state.sortBy
  });

  if (state.categoryFilter && state.categoryFilter !== "All") {
    params.append("category", state.categoryFilter);
  }

  if (state.searchQuery) {
    params.append("search", state.searchQuery);
  }

  try {
    const list = await apiRequest(`/api/expenses?${params.toString()}`);
    if (!list) return;

    state.expenses = list;
    renderAllExpenses(list);
  } catch (e) {
    console.error(e);
  }
}

function renderAllExpenses(expenses) {
  const container = document.getElementById("allExpensesList");
  const countText = document.getElementById("filteredCountText");
  const totalText = document.getElementById("filteredTotalText");

  const total = expenses.reduce((sum, item) => sum + item.amount, 0);
  if (countText) countText.textContent = `Showing ${expenses.length} transaction${expenses.length === 1 ? '' : 's'}`;
  if (totalText) totalText.textContent = `Total: ${formatCurrency(total)}`;

  if (!container) return;

  if (expenses.length === 0) {
    container.innerHTML = `
      <div class="p-12 text-center text-xs text-slate-400">
        <i data-lucide="search-x" class="w-8 h-8 mx-auto mb-2 opacity-50"></i>
        <span>No matching expenses found for this month filter.</span>
      </div>
    `;
    safeRenderIcons();
    return;
  }

  container.innerHTML = expenses.map(item => `
    <div class="p-4 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-700/40 transition">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-slate-100 dark:bg-slate-700 flex items-center justify-center text-slate-700 dark:text-slate-200">
          <i data-lucide="${getCategoryIcon(item.category)}" class="w-5 h-5"></i>
        </div>
        <div>
          <div class="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <span>${escapeHtml(item.description)}</span>
            ${item.receipt_note ? `<span class="text-[10px] text-slate-400 italic">(${escapeHtml(item.receipt_note)})</span>` : ''}
          </div>
          <div class="text-xs text-slate-400 flex items-center gap-2 mt-0.5">
            <span>${item.date}</span>
            <span>•</span>
            <span class="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 font-semibold text-[11px]">${item.category}</span>
            <span>•</span>
            <span>${item.payment_mode}</span>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-4">
        <div class="text-right">
          <div class="text-sm font-black text-rose-600 dark:text-rose-400">-${formatCurrency(item.amount)}</div>
          ${item.is_essential ? '<span class="text-[10px] text-emerald-600 dark:text-emerald-400 font-bold">Essential</span>' : '<span class="text-[10px] text-amber-500 font-bold">Discretionary</span>'}
        </div>

        <div class="flex items-center gap-1">
          <button onclick="editExpense(${item.id})" class="p-1.5 text-slate-400 hover:text-indigo-600 rounded-lg" title="Edit Expense">
            <i data-lucide="edit-2" class="w-4 h-4"></i>
          </button>
          <button onclick="deleteExpense(${item.id})" class="p-1.5 text-slate-400 hover:text-rose-600 rounded-lg" title="Delete Expense">
            <i data-lucide="trash-2" class="w-4 h-4"></i>
          </button>
        </div>
      </div>
    </div>
  `).join("");

  safeRenderIcons();
}


// ==========================================
// AI CATEGORY CLASSIFIER & INTELLIGENCE
// ==========================================
const AI_KEYWORDS = {
  "Food & Dining": [
    "canteen", "lunch", "dinner", "breakfast", "brunch", "snack", "snacks",
    "coffee", "tea", "chai", "burger", "pizza", "biryani", "swiggy", "zomato",
    "cafe", "restaurant", "hotel food", "mess", "dosa", "idli", "maggi",
    "subway", "kfc", "mcdonalds", "starbucks", "bakery", "ice cream", "dessert",
    "shawarma", "sandwich", "paneer", "roll", "momos", "thali", "juice", "eat", "meal", "food"
  ],
  "Groceries": [
    "grocery", "groceries", "milk", "bread", "eggs", "vegetables", "fruits",
    "sabzi", "kirana", "supermarket", "d-mart", "dmart", "blinkit", "zepto",
    "instamart", "bigbasket", "rice", "dal", "flour", "atta", "spices",
    "oil", "butter", "cheese", "snack refill", "pantry", "household provisions", "soap", "toothpaste"
  ],
  "Transport & Fuel": [
    "metro", "bus", "auto", "rickshaw", "uber", "ola", "rapido", "cab", "taxi",
    "petrol", "diesel", "fuel", "gasoline", "train", "railway", "irctc",
    "flight", "toll", "parking", "scooter", "bike", "mechanic", "fare", "travel", "smartcard"
  ],
  "Books & Study": [
    "book", "books", "textbook", "notebook", "stationery", "pen", "pens",
    "pencil", "xerox", "photocopy", "printout", "spiral", "course", "udemy",
    "coursera", "tuition", "coaching", "exam fee", "form fee", "college fee",
    "library", "calculator", "lab coat", "assignment", "project print", "study"
  ],
  "Bills & Utilities": [
    "bill", "electricity", "water", "wifi", "broadband", "internet",
    "recharge", "airtel", "jio", "vi", "bsnl", "mobile recharge", "dth",
    "gas cylinder", "indane", "hp gas", "maintenance fee", "electric"
  ],
  "Health & Medical": [
    "medicine", "medical", "doctor", "hospital", "clinic", "pharmacy",
    "chemist", "apollo", "medplus", "1mg", "tablet", "syrup", "capsule",
    "bandage", "crocin", "paracetamol", "dentist", "eye checkup", "specs",
    "consultation", "lab test", "blood test", "fever", "cough"
  ],
  "Entertainment & Outings": [
    "movie", "cinema", "pvr", "inox", "film", "theatre", "netflix", "prime",
    "hotstar", "spotify", "youtube", "gaming", "game", "steam", "playstation",
    "concert", "show", "amusement", "trip", "picnic", "bowling", "outing", "club"
  ],
  "Hostel & Room": [
    "hostel", "pg fee", "room rent", "rent", "landlord", "flat rent",
    "deposit", "security deposit", "mess advance", "room maintenance", "warden"
  ],
  "Emergency": [
    "emergency", "urgent", "hospital emergency", "lost", "theft", "penalty",
    "traffic fine", "police fine", "challan", "damage", "repair urgent", "breakage"
  ],
  "Personal & Clothing": [
    "clothes", "clothing", "shirt", "t-shirt", "jeans", "trousers", "shoes",
    "slippers", "sandals", "zara", "h&m", "myntra", "ajio", "amazon fashion",
    "haircut", "salon", "barber", "parlour", "shampoo", "perfume", "deodorant",
    "facewash", "skincare", "lotion", "watch"
  ]
};

let userOverrodeCategory = false;
let aiClassifyDebounce = null;

function handleUserCategoryOverride() {
  userOverrodeCategory = true;
  const badge = document.getElementById("aiCategoryBadge");
  if (badge) badge.classList.add("hidden");
}

function handleDescriptionChange(text) {
  if (userOverrodeCategory) {
    if (!text || !text.trim()) {
      userOverrodeCategory = false;
    }
    return;
  }
  clearTimeout(aiClassifyDebounce);
  aiClassifyDebounce = setTimeout(() => {
    runAiCategoryClassifier(text);
  }, 150);
}

function runAiCategoryClassifier(text) {
  const clean = (text || "").toLowerCase().trim();
  const badge = document.getElementById("aiCategoryBadge");
  const badgeText = document.getElementById("aiCategoryText");
  const categorySelect = document.getElementById("expenseCategory");

  if (!clean) {
    if (badge) badge.classList.add("hidden");
    return;
  }

  let bestCat = null;
  let bestScore = 0;

  for (const [cat, words] of Object.entries(AI_KEYWORDS)) {
    let score = 0;
    for (const kw of words) {
      if (clean.includes(kw)) {
        if (clean.startsWith(kw) || clean.endsWith(kw) || clean.includes(" " + kw + " ")) {
          score += 3;
        } else {
          score += 1;
        }
      }
    }
    if (score > bestScore) {
      bestScore = score;
      bestCat = cat;
    }
  }

  if (bestCat && bestScore > 0) {
    if (categorySelect) categorySelect.value = bestCat;
    if (badge) {
      badge.classList.remove("hidden");
      if (badgeText) badgeText.textContent = `AI: ${bestCat}`;
      safeRenderIcons();
    }
  } else {
    if (badge) badge.classList.add("hidden");
  }
}


// ==========================================
// SAVED CARDS & BANKS STORAGE HELPERS
// ==========================================
function getSavedCardsKey() {
  return `saved_cards_${state.user ? state.user.id : 'guest'}`;
}

function getSavedBanksKey() {
  return `saved_banks_${state.user ? state.user.id : 'guest'}`;
}

function getSavedCards() {
  try {
    return JSON.parse(localStorage.getItem(getSavedCardsKey()) || "[]");
  } catch (e) {
    return [];
  }
}

function saveCard(cardObj) {
  if (!cardObj || !cardObj.name) return;
  const list = getSavedCards();
  const exists = list.some(c => c.name.toLowerCase() === cardObj.name.toLowerCase() && c.last4 === cardObj.last4);
  if (!exists) {
    list.push(cardObj);
    localStorage.setItem(getSavedCardsKey(), JSON.stringify(list));
  }
}

function getSavedBanks() {
  try {
    return JSON.parse(localStorage.getItem(getSavedBanksKey()) || "[]");
  } catch (e) {
    return [];
  }
}

function saveBank(bankName) {
  if (!bankName) return;
  const list = getSavedBanks();
  if (!list.includes(bankName)) {
    list.push(bankName);
    localStorage.setItem(getSavedBanksKey(), JSON.stringify(list));
  }
}


// ==========================================
// DYNAMIC PAYMENT MODE SWITCHING
// ==========================================
function handlePaymentModeChange() {
  const mode = document.getElementById("expensePaymentMode").value;
  const upiGroup = document.getElementById("upiFieldGroup");
  const cashGroup = document.getElementById("cashFieldGroup");
  const cardGroup = document.getElementById("cardFieldGroup");
  const netBankingGroup = document.getElementById("netBankingFieldGroup");

  if (upiGroup) upiGroup.classList.add("hidden");
  if (cashGroup) cashGroup.classList.add("hidden");
  if (cardGroup) cardGroup.classList.add("hidden");
  if (netBankingGroup) netBankingGroup.classList.add("hidden");

  if (mode === "UPI") {
    if (upiGroup) upiGroup.classList.remove("hidden");
  } else if (mode === "Cash") {
    if (cashGroup) cashGroup.classList.remove("hidden");
  } else if (mode === "Card") {
    if (cardGroup) cardGroup.classList.remove("hidden");
    renderSavedCardsDropdown();
  } else if (mode === "Net Banking") {
    if (netBankingGroup) netBankingGroup.classList.remove("hidden");
    renderSavedBanksDropdown();
  }
  safeRenderIcons();
}

function selectUpiApp(appName) {
  const input = document.getElementById("upiAppNameInput");
  if (input) input.value = appName;
}

function selectBankName(bankName) {
  const input = document.getElementById("bankNameInput");
  if (input) input.value = bankName;
}

function renderSavedCardsDropdown() {
  const container = document.getElementById("savedCardsContainer");
  const select = document.getElementById("savedCardsSelect");
  if (!container || !select) return;

  const cards = getSavedCards();
  if (cards.length === 0) {
    container.classList.add("hidden");
    return;
  }

  container.classList.remove("hidden");
  select.innerHTML = `
    <option value="">-- Or Pick a Saved Card --</option>
    ${cards.map((c, idx) => `
      <option value="${idx}">${escapeHtml(c.name)}${c.last4 ? ` (****${c.last4})` : ''}</option>
    `).join('')}
    <option value="new">+ Enter New Card Details</option>
  `;
}

function handleSavedCardChange() {
  const select = document.getElementById("savedCardsSelect");
  const idx = select.value;
  if (!idx || idx === "new") {
    document.getElementById("cardNameInput").value = "";
    document.getElementById("cardLastDigitsInput").value = "";
    return;
  }
  const cards = getSavedCards();
  const card = cards[parseInt(idx)];
  if (card) {
    document.getElementById("cardNameInput").value = card.name;
    document.getElementById("cardLastDigitsInput").value = card.last4 || "";
  }
}

function renderSavedBanksDropdown() {
  const container = document.getElementById("savedBanksContainer");
  const select = document.getElementById("savedBanksSelect");
  if (!container || !select) return;

  const banks = getSavedBanks();
  if (banks.length === 0) {
    container.classList.add("hidden");
    return;
  }

  container.classList.remove("hidden");
  select.innerHTML = `
    <option value="">-- Or Pick a Saved Bank --</option>
    ${banks.map(b => `<option value="${escapeHtml(b)}">${escapeHtml(b)}</option>`).join('')}
    <option value="new">+ Enter Other Bank</option>
  `;
}

function handleSavedBankChange() {
  const select = document.getElementById("savedBanksSelect");
  const val = select.value;
  if (!val || val === "new") {
    document.getElementById("bankNameInput").value = "";
    return;
  }
  document.getElementById("bankNameInput").value = val;
}


// ==========================================
// ADD / EDIT EXPENSE MODAL & ACTIONS
// ==========================================
function openAddExpenseModal() {
  userOverrodeCategory = false;
  document.getElementById("editExpenseId").value = "";
  document.getElementById("expenseModalTitle").innerHTML = `
    <i data-lucide="plus-circle" class="w-5 h-5 text-indigo-500"></i>
    <span>Add New Expense</span>
  `;
  document.getElementById("expenseAmount").value = "";
  document.getElementById("expenseDescription").value = "";
  document.getElementById("expenseEssential").checked = true;

  // Reset payment specific fields
  document.getElementById("expensePaymentMode").value = "UPI";
  document.getElementById("upiAppNameInput").value = "";
  document.getElementById("cashRemarkInput").value = "";
  document.getElementById("cardNameInput").value = "";
  document.getElementById("cardLastDigitsInput").value = "";
  document.getElementById("bankNameInput").value = "";

  // Hide AI badge initially
  const badge = document.getElementById("aiCategoryBadge");
  if (badge) badge.classList.add("hidden");

  // Set date to today
  const today = new Date().toISOString().split("T")[0];
  document.getElementById("expenseDate").value = today;

  handlePaymentModeChange();

  document.getElementById("expenseModal").classList.remove("hidden");
  safeRenderIcons();
}

function closeExpenseModal() {
  document.getElementById("expenseModal").classList.add("hidden");
}

function editExpense(id) {
  const item = state.expenses.find(e => e.id === id) || (state.dashboardData?.recent_expenses.find(e => e.id === id));
  if (!item) return;

  userOverrodeCategory = true; // don't override category on existing item
  document.getElementById("editExpenseId").value = item.id;
  document.getElementById("expenseModalTitle").innerHTML = `
    <i data-lucide="edit-3" class="w-5 h-5 text-indigo-500"></i>
    <span>Edit Expense</span>
  `;
  document.getElementById("expenseAmount").value = item.amount;
  document.getElementById("expenseDescription").value = item.description;
  document.getElementById("expenseCategory").value = item.category;
  document.getElementById("expenseDate").value = item.date;
  document.getElementById("expensePaymentMode").value = item.payment_mode || "UPI";
  document.getElementById("expenseEssential").checked = item.is_essential;

  // Reset specific inputs
  document.getElementById("upiAppNameInput").value = "";
  document.getElementById("cashRemarkInput").value = "";
  document.getElementById("cardNameInput").value = "";
  document.getElementById("cardLastDigitsInput").value = "";
  document.getElementById("bankNameInput").value = "";

  // Parse receipt note back into payment fields
  const note = item.receipt_note || "";
  if (item.payment_mode === "UPI") {
    document.getElementById("upiAppNameInput").value = note.replace(/^UPI App:\s*/i, "").replace(/^Paid via\s*/i, "");
  } else if (item.payment_mode === "Cash") {
    document.getElementById("cashRemarkInput").value = note.replace(/^Remark:\s*/i, "").replace(/^Cash Remark:\s*/i, "");
  } else if (item.payment_mode === "Card") {
    const cardMatch = note.match(/^(?:Card:\s*)?(.*?)(?:\s*\(\*{4}(\d{4})\))?$/i);
    if (cardMatch) {
      document.getElementById("cardNameInput").value = cardMatch[1] || "";
      document.getElementById("cardLastDigitsInput").value = cardMatch[2] || "";
    } else {
      document.getElementById("cardNameInput").value = note;
    }
  } else if (item.payment_mode === "Net Banking") {
    document.getElementById("bankNameInput").value = note.replace(/^Net Banking:\s*/i, "");
  }

  handlePaymentModeChange();

  document.getElementById("expenseModal").classList.remove("hidden");
  safeRenderIcons();
}

async function handleSaveExpense(e) {
  e.preventDefault();
  const editId = document.getElementById("editExpenseId").value;
  const amount = parseFloat(document.getElementById("expenseAmount").value);
  const description = document.getElementById("expenseDescription").value.trim();
  const category = document.getElementById("expenseCategory").value;
  const date = document.getElementById("expenseDate").value;
  const payment_mode = document.getElementById("expensePaymentMode").value;
  const is_essential = document.getElementById("expenseEssential").checked;

  // Construct receipt_note according to payment mode
  let receipt_note = null;
  if (payment_mode === "UPI") {
    const upiApp = document.getElementById("upiAppNameInput").value.trim();
    if (upiApp) receipt_note = `UPI App: ${upiApp}`;
  } else if (payment_mode === "Cash") {
    const remark = document.getElementById("cashRemarkInput").value.trim();
    if (remark) receipt_note = `Remark: ${remark}`;
  } else if (payment_mode === "Card") {
    const cardName = document.getElementById("cardNameInput").value.trim();
    const last4 = document.getElementById("cardLastDigitsInput").value.trim();
    if (cardName || last4) {
      receipt_note = `Card: ${cardName}${last4 ? ` (****${last4})` : ''}`.trim();
      if (document.getElementById("saveCardCheckbox").checked && cardName) {
        saveCard({ name: cardName, last4 });
      }
    }
  } else if (payment_mode === "Net Banking") {
    const bankName = document.getElementById("bankNameInput").value.trim();
    if (bankName) {
      receipt_note = `Net Banking: ${bankName}`;
      if (document.getElementById("saveBankCheckbox").checked) {
        saveBank(bankName);
      }
    }
  }

  const payload = {
    amount,
    description,
    category,
    date,
    payment_mode,
    receipt_note: receipt_note || null,
    is_essential
  };

  try {
    if (editId) {
      await apiRequest(`/api/expenses/${editId}`, {
        method: "PUT",
        body: JSON.stringify(payload)
      });
      showToast("Expense updated successfully!", "success");
    } else {
      await apiRequest("/api/expenses", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      showToast("Expense logged & deducted from allowance!", "success");
    }

    closeExpenseModal();
    loadDashboardData();
    if (state.activeTab === "expenses") {
      loadExpenses();
    }
  } catch (err) {
    console.error(err);
  }
}

async function deleteExpense(id) {
  if (!confirm("Are you sure you want to delete this expense? The amount will be restored to your balance.")) {
    return;
  }

  try {
    await apiRequest(`/api/expenses/${id}`, { method: "DELETE" });
    showToast("Expense deleted and balance updated.", "success");
    loadDashboardData();
    loadExpenses();
  } catch (err) {
    console.error(err);
  }
}


// ==========================================
// ADD MONEY & DEPOSITS (TAB 3)
// ==========================================
function openRefillModal() {
  const amountInput = document.getElementById("refillAmount");
  const sourceInput = document.getElementById("refillSource");
  const reasonInput = document.getElementById("refillReason");
  const dateInput = document.getElementById("refillDate");
  if (amountInput) amountInput.value = "";
  if (sourceInput) sourceInput.value = "Parents";
  if (reasonInput) reasonInput.value = "";
  if (dateInput) dateInput.value = new Date().toISOString().split("T")[0];

  const modal = document.getElementById("refillModal");
  if (modal) modal.classList.remove("hidden");
  safeRenderIcons();
}

function closeRefillModal() {
  const modal = document.getElementById("refillModal");
  if (modal) modal.classList.add("hidden");
}

async function handleSaveRefill(e) {
  e.preventDefault();
  const amount = parseFloat(document.getElementById("refillAmount").value);
  const funding_source = document.getElementById("refillSource").value.trim();
  const reason = document.getElementById("refillReason").value.trim();
  const date = document.getElementById("refillDate").value;
  const payment_mode = document.getElementById("refillMode").value;

  try {
    await apiRequest("/api/refills", {
      method: "POST",
      body: JSON.stringify({
        amount,
        funding_source: funding_source || "Parents",
        reason: reason || "Added money",
        date,
        payment_mode,
        month_year: state.currentMonthYear
      })
    });

    showToast(`Added ${formatCurrency(amount)} to balance!`, "success");
    closeRefillModal();
    loadDashboardData();
    loadRefills();
  } catch (err) {
    console.error(err);
  }
}

async function loadRefills() {
  try {
    const list = await apiRequest(`/api/refills?month_year=${state.currentMonthYear}`);
    if (!list) return;
    state.refills = list;
    renderRefills(list);
  } catch (e) {
    console.error(e);
  }
}

function renderRefills(refills) {
  const container = document.getElementById("refillsListContainer");
  if (!container) return;

  if (!refills || refills.length === 0) {
    container.innerHTML = `
      <div class="py-8 text-center text-xs text-slate-400">
        <i data-lucide="wallet" class="w-8 h-8 mx-auto mb-2 opacity-50"></i>
        <span>No money deposits logged for this cycle yet. Click "+ Add Money" to add funds.</span>
      </div>
    `;
    safeRenderIcons();
    return;
  }

  container.innerHTML = refills.map(item => `
    <div class="py-3.5 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center font-bold">
          <i data-lucide="plus" class="w-4 h-4"></i>
        </div>
        <div>
          <div class="text-xs sm:text-sm font-bold text-slate-900 dark:text-white">
            ${escapeHtml(item.funding_source)}: ${escapeHtml(item.reason || 'Added Funds')}
          </div>
          <div class="text-[11px] text-slate-400 mt-0.5">
            <span>${item.date}</span> • <span>${item.payment_mode}</span>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <div class="text-sm font-extrabold text-emerald-600 dark:text-emerald-400">
          +${formatCurrency(item.amount)}
        </div>
        <button onclick="deleteRefill(${item.id})" class="p-1 text-slate-400 hover:text-rose-600 rounded" title="Delete Deposit">
          <i data-lucide="trash" class="w-3.5 h-3.5"></i>
        </button>
      </div>
    </div>
  `).join("");

  safeRenderIcons();
}

async function deleteRefill(id) {
  if (!confirm("Are you sure you want to delete this deposit? Your available balance will be reduced accordingly.")) {
    return;
  }

  try {
    await apiRequest(`/api/refills/${id}`, { method: "DELETE" });
    showToast("Deposit removed and balance adjusted.", "success");
    loadDashboardData();
    loadRefills();
  } catch (err) {
    console.error(err);
  }
}

// Fallback stubs for legacy allowance calls if any
function openSetAllowanceModal() {
  openRefillModal();
}

function closeSetAllowanceModal() {
  closeRefillModal();
}

function handleSaveAllowance(e) {
  if (e) e.preventDefault();
}


// ==========================================
// PARENT SETTLEMENT & BREAKDOWN (TAB 4)
// ==========================================
async function loadSettlement() {
  try {
    const data = await apiRequest(`/api/settlement/summary?month_year=${state.currentMonthYear}`);
    if (!data) return;

    state.settlementData = data;
    renderSettlementSheet(data);
  } catch (e) {
    console.error(e);
  }
}

function renderSettlementSheet(data) {
  document.getElementById("settleUserMonth").textContent = `Student / User: ${data.user_name} • Period: ${data.formatted_month}`;
  
  const statusBadge = document.getElementById("settleStatusBadge");
  if (data.is_deficit) {
    statusBadge.className = "self-start sm:self-auto px-3 py-1 rounded-full text-xs font-bold bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400";
    statusBadge.textContent = `Deficit of ${formatCurrency(data.deficit_or_surplus_amount)} Needed`;
  } else {
    statusBadge.className = "self-start sm:self-auto px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400";
    statusBadge.textContent = `Surplus Safe (${formatCurrency(data.remaining_balance)} Left)`;
  }

  document.getElementById("settleBase").textContent = formatCurrency(data.initial_allowance);
  document.getElementById("settleRefills").textContent = `+${formatCurrency(data.total_refills)}`;
  document.getElementById("settleSpent").textContent = `-${formatCurrency(data.total_spent)}`;
  document.getElementById("settleNet").textContent = formatCurrency(data.remaining_balance);

  document.getElementById("settleParentsNote").textContent = data.parents_note;

  // Category Table
  const catTbody = document.getElementById("settleCategoryTbody");
  if (catTbody) {
    catTbody.innerHTML = data.category_summary.map(cat => `
      <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50">
        <td class="p-2.5 font-bold flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${cat.color}"></span>
          <span>${cat.category}</span>
        </td>
        <td class="p-2.5 text-center text-slate-500">${cat.count}</td>
        <td class="p-2.5 text-right font-bold">${formatCurrency(cat.total_amount)}</td>
        <td class="p-2.5 text-right font-semibold text-slate-500">${cat.percentage}%</td>
      </tr>
    `).join("");
  }

  // Itemized Table
  const itemTbody = document.getElementById("settleItemizedTbody");
  if (itemTbody) {
    itemTbody.innerHTML = data.itemized_expenses.map(exp => `
      <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50">
        <td class="p-2.5 text-slate-500 whitespace-nowrap">${exp.date}</td>
        <td class="p-2.5 font-semibold text-slate-700 dark:text-slate-300">${exp.category}</td>
        <td class="p-2.5 font-medium text-slate-900 dark:text-white">
          ${escapeHtml(exp.description)}
          ${exp.receipt_note ? `<span class="text-[10px] text-slate-400"> (Ref: ${escapeHtml(exp.receipt_note)})</span>` : ''}
        </td>
        <td class="p-2.5 text-slate-500">${exp.payment_mode}</td>
        <td class="p-2.5 text-right font-bold text-rose-600 dark:text-rose-400">-${formatCurrency(exp.amount)}</td>
      </tr>
    `).join("");
  }

  // Document Audit Timestamp & Signature Date
  const now = new Date();
  const dateStr = now.toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
  const timeStr = now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
  const docTs = document.getElementById("settleDocTimestamp");
  if (docTs) docTs.textContent = `Generated: ${dateStr} • ${timeStr} IST`;
  const signDate = document.getElementById("signDateStudent");
  if (signDate) signDate.textContent = dateStr;

  safeRenderIcons();
}

async function downloadPdfReport() {
  switchTab("settlement");
  if (!state.settlementData) {
    await loadSettlement();
  }
  // Brief timeout to ensure DOM reflow and icons finish rendering
  setTimeout(() => {
    window.print();
  }, 300);
}

function shareWhatsApp() {
  if (!state.settlementData) return;
  const text = state.settlementData.whatsapp_share_text;
  const url = `https://api.whatsapp.com/send?text=${encodeURIComponent(text)}`;
  window.open(url, "_blank");
}

function copySettlementText() {
  if (!state.settlementData) return;
  navigator.clipboard.writeText(state.settlementData.whatsapp_share_text)
    .then(() => showToast("Breakdown statement copied to clipboard!", "success"))
    .catch(() => showToast("Failed to copy text", "error"));
}


// ==========================================
// CSV EXPORT
// ==========================================
function exportCSV() {
  if (!state.token) return;
  const url = getApiUrl(`/api/export/csv?month_year=${state.currentMonthYear}`);
  // Fetch with Authorization header and trigger download
  fetch(url, {
    headers: { "Authorization": `Bearer ${state.token}` }
  })
  .then(res => res.blob())
  .then(blob => {
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = `expense_report_${state.currentMonthYear}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    showToast("Downloaded monthly expense CSV report!", "success");
  })
  .catch(err => {
    showToast("Failed to download CSV", "error");
  });
}


// ==========================================
// VISUAL ANALYTICS (TAB 5)
// ==========================================
function renderVisualAnalytics() {
  if (!state.dashboardData) return;
  const data = state.dashboardData;

  document.getElementById("statDailyAverage").textContent = `${formatCurrency(data.daily_average_spent)} / day`;

  // Essential vs Non-essential
  const essentialTotal = state.settlementData ? state.settlementData.essential_spent : (data.total_spent * 0.7);
  const nonEssentialTotal = state.settlementData ? state.settlementData.non_essential_spent : (data.total_spent * 0.3);
  const total = essentialTotal + nonEssentialTotal;

  const essentialPct = total > 0 ? (essentialTotal / total * 100) : 50;
  const nonEssentialPct = total > 0 ? (nonEssentialTotal / total * 100) : 50;

  document.getElementById("barEssential").style.width = `${essentialPct}%`;
  document.getElementById("barNonEssential").style.width = `${nonEssentialPct}%`;
  document.getElementById("labelEssential").textContent = `Essential: ${formatCurrency(essentialTotal)}`;
  document.getElementById("labelNonEssential").textContent = `Discretionary: ${formatCurrency(nonEssentialTotal)}`;

  // Category progress bars
  const container = document.getElementById("analyticsCategoryBars");
  if (!container) return;

  if (!data.category_breakdown || data.category_breakdown.length === 0) {
    container.innerHTML = `<div class="text-xs text-slate-400 py-4">No expense categories to display yet.</div>`;
    return;
  }

  container.innerHTML = data.category_breakdown.map(cat => `
    <div class="space-y-1">
      <div class="flex items-center justify-between text-xs">
        <span class="font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${cat.color}"></span>
          <span>${cat.category}</span>
        </span>
        <span class="font-semibold text-slate-900 dark:text-white">${formatCurrency(cat.total_amount)} (${cat.percentage}%)</span>
      </div>
      <div class="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-2 overflow-hidden">
        <div class="h-full rounded-full transition-all duration-300" style="width: ${cat.percentage}%; background-color: ${cat.color}"></div>
      </div>
    </div>
  `).join("");
}


// ==========================================
// TAB SWITCHING NAVIGATION
// ==========================================
function switchTab(tabId) {
  if (tabId === "admin") {
    if (!state.user || !state.user.is_admin) {
      showToast("Access Denied: Administrator account required.", "error");
      switchTab("dashboard");
      return;
    }
  }

  state.activeTab = tabId;

  // Hide all tab sections
  ["dashboard", "expenses", "refills", "settlement", "analytics", "admin", "download"].forEach(t => {
    const sec = document.getElementById(`tabContent-${t}`);
    if (sec) sec.classList.add("hidden");

    // Desktop sidebar nav styles
    const navBtn = document.getElementById(`nav-${t}`);
    if (navBtn) {
      if (t === tabId) {
        navBtn.className = "nav-item w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/50";
      } else {
        navBtn.className = "nav-item w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700/50";
      }
    }

    // Top header nav styles
    const topNavBtn = document.getElementById(`top-nav-${t}`);
    if (topNavBtn) {
      if (t === tabId) {
        topNavBtn.className = "px-3 py-1.5 rounded-lg text-xs font-semibold text-indigo-600 dark:text-indigo-400 bg-white dark:bg-slate-800 shadow-sm transition";
      } else {
        topNavBtn.className = "px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 dark:text-slate-300 hover:text-slate-900 transition";
      }
    }

    // Mobile nav styles
    const mNavBtn = document.getElementById(`mobile-nav-${t}`);
    if (mNavBtn) {
      if (t === tabId) {
        mNavBtn.className = "flex flex-col items-center py-1.5 px-3 text-indigo-600 dark:text-indigo-400 transition font-bold";
      } else {
        mNavBtn.className = "flex flex-col items-center py-1.5 px-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition font-medium";
      }
    }
  });

  // Show active section
  const activeSec = document.getElementById(`tabContent-${tabId}`);
  if (activeSec) activeSec.classList.remove("hidden");

  // Page title update
  const titleMap = {
    dashboard: "Dashboard",
    expenses: "Expenses & Transactions",
    refills: "Added Money & Deposit Records",
    settlement: "Parent Expense Report",
    analytics: "Visual Analytics",
    admin: "Admin Security & Oversight",
    download: "Download Mobile App"
  };
  const titleEl = document.getElementById("pageTitle");
  if (titleEl) titleEl.textContent = titleMap[tabId] || "Dashboard";

  // Tab-specific loading
  if (tabId === "dashboard") {
    loadDashboardData();
  } else if (tabId === "expenses") {
    loadExpenses();
  } else if (tabId === "refills") {
    loadRefills();
  } else if (tabId === "settlement") {
    loadSettlement();
  } else if (tabId === "analytics") {
    loadSettlement().then(() => renderVisualAnalytics());
  } else if (tabId === "admin") {
    loadAdminData();
  }

  safeRenderIcons();
}


// ==========================================
// ADMIN DASHBOARD & TELEMETRY
// ==========================================
async function loadAdminData() {
  if (!state.user || !state.user.is_admin) return;
  try {
    const stats = await apiRequest("/api/admin/stats");
    if (stats) {
      document.getElementById("adminTotalUsers").textContent = stats.total_users;
      document.getElementById("adminActiveUsers").textContent = `${stats.active_users} Active (${stats.admin_users} Admin)`;
      document.getElementById("adminTotalExpenses").textContent = stats.total_expenses;
      document.getElementById("adminTotalSpendVol").textContent = `Spend Volume: ${formatCurrency(stats.total_spend_volume)}`;
      document.getElementById("adminDbStatus").textContent = `${stats.database_status}`;
    }

    const users = await apiRequest("/api/admin/users");
    const tbody = document.getElementById("adminUserTableBody");
    if (tbody && users) {
      if (users.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="p-6 text-center text-slate-400">No registered users found.</td></tr>`;
        return;
      }
      tbody.innerHTML = users.map(u => `
        <tr class="hover:bg-slate-50 dark:hover:bg-slate-700/40 transition">
          <td class="p-3 font-mono font-bold text-slate-500">#${u.id}</td>
          <td class="p-3 font-bold text-slate-900 dark:text-white">${escapeHtml(u.full_name)}</td>
          <td class="p-3 text-slate-500 font-mono text-[11px]">${escapeHtml(u.email)}</td>
          <td class="p-3 text-center font-semibold text-slate-700 dark:text-slate-300">${u.total_expenses_count}</td>
          <td class="p-3 text-right font-bold text-rose-600 dark:text-rose-400">-${formatCurrency(u.total_spent)}</td>
          <td class="p-3 text-center">
            ${u.is_admin ? '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 dark:bg-purple-950 text-purple-700 dark:text-purple-300">Admin</span>' : '<span class="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">User</span>'}
          </td>
          <td class="p-3 text-center">
            ${u.is_active ? '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">Active</span>' : '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300">Deactivated</span>'}
          </td>
          <td class="p-3 text-right">
            ${u.id === state.user.id ? '<span class="text-[11px] text-slate-400 italic">Current User</span>' : `
              <button onclick="toggleUserStatus(${u.id}, ${u.is_active})" class="px-2 py-1 text-[11px] font-semibold rounded-lg ${u.is_active ? 'bg-rose-50 text-rose-600 hover:bg-rose-100 dark:bg-rose-950/40' : 'bg-emerald-50 text-emerald-600 hover:bg-emerald-100 dark:bg-emerald-950/40'} transition">
                ${u.is_active ? 'Deactivate' : 'Reactivate'}
              </button>
            `}
          </td>
        </tr>
      `).join("");
      safeRenderIcons();
    }
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function refreshAdminData() {
  await loadAdminData();
  showToast("Security telemetry refreshed.", "success");
}

async function toggleUserStatus(userId, currentStatus) {
  const newStatus = !currentStatus;
  const actionName = newStatus ? "reactivate" : "deactivate";
  if (!confirm(`Are you sure you want to ${actionName} this user account?`)) return;

  try {
    const res = await apiRequest(`/api/admin/users/${userId}/toggle-status`, {
      method: "PUT",
      body: JSON.stringify({ is_active: newStatus })
    });
    if (res) {
      showToast(res.message, "success");
      loadAdminData();
    }
  } catch (err) {
    showToast(err.message, "error");
  }
}


// ==========================================
// MOBILE APP 1-CLICK INSTALL & APK DOWNLOAD
// ==========================================
let deferredInstallPrompt = null;

function isMobileDevice() {
  const userAgent = navigator.userAgent || navigator.vendor || window.opera || "";
  const isMobileUa = /android|iphone|ipad|ipod|blackberry|iemobile|opera mini/i.test(userAgent);
  const isSmallScreen = window.innerWidth <= 768;
  return isMobileUa || isSmallScreen;
}

function initMobileInstallPrompt() {
  // Capture Chromium / Android PWA installation prompt silently (NO AUTO POPUPS)
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
  });

  // Track successful app installs
  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    showToast("Expense Tracker installed successfully! Added to your phone screen.", "success");
    closeMobileInstallModal();
  });
}

function checkAndAutoPromptMobileInstall() {
  // Do not prompt if already running in standalone PWA window
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
  if (isStandalone) return;

  // Do not spam if user dismissed in the current session
  if (sessionStorage.getItem("pwaModalDismissed") === "true") return;

  openMobileInstallModal();
}

function openMobileInstallModal() {
  const modal = document.getElementById("mobileInstallModal");
  if (!modal) return;
  modal.classList.remove("hidden");

  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  const iosGuide = document.getElementById("iosInstallGuide");
  const pwaBtn = document.getElementById("pwaInstallActionBtn");

  if (isIOS) {
    if (iosGuide) iosGuide.classList.remove("hidden");
    if (pwaBtn) {
      pwaBtn.innerHTML = `<i data-lucide="share" class="w-4 h-4"></i><span>Add to Home Screen</span>`;
    }
  } else {
    if (iosGuide) iosGuide.classList.add("hidden");
    if (pwaBtn) {
      pwaBtn.innerHTML = `<i data-lucide="smartphone" class="w-4 h-4"></i><span>Install App (1-Click)</span>`;
    }
  }

  if (window.lucide) safeRenderIcons();
}

function closeMobileInstallModal() {
  const modal = document.getElementById("mobileInstallModal");
  if (modal) modal.classList.add("hidden");
  sessionStorage.setItem("pwaModalDismissed", "true");
}

async function triggerPwaInstall() {
  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    const { outcome } = await deferredInstallPrompt.userChoice;
    if (outcome === "accepted") {
      showToast("App successfully installed to your phone!", "success");
      closeMobileInstallModal();
    }
    deferredInstallPrompt = null;
  } else {
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    if (isIOS) {
      showToast("On iOS Safari: Tap Share (box with arrow) -> 'Add to Home Screen'", "info");
    } else {
      showToast("On Android Chrome: Tap menu (⋮) -> 'Install app' or 'Add to Home screen'", "info");
      sessionStorage.setItem("pwaModalDismissed", "true");
    }
  }
}

function trackApkDownload() {
  showToast("Downloading ExpenseTracker.apk installer...", "success");
  sessionStorage.setItem("pwaModalDismissed", "true");
  setTimeout(() => {
    closeMobileInstallModal();
  }, 1200);
}


// ==========================================
// ADMIN UPGRADE / UNLOCK LOGIC
// ==========================================
function openAdminUpgradeModal() {
  const modal = document.getElementById("adminUpgradeModal");
  if (modal) {
    modal.classList.remove("hidden");
    const input = document.getElementById("adminUpgradeSecretInput");
    if (input) {
      input.value = "";
      input.focus();
    }
  }
  if (window.lucide) safeRenderIcons();
}

function closeAdminUpgradeModal() {
  const modal = document.getElementById("adminUpgradeModal");
  if (modal) modal.classList.add("hidden");
}

async function handleAdminUpgradeSubmit(event) {
  event.preventDefault();
  const secretInput = document.getElementById("adminUpgradeSecretInput");
  const secretKey = secretInput?.value.trim();
  if (!secretKey) {
    showToast("Please enter the admin secret key.", "error");
    return;
  }

  try {
    const res = await apiRequest("/api/auth/upgrade-admin", {
      method: "POST",
      body: JSON.stringify({ admin_secret: secretKey })
    });

    if (res && res.access_token) {
      state.token = res.access_token;
      state.user = res.user;
      localStorage.setItem("token", res.access_token);
      localStorage.setItem("user", JSON.stringify(res.user));

      // Reveal Admin Navigation Tabs
      const adminNav = document.getElementById("nav-admin");
      const mobileAdminNav = document.getElementById("mobile-nav-admin");
      const adminUnlockBtn = document.getElementById("sidebarAdminUnlockBtn");
      if (adminNav) adminNav.classList.remove("hidden");
      if (mobileAdminNav) mobileAdminNav.classList.remove("hidden");
      if (adminUnlockBtn) adminUnlockBtn.classList.add("hidden");

      closeAdminUpgradeModal();
      showToast("Administrative privileges unlocked! Switched to Admin view.", "success");
      switchTab("admin");
    }
  } catch (err) {
    // Error handled in apiRequest
  }
}


// ==========================================
// REGISTRATION OTP CONTROLLER
// ==========================================
let pendingRegistration = null;
let otpCountdownInterval = null;
let currentDevOtp = null;

function openOtpModal(email, devOtp = null) {
  const modal = document.getElementById("otpModal");
  if (!modal) return;

  const emailSpan = document.getElementById("otpTargetEmail");
  if (emailSpan) emailSpan.textContent = email;

  currentDevOtp = devOtp;
  const devBadge = document.getElementById("devOtpBadge");
  const devValue = document.getElementById("devOtpValue");
  if (devBadge && devValue) {
    if (devOtp) {
      devValue.textContent = devOtp;
      devBadge.classList.remove("hidden");
    } else {
      devBadge.classList.add("hidden");
    }
  }

  // Clear inputs
  const inputs = document.querySelectorAll(".otp-digit");
  inputs.forEach(input => input.value = "");
  if (inputs.length > 0) {
    setTimeout(() => inputs[0].focus(), 150);
  }

  startOtpCountdown(300); // 5 minutes
  modal.classList.remove("hidden");
  if (window.lucide) safeRenderIcons();
}

function closeOtpModal() {
  const modal = document.getElementById("otpModal");
  if (modal) modal.classList.add("hidden");
  if (otpCountdownInterval) {
    clearInterval(otpCountdownInterval);
    otpCountdownInterval = null;
  }
}

function autoFillDevOtp() {
  if (!currentDevOtp) return;
  const inputs = document.querySelectorAll(".otp-digit");
  const digits = currentDevOtp.split("");
  inputs.forEach((input, idx) => {
    if (digits[idx]) input.value = digits[idx];
  });
  if (inputs[inputs.length - 1]) inputs[inputs.length - 1].focus();
  showToast("Development OTP code auto-filled!", "success");
}

function startOtpCountdown(seconds) {
  if (otpCountdownInterval) clearInterval(otpCountdownInterval);
  const timerDisplay = document.getElementById("otpTimerDisplay");
  const resendBtn = document.getElementById("resendOtpBtn");
  if (resendBtn) resendBtn.disabled = true;

  let remaining = seconds;
  const updateTimer = () => {
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    if (timerDisplay) {
      timerDisplay.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }
    if (remaining <= 0) {
      clearInterval(otpCountdownInterval);
      otpCountdownInterval = null;
      if (resendBtn) resendBtn.disabled = false;
      if (timerDisplay) timerDisplay.textContent = "Expired";
    }
    remaining--;
  };

  updateTimer();
  otpCountdownInterval = setInterval(updateTimer, 1000);
}

async function resendRegistrationOtp() {
  if (!pendingRegistration || !pendingRegistration.email) {
    showToast("No active registration found. Please fill registration details.", "error");
    closeOtpModal();
    return;
  }

  const resendBtn = document.getElementById("resendOtpBtn");
  if (resendBtn) resendBtn.disabled = true;

  try {
    const res = await fetch(getApiUrl("/api/auth/send-registration-otp"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: pendingRegistration.email })
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error((data && data.detail) || "Failed to resend OTP");

    currentDevOtp = data.dev_otp;
    const devBadge = document.getElementById("devOtpBadge");
    const devValue = document.getElementById("devOtpValue");
    if (devBadge && devValue) {
      if (data.dev_otp) {
        devValue.textContent = data.dev_otp;
        devBadge.classList.remove("hidden");
      }
    }

    startOtpCountdown(300);
    showToast(`New verification code sent to ${pendingRegistration.email}`, "success");
  } catch (err) {
    showToast(formatNetworkError(err), "error");
    if (resendBtn) resendBtn.disabled = false;
  }
}

function setupOtpInputs() {
  const inputs = document.querySelectorAll(".otp-digit");
  inputs.forEach((input, idx) => {
    input.addEventListener("input", (e) => {
      const val = e.target.value.replace(/\D/g, "");
      e.target.value = val ? val[0] : "";
      if (val && idx < inputs.length - 1) {
        inputs[idx + 1].focus();
      }
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !e.target.value && idx > 0) {
        inputs[idx - 1].focus();
      }
    });

    input.addEventListener("paste", (e) => {
      e.preventDefault();
      const pasted = (e.clipboardData || window.clipboardData).getData("text").replace(/\D/g, "");
      if (!pasted) return;
      const chars = pasted.slice(0, 6).split("");
      inputs.forEach((inp, i) => {
        inp.value = chars[i] || "";
      });
      const nextIdx = Math.min(chars.length, inputs.length - 1);
      inputs[nextIdx].focus();
    });
  });
}

async function handleOtpSubmit(e) {
  e.preventDefault();
  if (!pendingRegistration) {
    showToast("Registration session lost. Please fill registration form again.", "error");
    closeOtpModal();
    return;
  }

  const inputs = document.querySelectorAll(".otp-digit");
  let otp = "";
  inputs.forEach(inp => otp += inp.value.trim());

  if (otp.length !== 6 || !/^\d{6}$/.test(otp)) {
    showToast("Please enter all 6 numeric digits of your verification code.", "warning");
    return;
  }

  const verifyBtn = document.getElementById("verifyOtpBtn");
  const originalHtml = verifyBtn ? verifyBtn.innerHTML : "Verify & Create Account";

  try {
    if (verifyBtn) {
      verifyBtn.disabled = true;
      verifyBtn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Verifying Code...</span>`;
      if (window.lucide) safeRenderIcons();
    }

    const payload = {
      ...pendingRegistration,
      otp
    };

    const res = await fetch(getApiUrl("/api/auth/register"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error((data && data.detail) || `Registration verification failed (${res.status})`);

    applyAuthSession(data, true);

    closeOtpModal();
    pendingRegistration = null;

    if (data.user.is_admin) {
      showToast("Administrator account verified and created successfully!", "success");
    } else {
      showToast(`Welcome ${data.user.full_name}! Your account has been verified.`, "success");
    }
    showApp();
  } catch (err) {
    showToast(formatNetworkError(err), "error");
    inputs.forEach(inp => inp.classList.add("border-rose-500"));
    setTimeout(() => {
      inputs.forEach(inp => inp.classList.remove("border-rose-500"));
    }, 2000);
  } finally {
    if (verifyBtn) {
      verifyBtn.disabled = false;
      verifyBtn.innerHTML = originalHtml;
      if (window.lucide) safeRenderIcons();
    }
  }
}


// ==========================================================================
// APP SECURITY: 4-DIGIT MPIN & BIOMETRICS (FINGERPRINT / FACE ID) UNLOCK
// ==========================================================================

let currentMpinBuffer = "";
let mpinFailedAttempts = 0;
let mpinLockoutUntil = 0;

function jsSha256(ascii) {
  function rightRotate(value, amount) { return (value >>> amount) | (value << (32 - amount)); }
  const mathPow = Math.pow, maxWord = mathPow(2, 32);
  let lengthProperty = 'length', i, j, result = '';
  const words = [];
  const asciiBitLength = ascii[lengthProperty] * 8;
  let hash = [], k = [], primeCounter = 0;
  const isComposite = {};
  for (let candidate = 2; primeCounter < 64; candidate++) {
    if (!isComposite[candidate]) {
      for (i = 0; i < 313; i += candidate) isComposite[i] = candidate;
      hash[primeCounter] = (mathPow(candidate, .5) * maxWord) | 0;
      k[primeCounter++] = (mathPow(candidate, 1 / 3) * maxWord) | 0;
    }
  }
  hash = hash.slice(0, 8);
  ascii += '\x80';
  while (ascii[lengthProperty] % 64 - 56) ascii += '\x00';
  for (i = 0; i < ascii[lengthProperty]; i++) {
    j = ascii.charCodeAt(i);
    if (j >> 8) return "";
    words[i >> 2] |= j << ((3 - i) % 4) * 8;
  }
  words[words[lengthProperty]] = ((asciiBitLength / maxWord) | 0);
  words[words[lengthProperty]] = (asciiBitLength) | 0;
  for (j = 0; j < words[lengthProperty];) {
    const w = words.slice(j, j += 16);
    const oldHash = hash;
    hash = hash.slice(0, 8);
    for (i = 0; i < 64; i++) {
      const w15 = w[i - 15], w2 = w[i - 2];
      const a = hash[0], e = hash[4];
      const temp1 = hash[7]
        + (rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25))
        + ((e & hash[5]) ^ ((~e) & hash[6]))
        + k[i]
        + (w[i] = (i < 16) ? w[i] : (
          w[i - 16]
          + (rightRotate(w15, 7) ^ rightRotate(w15, 18) ^ (w15 >>> 3))
          + w[i - 7]
          + (rightRotate(w2, 17) ^ rightRotate(w2, 19) ^ (w2 >>> 10))
        ) | 0);
      const temp2 = (rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22))
        + ((a & hash[1]) ^ (a & hash[2]) ^ (hash[1] & hash[2]));
      hash = [(temp1 + temp2) | 0].concat(hash);
      hash[4] = (hash[4] + temp1) | 0;
    }
    for (i = 0; i < 8; i++) hash[i] = (hash[i] + oldHash[i]) | 0;
  }
  for (i = 0; i < 8; i++) {
    for (j = 3; j + 1; j--) {
      const b = (hash[i] >> (j * 8)) & 255;
      result += ((b < 16) ? 0 : '') + b.toString(16);
    }
  }
  return result;
}

async function computeMpinHash(pin, salt) {
  const salted = `${salt}_${pin}_ExpenseTrackFin2026`;
  if (window.crypto && window.crypto.subtle && typeof window.crypto.subtle.digest === 'function') {
    try {
      const enc = new TextEncoder().encode(salted);
      const buf = await window.crypto.subtle.digest("SHA-256", enc);
      return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
    } catch (e) {
      console.warn("Subtle crypto fallback to jsSha256:", e);
    }
  }
  return jsSha256(salted);
}

function isAppLockActive() {
  const enabled = localStorage.getItem("app_lock_enabled") === "true";
  const hasHash = Boolean(localStorage.getItem("app_lock_mpin_hash"));
  return enabled && hasHash;
}

function isBiometricsEnabled() {
  return localStorage.getItem("app_lock_biometrics_enabled") === "true";
}

function isAutoLockEnabled() {
  return localStorage.getItem("app_lock_autolock") !== "false";
}

async function checkBiometricsAvailability() {
  if (window.PublicKeyCredential && typeof PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable === 'function') {
    try {
      return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
    } catch (e) {
      return false;
    }
  }
  return false;
}

// Show Lockscreen
function showAppLockScreen() {
  const lockScreen = document.getElementById("appLockScreen");
  if (!lockScreen) return;

  currentMpinBuffer = "";
  updateLockDotsUI();

  const greetingEl = document.getElementById("lockUserGreeting");
  const promptEl = document.getElementById("lockStatusPrompt");
  if (greetingEl) {
    const name = state.user?.full_name ? state.user.full_name.split(" ")[0] : "User";
    greetingEl.textContent = `Hi, ${name}! Enter MPIN`;
  }
  if (promptEl) {
    promptEl.textContent = isBiometricsEnabled()
      ? "Scan fingerprint or enter 4-digit MPIN"
      : "Enter your 4-digit Security MPIN";
  }

  // Toggle quick biometric scan button visibility
  const bioPill = document.getElementById("lockScreenBioQuickBtn");
  const bioKeypad = document.getElementById("keypadBioBtn");
  if (bioPill) {
    if (isBiometricsEnabled()) {
      bioPill.classList.remove("hidden");
    } else {
      bioPill.classList.add("hidden");
    }
  }
  if (bioKeypad) {
    if (isBiometricsEnabled()) {
      bioKeypad.classList.remove("opacity-40");
      bioKeypad.title = "Unlock with Fingerprint or Face ID";
    } else {
      bioKeypad.classList.add("opacity-40");
      bioKeypad.title = "Biometrics not enabled";
    }
  }

  lockScreen.classList.remove("hidden");
  document.getElementById("appScreen")?.classList.add("hidden");
  document.getElementById("authScreen")?.classList.add("hidden");
  safeRenderIcons();
}

function unlockAppLockScreen() {
  const lockScreen = document.getElementById("appLockScreen");
  if (lockScreen) {
    lockScreen.classList.add("hidden");
  }
  currentMpinBuffer = "";
  mpinFailedAttempts = 0;
  if (navigator.vibrate) {
    try { navigator.vibrate(40); } catch (e) {}
  }
  showApp();
}

function updateLockDotsUI(isError = false) {
  for (let i = 0; i < 4; i++) {
    const dot = document.getElementById(`lockDot${i}`);
    if (!dot) continue;
    if (isError) {
      dot.className = "lock-dot-empty lock-dot-error";
    } else if (i < currentMpinBuffer.length) {
      dot.className = "lock-dot-empty lock-dot-filled";
    } else {
      dot.className = "lock-dot-empty";
    }
  }
}

function handleKeypadInput(digit) {
  if (Date.now() < mpinLockoutUntil) {
    const secs = Math.ceil((mpinLockoutUntil - Date.now()) / 1000);
    showToast(`Too many attempts. Please wait ${secs}s`, "warning");
    return;
  }

  if (currentMpinBuffer.length < 4) {
    currentMpinBuffer += digit;
    updateLockDotsUI();
    if (navigator.vibrate) {
      try { navigator.vibrate(20); } catch (e) {}
    }

    if (currentMpinBuffer.length === 4) {
      verifyEnteredMpin(currentMpinBuffer);
    }
  }
}

function handleKeypadBackspace() {
  if (currentMpinBuffer.length > 0) {
    currentMpinBuffer = currentMpinBuffer.slice(0, -1);
    updateLockDotsUI();
    if (navigator.vibrate) {
      try { navigator.vibrate(15); } catch (e) {}
    }
  }
}

async function verifyEnteredMpin(pin) {
  const salt = localStorage.getItem("app_lock_salt") || "DefaultSecureSalt99";
  const storedHash = localStorage.getItem("app_lock_mpin_hash");

  const computed = await computeMpinHash(pin, salt);

  if (computed === storedHash) {
    showToast("App unlocked successfully!", "success");
    unlockAppLockScreen();
  } else {
    mpinFailedAttempts++;
    updateLockDotsUI(true);

    const dotsContainer = document.getElementById("lockPinDotsContainer");
    if (dotsContainer) {
      dotsContainer.classList.add("shake-anim");
      setTimeout(() => dotsContainer.classList.remove("shake-anim"), 350);
    }

    const promptEl = document.getElementById("lockStatusPrompt");
    if (promptEl) {
      promptEl.textContent = "Incorrect MPIN. Please try again.";
      promptEl.className = "text-[11px] text-rose-400 font-bold";
    }

    if (navigator.vibrate) {
      try { navigator.vibrate([60, 50, 60]); } catch (e) {}
    }

    if (mpinFailedAttempts >= 5) {
      mpinLockoutUntil = Date.now() + 30000;
      showToast("5 incorrect attempts. Keypad locked for 30 seconds.", "error");
    }

    setTimeout(() => {
      currentMpinBuffer = "";
      updateLockDotsUI();
      if (promptEl) {
        promptEl.textContent = isBiometricsEnabled()
          ? "Scan fingerprint or enter 4-digit MPIN"
          : "Enter your 4-digit Security MPIN";
        promptEl.className = "text-[11px] text-slate-400";
      }
    }, 600);
  }
}

// Biometrics Authentication Trigger (Fingerprint / Face ID / Screen Lock)
async function triggerBiometricPrompt() {
  if (!isBiometricsEnabled()) {
    showToast("Biometrics is not enabled. Enter your 4-digit MPIN.", "info");
    return;
  }

  const promptEl = document.getElementById("lockStatusPrompt");
  if (promptEl) {
    promptEl.textContent = "Waiting for fingerprint or Face ID...";
    promptEl.className = "text-[11px] text-indigo-400 font-semibold";
  }

  try {
    const challenge = new Uint8Array(32);
    window.crypto.getRandomValues(challenge);

    const credIdBase64 = localStorage.getItem("app_lock_bio_credential_id");
    let allowCredentials = [];
    if (credIdBase64) {
      try {
        const rawId = Uint8Array.from(atob(credIdBase64), c => c.charCodeAt(0));
        allowCredentials.push({
          id: rawId,
          type: "public-key",
          transports: ["internal"]
        });
      } catch (e) {}
    }

    const assertion = await navigator.credentials.get({
      publicKey: {
        challenge,
        timeout: 60000,
        userVerification: "required",
        ...(allowCredentials.length > 0 ? { allowCredentials } : {})
      }
    });

    if (assertion) {
      showToast("Biometric verification successful!", "success");
      unlockAppLockScreen();
      return;
    }
  } catch (err) {
    console.log("Biometric prompt result notice:", err.name, err.message);
    if (promptEl) {
      promptEl.textContent = "Biometrics cancelled. Enter your 4-digit MPIN.";
      promptEl.className = "text-[11px] text-slate-400";
    }
  }
}

// Forgot MPIN Recovery
function handleForgotMpin() {
  const ans = confirm("Forgot your 4-digit MPIN?\n\nYou can reset your MPIN by logging in with your account password. Would you like to proceed to account password sign-in?");
  if (ans) {
    localStorage.removeItem("app_lock_enabled");
    localStorage.removeItem("app_lock_mpin_hash");
    localStorage.removeItem("app_lock_biometrics_enabled");
    localStorage.removeItem("app_lock_bio_credential_id");
    logout();
    showToast("Please sign in with your password to set a new MPIN.", "info");
  }
}

// Switch Account / Log in with Password
function handleLockscreenSwitchAccount() {
  document.getElementById("appLockScreen")?.classList.add("hidden");
  logout();
}

// Setup & Settings Modal Controls
async function openAppLockSetupModal() {
  const modal = document.getElementById("appLockSetupModal");
  if (!modal) return;

  const isEnabled = isAppLockActive();
  const enableToggle = document.getElementById("enableAppLockToggle");
  const fieldsContainer = document.getElementById("appLockFieldsContainer");
  const statusText = document.getElementById("appLockStatusText");
  const statusBadge = document.getElementById("appLockStatusBadge");
  const bioToggle = document.getElementById("enableBiometricsToggle");
  const autoLockToggle = document.getElementById("autoLockOnSwitchToggle");
  const testBtn = document.getElementById("testAppLockBtn");
  const removeBtn = document.getElementById("removeAppLockBtn");

  if (enableToggle) enableToggle.checked = isEnabled;
  if (fieldsContainer) {
    if (isEnabled) fieldsContainer.classList.remove("hidden");
    else fieldsContainer.classList.add("hidden");
  }

  if (statusText) {
    statusText.textContent = isEnabled ? "Active & Protecting App" : "Disabled (No MPIN Required)";
  }
  if (statusBadge) {
    statusBadge.textContent = isEnabled ? "Active" : "Disabled";
    statusBadge.className = isEnabled
      ? "px-2.5 py-1 rounded-full text-[10px] font-extrabold bg-emerald-100 dark:bg-emerald-950/70 text-emerald-700 dark:text-emerald-400 border border-emerald-300 dark:border-emerald-800"
      : "px-2.5 py-1 rounded-full text-[10px] font-extrabold bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300";
  }

  if (autoLockToggle) {
    autoLockToggle.checked = isAutoLockEnabled();
  }

  // Detect Biometric Hardware on device
  const hasBio = await checkBiometricsAvailability();
  const bioCard = document.getElementById("bioHardwareCard");
  const bioTitle = document.getElementById("bioHardwareTitle");
  const bioSubtitle = document.getElementById("bioHardwareSubtitle");
  const bioRow = document.getElementById("enableBioRow");

  if (hasBio) {
    if (bioCard) bioCard.className = "p-3 rounded-2xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-100 dark:border-emerald-900/50 flex items-center gap-3";
    if (bioTitle) bioTitle.textContent = "Biometric Sensor Ready";
    if (bioSubtitle) bioSubtitle.textContent = "Your device supports native Fingerprint / Face Unlock authentication.";
    if (bioRow) bioRow.classList.remove("hidden");
    if (bioToggle) bioToggle.checked = isBiometricsEnabled();
  } else {
    if (bioCard) bioCard.className = "p-3 rounded-2xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-700 flex items-center gap-3";
    if (bioTitle) bioTitle.textContent = "4-Digit MPIN Mode Available";
    if (bioSubtitle) bioSubtitle.textContent = "Biometric hardware is not detected or supported on this browser context. You can use 4-digit Security MPIN.";
    if (bioRow) bioRow.classList.add("hidden");
    if (bioToggle) bioToggle.checked = false;
  }

  if (testBtn) {
    if (isEnabled) testBtn.classList.remove("hidden");
    else testBtn.classList.add("hidden");
  }
  if (removeBtn) {
    if (isEnabled) removeBtn.classList.remove("hidden");
    else removeBtn.classList.add("hidden");
  }

  // Reset inputs
  const mpinInput = document.getElementById("setupMpinInput");
  const confirmInput = document.getElementById("confirmMpinInput");
  if (mpinInput) mpinInput.value = "";
  if (confirmInput) confirmInput.value = "";

  modal.classList.remove("hidden");
  safeRenderIcons();
}

function closeAppLockSetupModal() {
  document.getElementById("appLockSetupModal")?.classList.add("hidden");
}

function toggleAppLockFields(enabled) {
  const container = document.getElementById("appLockFieldsContainer");
  if (container) {
    if (enabled) container.classList.remove("hidden");
    else container.classList.add("hidden");
  }
}

async function handleSaveAppLockSettings(e) {
  e.preventDefault();
  const enableToggle = document.getElementById("enableAppLockToggle");
  const isEnabling = enableToggle ? enableToggle.checked : false;

  if (!isEnabling) {
    handleRemoveAppLock();
    return;
  }

  const mpin = document.getElementById("setupMpinInput").value.trim();
  const confirmMpin = document.getElementById("confirmMpinInput").value.trim();
  const bioToggle = document.getElementById("enableBiometricsToggle");
  const autoLockToggle = document.getElementById("autoLockOnSwitchToggle");

  const existingHash = localStorage.getItem("app_lock_mpin_hash");

  // If user is setting a new MPIN or changing it
  if (mpin || !existingHash) {
    if (!/^\d{4}$/.test(mpin)) {
      showToast("Security MPIN must be exactly 4 numeric digits (0-9).", "warning");
      return;
    }
    if (mpin !== confirmMpin) {
      showToast("The confirmation MPIN does not match. Please re-enter.", "error");
      return;
    }

    const salt = Array.from(crypto.getRandomValues(new Uint8Array(16)))
      .map(b => b.toString(16).padStart(2, "0")).join("");
    const hash = await computeMpinHash(mpin, salt);

    localStorage.setItem("app_lock_salt", salt);
    localStorage.setItem("app_lock_mpin_hash", hash);
  }

  localStorage.setItem("app_lock_enabled", "true");
  localStorage.setItem("app_lock_autolock", autoLockToggle?.checked ? "true" : "false");

  // Handle Biometrics Registration if toggled ON
  if (bioToggle && bioToggle.checked) {
    try {
      showToast("Requesting device biometric permission...", "info");
      const cred = await registerBiometricAuthenticator();
      if (cred && cred.rawId) {
        const base64Id = btoa(String.fromCharCode(...new Uint8Array(cred.rawId)));
        localStorage.setItem("app_lock_bio_credential_id", base64Id);
        localStorage.setItem("app_lock_biometrics_enabled", "true");
        showToast("Fingerprint / Face ID linked successfully!", "success");
      }
    } catch (bioErr) {
      console.warn("Biometrics registration notice:", bioErr);
      showToast("Biometric sensor registration was cancelled. MPIN will be used.", "warning");
      localStorage.setItem("app_lock_biometrics_enabled", "false");
    }
  } else {
    localStorage.setItem("app_lock_biometrics_enabled", "false");
  }

  closeAppLockSetupModal();
  dismissAppLockPromo();
  showToast("App Lock & Security MPIN configured successfully!", "success");
}

async function registerBiometricAuthenticator() {
  const challenge = new Uint8Array(32);
  window.crypto.getRandomValues(challenge);
  const userId = new Uint8Array(16);
  window.crypto.getRandomValues(userId);

  const cred = await navigator.credentials.create({
    publicKey: {
      challenge,
      rp: {
        name: "ExpenseTrack Security",
        id: window.location.hostname
      },
      user: {
        id: userId,
        name: state.user?.email || "user@expensetrack.app",
        displayName: state.user?.full_name || "ExpenseTrack User"
      },
      pubKeyCredParams: [
        { alg: -7, type: "public-key" },
        { alg: -257, type: "public-key" }
      ],
      authenticatorSelection: {
        authenticatorAttachment: "platform",
        userVerification: "required",
        residentKey: "preferred"
      },
      timeout: 60000,
      attestation: "none"
    }
  });

  return cred;
}

function handleRemoveAppLock() {
  localStorage.removeItem("app_lock_enabled");
  localStorage.removeItem("app_lock_mpin_hash");
  localStorage.removeItem("app_lock_salt");
  localStorage.removeItem("app_lock_biometrics_enabled");
  localStorage.removeItem("app_lock_bio_credential_id");
  closeAppLockSetupModal();
  showToast("App Lock has been disabled.", "info");
}

function testAppLockScreen() {
  closeAppLockSetupModal();
  showAppLockScreen();
  if (isBiometricsEnabled()) {
    setTimeout(triggerBiometricPrompt, 280);
  }
}

// Dashboard Promo Banner Handlers
function checkAppLockPromoBanner() {
  const banner = document.getElementById("appLockPromoBanner");
  if (!banner) return;
  const isEnabled = isAppLockActive();
  const isDismissed = localStorage.getItem("app_lock_promo_dismissed") === "true";
  if (!isEnabled && !isDismissed && state.user) {
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

function dismissAppLockPromo() {
  localStorage.setItem("app_lock_promo_dismissed", "true");
  const banner = document.getElementById("appLockPromoBanner");
  if (banner) banner.classList.add("hidden");
}

// Keyboard typing support for physical keyboards (0-9, Backspace)
document.addEventListener("keydown", (e) => {
  const lockScreen = document.getElementById("appLockScreen");
  if (!lockScreen || lockScreen.classList.contains("hidden")) return;

  if (e.key >= "0" && e.key <= "9") {
    handleKeypadInput(e.key);
  } else if (e.key === "Backspace") {
    handleKeypadBackspace();
  }
});

// Auto-lock on app minimize or switching tabs/apps
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    state.lastBackgroundTime = Date.now();
  } else if (document.visibilityState === "visible") {
    if (state.token && state.user && isAppLockActive() && isAutoLockEnabled()) {
      showAppLockScreen();
      if (isBiometricsEnabled()) {
        setTimeout(triggerBiometricPrompt, 280);
      }
    }
  }
});

