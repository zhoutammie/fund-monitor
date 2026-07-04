const TENCENT_URL = "https://qt.gtimg.cn/q=";
const FUND_URL = "https://fundgz.1234567.com.cn/js/{code}.js";

let watchlist = { indices: [], funds: [], refresh_interval: 180 };
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

async function fetchIndices(codes) {
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
      if (window.jsonpgz === handler) {
        delete window.jsonpgz;
      }
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
    results.push({
      ...data,
      name: fund.name || data.name,
      code: fund.code,
    });
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

  return `
    <div class="card ${isError ? "error" : ""}">
      <div class="card-name">${displayName}</div>
      <div class="card-code">${item.code}</div>
      <div class="card-price">${isError ? "加载失败" : formatPrice(item.price)}</div>
      <div class="card-change ${change.cls}">${change.text}</div>
      ${item.updateTime ? `<div class="card-time">${item.updateTime}</div>` : ""}
      ${type === "fund" && !isError ? '<div class="card-time">估值 · 仅供参考</div>' : ""}
    </div>
  `;
}

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 2500);
}

async function loadWatchlist() {
  try {
    const resp = await fetch("watchlist.json");
    if (resp.ok) {
      watchlist = await resp.json();
    }
  } catch {
    console.warn("无法加载 watchlist.json，使用空列表");
  }
}

async function refresh() {
  const btn = document.getElementById("refresh-btn");
  btn.disabled = true;

  try {
    const indexCodes = watchlist.indices.map((i) => i.code);
    const indexNames = Object.fromEntries(watchlist.indices.map((i) => [i.code, i.name]));

    const [indicesRaw, fundsRaw] = await Promise.all([
      fetchIndices(indexCodes),
      fetchFunds(watchlist.funds || []),
    ]);

    const indices = indicesRaw.map((item) => ({
      ...item,
      name: indexNames[item.code] || item.name,
    }));

    document.getElementById("indices-grid").innerHTML =
      indices.length > 0
        ? indices.map((i) => renderCard(i, "index")).join("")
        : '<p class="hint">暂无指数配置</p>';

    document.getElementById("funds-grid").innerHTML =
      fundsRaw.length > 0
        ? fundsRaw.map((f) => renderCard(f, "fund")).join("")
        : '<p class="hint">暂无基金配置</p>';

    const now = new Date();
    document.getElementById("last-update").textContent =
      `最后更新：${now.toLocaleString("zh-CN")}`;
  } catch (err) {
    showToast("刷新失败，请稍后重试");
    console.error(err);
  } finally {
    btn.disabled = false;
  }
}

function scheduleRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  const interval = (watchlist.refresh_interval || 180) * 1000;
  refreshTimer = setInterval(refresh, interval);
}

async function init() {
  await loadWatchlist();
  document.getElementById("refresh-btn").addEventListener("click", refresh);
  await refresh();
  scheduleRefresh();
}

init();
