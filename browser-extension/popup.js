/* global DEFAULTS, api, storageGet, queryTabs, executeScript, getConfig,
          isSaveableUrl, loadCategories, saveBookmarkPayload, captureSanitizedPage, getPendingSaves,
          retryPendingSaves, clearPendingSaves */

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
  const button = document.getElementById("saveBookmark");
  button.disabled = isBusy;
  button.textContent = isBusy
    ? extensionMessage("saving", [], "Saving...")
    : extensionMessage("saveBookmark", [], "Save Bookmark");
}

function setUnavailable(message) {
  const button = document.getElementById("saveBookmark");
  button.disabled = true;
  button.textContent = extensionMessage("unavailable", [], "Unavailable");
  setStatus(message, "error");
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
  document.getElementById("pageTitle").textContent = activeTab?.title ||
    extensionMessage("noActiveTab", [], "No active tab");

  if (!activeTab || !isSaveableUrl(activeTab.url)) {
    setUnavailable("Open an HTTP or HTTPS page before saving.");
    return;
  }

  if (!values.apiToken) {
    setUnavailable("Add the local API token in Options before saving.");
    return;
  }

  const selection = await getSelection(activeTab.id);
  if (selection) {
    document.getElementById("notes").value = `Selected: ${selection}`;
  }

  await loadCategories("categoryList");
}

async function refreshPendingPanel() {
  const panel = document.getElementById("pendingPanel");
  const count = document.getElementById("pendingCount");
  const pending = await getPendingSaves();
  panel.hidden = pending.length === 0;
  count.textContent = `${pending.length} pending quick save${pending.length === 1 ? "" : "s"}`;
}

async function retryPendingQueue() {
  const result = await retryPendingSaves();
  setStatus(`Retried ${result.attempted}; resolved ${result.resolved}.`, result.remaining ? "warning" : "success");
  await refreshPendingPanel();
}

async function clearPendingQueue() {
  const cleared = await clearPendingSaves();
  setStatus(`Cleared ${cleared} pending quick save${cleared === 1 ? "" : "s"}.`, "info");
  await refreshPendingPanel();
}

async function saveBookmark() {
  if (!activeTab || !isSaveableUrl(activeTab.url)) {
    setStatus(extensionMessage("pageCannotBeSaved", [], "This page cannot be saved."), "error");
    return;
  }

  const values = await getConfig();
  if (!values.apiToken) {
    setStatus(extensionMessage("addTokenBeforeSaving", [], "Add the local API token in Options before saving."), "error");
    return;
  }

  setBusy(true);
  setStatus(extensionMessage("saving", [], "Saving..."));

  const payload = {
    url: activeTab.url,
    title: activeTab.title || activeTab.url,
    category: document.getElementById("category").value.trim() || values.defaultCategory,
    tags: document.getElementById("tags").value,
    notes: document.getElementById("notes").value,
    read_later: document.getElementById("readLater").checked
  };

  try {
    if (document.getElementById("captureSnapshot").checked) {
      setStatus(extensionMessage("sanitizingPage", [], "Sanitizing this page before upload..."));
      payload.browser_snapshot = await captureSanitizedPage(activeTab.id);
    }
    const result = await saveBookmarkPayload(payload, values);
    if (result.status === 201) {
      const preserved = result.body && result.body.browser_snapshot;
      setStatus(preserved
        ? extensionMessage("savedWithOfflineCopy", [], "Saved with a sanitized offline copy. No cookies were sent.")
        : extensionMessage("savedToLibrary", [], "Saved to your library."), "success");
    } else if (result.status === 409) {
      setStatus(extensionMessage("alreadyInLibrary", [], "Already in your library."), "success");
    } else if (result.status === 401) {
      setStatus(extensionMessage("invalidToken", [], "Invalid API token. Check Options."), "error");
    } else {
      setStatus(`Save failed (${result.status}).`, "error");
    }
  } catch (error) {
    setStatus(error?.message || "Cannot reach the local API. Start the app or run: bop api-server", "error");
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
  document.getElementById("retryPending").addEventListener("click", () => {
    retryPendingQueue().catch(() => setStatus("Pending retry failed.", "error"));
  });
  document.getElementById("clearPending").addEventListener("click", () => {
    clearPendingQueue().catch(() => setStatus("Pending queue could not be cleared.", "error"));
  });
  refreshPendingPanel().catch(() => {});
  loadPopup().catch(() => setStatus("Could not load the active tab.", "error"));
});
