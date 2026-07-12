const DEFAULTS = {
  apiPort: 8765,
  apiToken: "",
  defaultCategory: "Uncategorized / Needs Review"
};
const PENDING_SAVES_KEY = "pendingSaves";

const api = globalThis.browser ?? globalThis.chrome;

function storageGet(keys) {
  if (api.storage.local.get.length === 1) {
    return api.storage.local.get(keys);
  }
  return new Promise(resolve => api.storage.local.get(keys, resolve));
}

function storageSet(values) {
  if (api.storage.local.set.length === 1) {
    return api.storage.local.set(values);
  }
  return new Promise(resolve => api.storage.local.set(values, resolve));
}

function runtimeMessage(message) {
  if (api.runtime.sendMessage.length === 1) {
    return api.runtime.sendMessage(message);
  }
  return new Promise((resolve, reject) => {
    api.runtime.sendMessage(message, response => {
      const error = api.runtime.lastError;
      if (error) { reject(new Error("Extension service unavailable")); return; }
      resolve(response);
    });
  });
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

async function getConfig() {
  const response = await runtimeMessage({ type: "bop:get-config" });
  if (!response || !response.ok || !response.config) {
    throw new Error("Extension credential service unavailable");
  }
  return { ...DEFAULTS, ...response.config };
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

async function saveBookmarkPayload(payload, config) {
  const headers = authHeaders(config);
  if (payload.browser_snapshot) headers["X-BOP-Capture-Version"] = "1";
  const response = await fetch(`${baseUrl(config)}/bookmarks`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload)
  });
  let body = {};
  try { body = await response.json(); } catch { /* response body is optional */ }
  return { status: response.status, body };
}

async function captureSanitizedPage(tabId) {
  const frames = await executeScript(tabId, () => {
    const clone = document.documentElement.cloneNode(true);
    let removedElements = 0;
    let removedAttributes = 0;
    const blocked = "script,iframe,frame,frameset,object,embed,applet,portal,base,meta,link,form,input,button,select,textarea";
    for (const element of clone.querySelectorAll(blocked)) {
      element.remove();
      removedElements += 1;
    }
    const remoteAttrs = new Set(["src", "srcset", "poster", "background", "action", "formaction", "ping"]);
    for (const element of clone.querySelectorAll("*")) {
      for (const attribute of [...element.attributes]) {
        const name = attribute.name.toLowerCase();
        const value = attribute.value.trim().toLowerCase();
        if (name.startsWith("on") || name === "srcdoc" || name === "nonce" || name === "integrity" ||
            (remoteAttrs.has(name) && !value.startsWith("data:")) ||
            (name.endsWith("href") && element.localName !== "a" && !value.startsWith("data:")) ||
            (name === "href" && /^(javascript:|data:|file:|blob:)/.test(value))) {
          element.removeAttribute(attribute.name);
          removedAttributes += 1;
        }
      }
    }
    const selection = String(window.getSelection() || "").slice(0, 500);
    const html = "<!doctype html>\n" + clone.outerHTML;
    const byteLength = new TextEncoder().encode(html).byteLength;
    if (byteLength > 4500000) {
      return { error: "This page is larger than the 4.5 MB browser capture limit." };
    }
    return {
      html,
      source_url: location.href,
      title: document.title.slice(0, 500),
      selection,
      resources: {
        count: document.images.length + document.styleSheets.length + document.querySelectorAll("video,audio").length,
        removed_elements: removedElements,
        removed_attributes: removedAttributes
      }
    };
  });
  const result = frames && frames[0] ? frames[0].result : null;
  if (!result) throw new Error("The page did not allow browser capture.");
  if (result.error) throw new Error(result.error);
  return result;
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

function normalizePendingSave(payload, reason = "API unavailable", source = "context_menu") {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    source,
    reason,
    attempts: 0,
    created_at: new Date().toISOString(),
    payload: {
      url: payload.url,
      title: payload.title || payload.url,
      category: payload.category || DEFAULTS.defaultCategory,
      tags: Array.isArray(payload.tags) ? payload.tags : (payload.tags || []),
      notes: payload.notes || "",
      read_later: Boolean(payload.read_later)
    }
  };
}

async function getPendingSaves() {
  const stored = await storageGet({ [PENDING_SAVES_KEY]: [] });
  return Array.isArray(stored[PENDING_SAVES_KEY]) ? stored[PENDING_SAVES_KEY] : [];
}

async function setPendingSaves(items) {
  await storageSet({ [PENDING_SAVES_KEY]: items.slice(-50) });
}

async function enqueuePendingSave(payload, reason = "API unavailable", source = "context_menu") {
  const pending = await getPendingSaves();
  const normalized = normalizePendingSave(payload, reason, source);
  const duplicate = pending.find(item => item.payload && item.payload.url === normalized.payload.url);
  if (duplicate) {
    duplicate.payload = normalized.payload;
    duplicate.reason = reason;
    duplicate.created_at = normalized.created_at;
  } else {
    pending.push(normalized);
  }
  await setPendingSaves(pending);
  return pending.length;
}

async function retryPendingSaves() {
  const config = await getConfig();
  const pending = await getPendingSaves();
  const remaining = [];
  let resolved = 0;
  for (const item of pending) {
    try {
      const result = await saveBookmarkPayload(item.payload, config);
      if (result.status === 201 || result.status === 409) {
        resolved += 1;
      } else {
        remaining.push({ ...item, attempts: (item.attempts || 0) + 1, reason: `HTTP ${result.status}` });
      }
    } catch {
      remaining.push({ ...item, attempts: (item.attempts || 0) + 1, reason: "API unavailable" });
    }
  }
  await setPendingSaves(remaining);
  return { attempted: pending.length, resolved, remaining: remaining.length };
}

async function clearPendingSaves() {
  const pending = await getPendingSaves();
  await setPendingSaves([]);
  return pending.length;
}
