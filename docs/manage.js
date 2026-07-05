/**
 * 关注列表管理：localStorage + GitHub Contents API 同步
 */
const WatchlistStore = (() => {
  const LS_KEY = "fund_monitor_watchlist";
  const SYNC_KEY = "fund_monitor_watchlist_synced";
  const TOKEN_KEY = "fund_monitor_github_token";
  const REPO = { owner: "zhoutammie", repo: "fund-monitor" };
  const FILE_PATH = "docs/watchlist.json";

  const TENCENT_URL = "https://qt.gtimg.cn/q=";
  const FUND_URL = "https://fundgz.1234567.com.cn/js/{code}.js";

  let watchlist = defaultWatchlist();
  let listeners = [];

  function defaultWatchlist() {
    return {
      indices: [],
      funds: [],
      stocks: [],
      refresh_interval: 180,
      push: { channels: ["feishu"] },
    };
  }

  function notify() {
    listeners.forEach((fn) => fn(watchlist));
  }

  function inferMarket(code) {
    const c = code.toLowerCase();
    if (c.startsWith("sh") || c.startsWith("sz")) return "cn";
    if (c.startsWith("hk")) return "hk";
    if (c.startsWith("us")) return "us";
    return "cn";
  }

  function normalizeCode(type, raw) {
    let code = raw.trim().toLowerCase();
    if (type === "fund") {
      code = code.replace(/\D/g, "");
      if (!/^\d{6}$/.test(code)) {
        throw new Error("基金代码应为 6 位数字");
      }
      return code;
    }
    if (/^\d{6}$/.test(code)) {
      code = (code.startsWith("6") ? "sh" : "sz") + code;
    }
    if (!/^(sh|sz|hk|us)[a-z0-9]+$/i.test(code)) {
      throw new Error("代码格式无效，示例：sh000001、sh600519、hk00700、110022");
    }
    return code;
  }

  function getListKey(type) {
    if (type === "index") return "indices";
    if (type === "fund") return "funds";
    if (type === "stock") return "stocks";
    throw new Error("未知类型");
  }

  function isDirty() {
    const synced = localStorage.getItem(SYNC_KEY);
    if (!synced) return true;
    return synced !== JSON.stringify(watchlist);
  }

  function saveLocal() {
    localStorage.setItem(LS_KEY, JSON.stringify(watchlist));
    notify();
  }

  async function load() {
    const cached = localStorage.getItem(LS_KEY);
    if (cached) {
      watchlist = { ...defaultWatchlist(), ...JSON.parse(cached) };
      notify();
      return watchlist;
    }
    try {
      const resp = await fetch("watchlist.json?_=" + Date.now());
      if (resp.ok) {
        watchlist = { ...defaultWatchlist(), ...await resp.json() };
        saveLocal();
        localStorage.setItem(SYNC_KEY, JSON.stringify(watchlist));
      }
    } catch {
      watchlist = defaultWatchlist();
    }
    notify();
    return watchlist;
  }

  function get() {
    return watchlist;
  }

  function subscribe(fn) {
    listeners.push(fn);
    return () => {
      listeners = listeners.filter((f) => f !== fn);
    };
  }

  function exists(type, code) {
    const key = getListKey(type);
    return (watchlist[key] || []).some((item) => item.code === code);
  }

  async function previewName(type, code) {
    if (type === "fund") {
      return new Promise((resolve) => {
        const script = document.createElement("script");
        const timer = setTimeout(() => {
          cleanup();
          resolve(null);
        }, 8000);

        function cleanup() {
          clearTimeout(timer);
          if (window.jsonpgz === handler) delete window.jsonpgz;
          script.remove();
        }

        function handler(data) {
          cleanup();
          resolve(data.name || null);
        }

        window.jsonpgz = handler;
        script.src = FUND_URL.replace("{code}", code);
        script.onerror = () => {
          cleanup();
          resolve(null);
        };
        document.body.appendChild(script);
      });
    }

    const resp = await fetch(TENCENT_URL + code);
    const buffer = await resp.arrayBuffer();
    const text = new TextDecoder("gbk").decode(buffer);
    const match = text.match(/v_[a-zA-Z0-9]+="([^"]*)"/);
    if (!match) return null;
    const parts = match[1].split("~");
    return parts[1] || null;
  }

  async function addItem(type, rawCode, rawName) {
    const code = normalizeCode(type, rawCode);
    if (exists(type, code)) {
      throw new Error("该标的已在关注列表中");
    }

    let name = rawName?.trim() || "";
    if (!name) {
      name = (await previewName(type, code)) || code;
    }

    const item = { code, name };
    if (type !== "fund") {
      item.market = inferMarket(code);
    }

    const key = getListKey(type);
    watchlist[key] = watchlist[key] || [];
    watchlist[key].push(item);
    saveLocal();
    return item;
  }

  function removeItem(type, code) {
    const key = getListKey(type);
    watchlist[key] = (watchlist[key] || []).filter((item) => item.code !== code);
    saveLocal();
  }

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function setToken(token) {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token.trim());
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  }

  async function githubApi(path, method, body) {
    const token = getToken();
    if (!token) throw new Error("请先在设置中配置 GitHub Token");

    const resp = await fetch(`https://api.github.com${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.message || `GitHub API 错误 ${resp.status}`);
    }
    return data;
  }

  async function syncToGitHub() {
    let sha;
    try {
      const existing = await githubApi(
        `/repos/${REPO.owner}/${REPO.repo}/contents/${FILE_PATH}`,
        "GET"
      );
      sha = existing.sha;
    } catch {
      sha = undefined;
    }

    const content = btoa(unescape(encodeURIComponent(JSON.stringify(watchlist, null, 2) + "\n")));
    const payload = {
      message: "chore: update watchlist from web UI",
      content,
      branch: "main",
    };
    if (sha) payload.sha = sha;

    await githubApi(
      `/repos/${REPO.owner}/${REPO.repo}/contents/${FILE_PATH}`,
      "PUT",
      payload
    );

    localStorage.setItem(SYNC_KEY, JSON.stringify(watchlist));
    notify();
  }

  return {
    load,
    get,
    subscribe,
    addItem,
    removeItem,
    syncToGitHub,
    isDirty,
    getToken,
    setToken,
    inferMarket,
  };
})();
