const TENCENT_URL = "https://qt.gtimg.cn/q=";
const FUND_URL = "https://fundgz.1234567.com.cn/js/{code}.js";

let refreshTimer = null;

function formatPrice(value) {
  if (value == null || Number.isNaN(value)) return "—";
  if (value >= 1000) return value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (value < 10) return value.toFixed(4);
  return value.toFixed(2);
}

function formatChange(pct) {
  if (pct == null || Number.isNaN(pct)) return { text: "—", cls: "flat" };
  const sign = pct >= 0 ? "+" : "";
  const cls = pct > 0 ? "up" : pct < 0 ? "down" : "flat";
  return { text: `${sign}${pct.toFixed(2)}%`, cls };
}

function parseTencentLine(line) {
  const match = line.match(/v_([a-zA-Z0-9]+)="([^"]*)"/);
  if (!match || !match[2]) return null;
  const parts = match[2].split("~");
  if (parts.length < 6) return null;

  const price = parseFloat(parts[3]);
  const prevClose = parseFloat(parts[4]);
  let changePct = null;
  if (!Number.isNaN(price) && prevClose) {
    changePct = ((price - prevClose) / prevClose) * 100;
  }

  return {
    code: match[1],
    name: parts[1],
    price: Number.isNaN(price) ? null : price,
    changePct,
    updateTime: parts[30] || null,
  };
}

async function fetchTencentQuotes(codes) {
  if (!codes.length) return [];
  const url = TENCENT_URL + codes.join(",");
  const resp = await fetch(url);
  const buffer = await resp.arrayBuffer();
  const text = new TextDecoder("gbk").decode(buffer);

  const parsed = {};
  text.split(";").forEach((line) => {
    const item = parseTencentLine(line.trim());
    if (item) parsed[item.code] = item;
  });

  return codes.map((code) => parsed[code] || { code, error: true });
}

function fetchFundJsonp(code) {
  return new Promise((resolve) => {
    const script = document.createElement("script");
    const timer = setTimeout(() => {
      cleanup();
      resolve({ code, error: true });
    }, 10000);

    function cleanup() {
      clearTimeout(timer);
      if (window.jsonpgz === handler) delete window.jsonpgz;
      script.remove();
    }

    function handler(data) {
      cleanup();
      resolve({
        code,
        name: data.name,
        price: parseFloat(data.gsz) || parseFloat(data.dwjz) || null,
        changePct: parseFloat(data.gszzl),
        updateTime: data.gztime,
      });
    }

    window.jsonpgz = handler;
    script.src = FUND_URL.replace("{code}", code);
    script.onerror = () => {
      cleanup();
      resolve({ code, error: true });
    };
    document.body.appendChild(script);
  });
}

async function fetchFunds(funds) {
  const results = [];
  for (const fund of funds) {
    const data = await fetchFundJsonp(fund.code);
    results.push({ ...data, name: fund.name || data.name, code: fund.code });
    await sleep(200);
  }
  return results;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function renderCard(item, type) {
  const isError = item.error;
  const change = formatChange(item.changePct);
  const displayName = item.name || item.code;
  const fundHint = type === "fund" && !isError ? '<div class="card-time">估值 · 仅供参考</div>' : "";

  return `
    <div class="card ${isError ? "error" : ""}" data-type="${type}" data-code="${item.code}">
      <button type="button" class="card-delete" title="删除" aria-label="删除">×</button>
      <div class="card-name">${escapeHtml(displayName)}</div>
      <div class="card-code">${escapeHtml(item.code)}</div>
      <div class="card-price">${isError ? "加载失败" : formatPrice(item.price)}</div>
      <div class="card-change ${change.cls}">${change.text}</div>
      ${item.updateTime ? `<div class="card-time">${escapeHtml(item.updateTime)}</div>` : ""}
      ${fundHint}
    </div>
  `;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 2800);
}

function updateSyncBadge() {
  const badge = document.getElementById("sync-badge");
  if (!badge) return;
  if (WatchlistStore.isDirty()) {
    badge.textContent = "有未同步更改";
    badge.className = "sync-badge dirty";
  } else {
    badge.textContent = "已同步";
    badge.className = "sync-badge synced";
  }
}

function bindCardDeletes(container) {
  container.querySelectorAll(".card-delete").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const card = e.target.closest(".card");
      const type = card.dataset.type;
      const code = card.dataset.code;
      const typeMap = { index: "index", fund: "fund", stock: "stock" };
      WatchlistStore.removeItem(typeMap[type], code);
      updateSyncBadge();
      refresh();
      showToast("已删除，记得点「保存并同步」");
    });
  });
}

function renderGrid(containerId, items, type, emptyText) {
  const el = document.getElementById(containerId);
  if (!items.length) {
    el.innerHTML = `<p class="hint">${emptyText}</p>`;
    return;
  }
  el.innerHTML = items.map((i) => renderCard(i, type)).join("");
  bindCardDeletes(el);
}

async function refresh() {
  const btn = document.getElementById("refresh-btn");
  btn.disabled = true;

  try {
    const watchlist = WatchlistStore.get();
    const indexNames = Object.fromEntries(watchlist.indices.map((i) => [i.code, i.name]));
    const stockNames = Object.fromEntries((watchlist.stocks || []).map((i) => [i.code, i.name]));

    const indexCodes = watchlist.indices.map((i) => i.code);
    const stockCodes = (watchlist.stocks || []).map((i) => i.code);

    const [indicesRaw, stocksRaw, fundsRaw] = await Promise.all([
      fetchTencentQuotes(indexCodes),
      fetchTencentQuotes(stockCodes),
      fetchFunds(watchlist.funds || []),
    ]);

    const indices = indicesRaw.map((item) => ({
      ...item,
      name: indexNames[item.code] || item.name,
    }));
    const stocks = stocksRaw.map((item) => ({
      ...item,
      name: stockNames[item.code] || item.name,
    }));

    renderGrid("indices-grid", indices, "index", "暂无指数，请在上方添加");
    renderGrid("stocks-grid", stocks, "stock", "暂无股票，请在上方添加");
    renderGrid("funds-grid", fundsRaw, "fund", "暂无基金，请在上方添加");

    document.getElementById("last-update").textContent =
      `最后更新：${new Date().toLocaleString("zh-CN")}`;
  } catch (err) {
    showToast("刷新失败，请稍后重试");
    console.error(err);
  } finally {
    btn.disabled = false;
  }
}

function scheduleRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  const interval = (WatchlistStore.get().refresh_interval || 180) * 1000;
  refreshTimer = setInterval(refresh, interval);
}

function openModal(id) {
  document.getElementById(id).classList.remove("hidden");
}

function closeModal(id) {
  document.getElementById(id).classList.add("hidden");
}

function setupManageUI() {
  document.getElementById("add-btn").addEventListener("click", async () => {
    const type = document.getElementById("add-type").value;
    const code = document.getElementById("add-code").value;
    const name = document.getElementById("add-name").value;
    const btn = document.getElementById("add-btn");
    btn.disabled = true;
    try {
      await WatchlistStore.addItem(type, code, name);
      document.getElementById("add-code").value = "";
      document.getElementById("add-name").value = "";
      updateSyncBadge();
      await refresh();
      showToast("已添加，记得点「保存并同步」");
    } catch (err) {
      showToast(err.message || "添加失败");
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("sync-btn").addEventListener("click", async () => {
    const btn = document.getElementById("sync-btn");
    btn.disabled = true;
    try {
      await WatchlistStore.syncToGitHub();
      updateSyncBadge();
      showToast("已同步到 GitHub，飞书推送将使用新列表");
    } catch (err) {
      showToast(err.message || "同步失败");
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("settings-btn").addEventListener("click", () => {
    document.getElementById("token-input").value = WatchlistStore.getToken();
    openModal("settings-modal");
  });

  document.getElementById("save-token-btn").addEventListener("click", () => {
    WatchlistStore.setToken(document.getElementById("token-input").value);
    closeModal("settings-modal");
    showToast("Token 已保存（仅存在本浏览器）");
  });

  document.querySelectorAll("[data-close-modal]").forEach((el) => {
    el.addEventListener("click", () => closeModal(el.dataset.closeModal));
  });

  document.getElementById("refresh-btn").addEventListener("click", refresh);
}

async function init() {
  await WatchlistStore.load();
  setupManageUI();
  updateSyncBadge();
  WatchlistStore.subscribe(() => {
    updateSyncBadge();
    scheduleRefresh();
  });
  await refresh();
  scheduleRefresh();
}

init();
