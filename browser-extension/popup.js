const DEFAULTS = {
  apiPort: 8765,
  apiToken: "",
  defaultCategory: "Uncategorized / Needs Review"
};

const api = globalThis.browser ?? globalThis.chrome;
let activeTab = null;

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

function openOptionsPage() {
  if (api.runtime.openOptionsPage.length === 0) {
    const result = api.runtime.openOptionsPage();
    return result && typeof result.then === "function" ? result : Promise.resolve();
  }
  return new Promise(resolve => api.runtime.openOptionsPage(resolve));
}

function executeScript(tabId, func) {
  if (!api.scripting || !api.scripting.executeScript) {
    return Promise.resolve([]);
  }
  const details = { target: { tabId }, func };
  if (api.scripting.executeScript.length === 1) {
    return api.scripting.executeScript(details);
  }
  return new Promise((resolve, reject) => {
    api.scripting.executeScript(details, result => {
      const error = api.runtime.lastError;
      if (error) {
        reject(new Error(error.message));
        return;
      }
      resolve(result);
    });
  });
}

function setStatus(message, tone = "info") {
  const status = document.getElementById("status");
  status.textContent = message;
  status.dataset.tone = tone;
}

function setBusy(isBusy) {
  document.getElementById("saveBookmark").disabled = isBusy;
}

function isSaveableUrl(url) {
  return /^https?:\/\//i.test(url || "");
}

async function getSelection(tabId) {
  try {
    const frames = await executeScript(tabId, () => String(window.getSelection() || "").slice(0, 500));
    return String(frames?.[0]?.result || "").trim();
  } catch {
    return "";
  }
}

async function loadPopup() {
  const [tab] = await queryTabs({ active: true, currentWindow: true });
  activeTab = tab || null;
  const values = { ...DEFAULTS, ...(await storageGet(DEFAULTS)) };

  document.getElementById("category").value = values.defaultCategory;
  document.getElementById("pageTitle").textContent = activeTab?.title || "No active tab";

  if (!activeTab || !isSaveableUrl(activeTab.url)) {
    setStatus("Open an HTTP or HTTPS page before saving.", "error");
    setBusy(true);
    return;
  }

  if (!values.apiToken) {
    setStatus("Set the local API token in Options.", "error");
    setBusy(true);
    return;
  }

  const selection = await getSelection(activeTab.id);
  if (selection) {
    document.getElementById("notes").value = `Selected: ${selection}`;
  }
}

async function saveBookmark() {
  if (!activeTab || !isSaveableUrl(activeTab.url)) {
    setStatus("This page cannot be saved.", "error");
    return;
  }

  const values = { ...DEFAULTS, ...(await storageGet(DEFAULTS)) };
  if (!values.apiToken) {
    setStatus("Set the local API token in Options.", "error");
    return;
  }

  setBusy(true);
  setStatus("Saving...");

  const payload = {
    url: activeTab.url,
    title: activeTab.title || activeTab.url,
    category: document.getElementById("category").value.trim() || values.defaultCategory,
    tags: document.getElementById("tags").value,
    notes: document.getElementById("notes").value
  };

  try {
    const response = await fetch(`http://127.0.0.1:${values.apiPort}/bookmarks`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${values.apiToken}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
    const body = await response.json().catch(() => ({}));
    if (response.status === 201) {
      setStatus("Saved.", "success");
    } else if (response.status === 409) {
      setStatus("Already saved.", "success");
    } else {
      setStatus(body.error || `Save failed (${response.status}).`, "error");
    }
  } catch {
    setStatus("Cannot reach the local API.", "error");
  } finally {
    setBusy(false);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("saveBookmark").addEventListener("click", () => {
    saveBookmark().catch(() => setStatus("Save failed.", "error"));
  });
  document.getElementById("openOptions").addEventListener("click", () => {
    openOptionsPage().catch(() => setStatus("Options could not be opened.", "error"));
  });
  loadPopup().catch(() => setStatus("Could not load the active tab.", "error"));
});
