const DEFAULTS = {
  apiPort: 8765,
  apiToken: "",
  defaultCategory: "Uncategorized / Needs Review"
};

const api = globalThis.browser ?? globalThis.chrome;

function storageGet(keys) {
  if (api.storage.local.get.length === 1) {
    return api.storage.local.get(keys);
  }
  return new Promise(resolve => api.storage.local.get(keys, resolve));
}

function queryTabs(queryInfo) {
  if (api.tabs.query.length === 1) {
    return api.tabs.query(queryInfo);
  }
  return new Promise(resolve => api.tabs.query(queryInfo, resolve));
}

function executeScript(tabId, func) {
  if (!api.scripting || !api.scripting.executeScript) return Promise.resolve([]);
  const details = { target: { tabId }, func };
  if (api.scripting.executeScript.length === 1) {
    return api.scripting.executeScript(details);
  }
  return new Promise((resolve, reject) => {
    api.scripting.executeScript(details, result => {
      const error = api.runtime.lastError;
      if (error) { reject(new Error(error.message)); return; }
      resolve(result);
    });
  });
}

function getConfig() {
  return storageGet(DEFAULTS).then(stored => ({ ...DEFAULTS, ...stored }));
}

function baseUrl(config) {
  return `http://127.0.0.1:${config.apiPort}`;
}

function authHeaders(config) {
  return {
    "Authorization": `Bearer ${config.apiToken}`,
    "Content-Type": "application/json"
  };
}

function isSaveableUrl(url) {
  return /^https?:\/\//i.test(url || "");
}

async function loadCategories(datalistId) {
  try {
    const datalist = document.getElementById(datalistId);
    const resp = await fetch(api.runtime.getURL("categories.json"));
    const categories = await resp.json();
    for (const cat of categories) {
      const opt = document.createElement("option");
      opt.value = cat;
      datalist.appendChild(opt);
    }
  } catch { /* bundled file missing */ }
}
