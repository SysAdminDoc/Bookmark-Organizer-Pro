/* global DEFAULTS, api, storageGet, queryTabs, executeScript, getConfig,
          baseUrl, authHeaders, isSaveableUrl, loadCategories */

let activeTab = null;

function openOptionsPage() {
  if (api.runtime.openOptionsPage.length === 0) {
    const result = api.runtime.openOptionsPage();
    return result && typeof result.then === "function" ? result : Promise.resolve();
  }
  return new Promise(resolve => api.runtime.openOptionsPage(resolve));
}

function setStatus(message, tone = "info") {
  const status = document.getElementById("status");
  status.textContent = message;
  status.dataset.tone = tone;
}

function setBusy(isBusy) {
  document.getElementById("saveBookmark").disabled = isBusy;
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
  const values = await getConfig();

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

  await loadCategories("categoryList");
}

async function saveBookmark() {
  if (!activeTab || !isSaveableUrl(activeTab.url)) {
    setStatus("This page cannot be saved.", "error");
    return;
  }

  const values = await getConfig();
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
    notes: document.getElementById("notes").value,
    read_later: document.getElementById("readLater").checked
  };

  try {
    const response = await fetch(`${baseUrl(values)}/bookmarks`, {
      method: "POST",
      headers: authHeaders(values),
      body: JSON.stringify(payload)
    });
    const body = await response.json().catch(() => ({}));
    if (response.status === 201) {
      setStatus("Saved.", "success");
    } else if (response.status === 409) {
      setStatus("Already saved.", "success");
    } else if (response.status === 401) {
      setStatus("Invalid API token. Check Options.", "error");
    } else {
      setStatus(body.error || `Save failed (${response.status}).`, "error");
    }
  } catch {
    setStatus("API not reachable. Start BOP or run: bop api-server", "error");
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
