/* global DEFAULTS, api, storageGet, queryTabs, executeScript, getConfig,
          isSaveableUrl, loadCategories, saveBookmarkPayload, captureSanitizedPage, getPendingSaves,
          retryPendingSaves, clearPendingSaves, getClearedPendingSaves, restoreClearedPendingSaves,
          renderPendingSaves, exportPendingSaves */

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
    setUnavailable(extensionMessage("openWebPage", [], "Open an HTTP or HTTPS page before saving."));
    return;
  }

  if (!values.apiToken) {
    setUnavailable(extensionMessage("addTokenBeforeSaving", [], "Add the local API token in Options before saving."));
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
  const cleared = await getClearedPendingSaves();
  panel.hidden = pending.length === 0 && !cleared;
  count.textContent = pending.length
    ? pending.length === 1
      ? extensionMessage("onePendingSave", [], "1 pending save")
      : extensionMessage("pendingSavesCount", [String(pending.length)], `${pending.length} pending saves`)
    : cleared
      ? extensionMessage("clearedSavesRestorable", [String(cleared.items.length)], `${cleared.items.length} cleared saves can be restored`)
      : extensionMessage("zeroPendingSaves", [], "0 pending saves");
  renderPendingSaves(document.getElementById("pendingList"), pending);
  document.getElementById("retryPending").disabled = pending.length === 0;
  document.getElementById("exportPending").disabled = pending.length === 0;
  document.getElementById("clearPending").disabled = pending.length === 0;
  document.getElementById("restorePending").hidden = !cleared;
}

async function retryPendingQueue() {
  const result = await retryPendingSaves();
  setStatus(extensionMessage(
    "retriedPendingSaves",
    [String(result.attempted), String(result.resolved)],
    `Retried ${result.attempted}; resolved ${result.resolved}.`,
  ), result.remaining ? "warning" : "success");
  await refreshPendingPanel();
}

async function clearPendingQueue() {
  if (!globalThis.confirm(extensionMessage(
    "confirmClearPending",
    [],
    "Clear the pending save journal? You can undo this from the same panel.",
  ))) return;
  const cleared = await clearPendingSaves({ confirmed: true });
  setStatus(cleared === 1
    ? extensionMessage("clearedOnePendingSave", [], "Cleared 1 pending save")
    : extensionMessage("clearedPendingSaves", [String(cleared)], `Cleared ${cleared} pending saves`), "info");
  await refreshPendingPanel();
}

async function restorePendingQueue() {
  const restored = await restoreClearedPendingSaves();
  setStatus(restored === 1
    ? extensionMessage("restoredOnePendingSave", [], "Restored 1 pending save")
    : extensionMessage("restoredPendingSaves", [String(restored)], `Restored ${restored} pending saves`), "success");
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
    const result = await saveBookmarkPayload(payload, values, { source: "popup" });
    if (result.queued) {
      setStatus(extensionMessage("queuedSave", [], "API unavailable. Save added to the retry journal."), "warning");
      await refreshPendingPanel();
    } else if (result.status === 201) {
      const preserved = result.body && result.body.browser_snapshot;
      setStatus(preserved
        ? extensionMessage("savedWithOfflineCopy", [], "Saved with a sanitized offline copy. No cookies were sent.")
        : extensionMessage("savedToLibrary", [], "Saved to your library."), "success");
    } else if (result.status === 409) {
      setStatus(extensionMessage("alreadyInLibrary", [], "Already in your library."), "success");
    } else if (result.status === 401) {
      setStatus(extensionMessage("invalidToken", [], "Invalid API token. Check Options."), "error");
    } else {
      setStatus(extensionMessage("saveFailed", [String(result.status)], `Save failed (${result.status}).`), "error");
    }
  } catch (error) {
    setStatus(extensionMessage("apiUnavailable", [], "Cannot reach the local API. Start the app or run: bop api-server"), "error");
  } finally {
    setBusy(false);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("saveBookmark").addEventListener("click", () => {
    saveBookmark().catch(() => setStatus(extensionMessage("saveFailedGeneric", [], "Save failed."), "error"));
  });
  document.getElementById("openOptions").addEventListener("click", () => {
    openOptionsPage().catch(() => setStatus(extensionMessage("optionsOpenFailed", [], "Options could not be opened."), "error"));
  });
  document.getElementById("retryPending").addEventListener("click", () => {
    retryPendingQueue().catch(() => setStatus(extensionMessage("pendingRetryFailed", [], "Pending retry failed."), "error"));
  });
  document.getElementById("clearPending").addEventListener("click", () => {
    clearPendingQueue().catch(() => setStatus(extensionMessage("pendingClearFailed", [], "Pending queue could not be cleared."), "error"));
  });
  document.getElementById("restorePending").addEventListener("click", () => {
    restorePendingQueue().catch(() => setStatus(extensionMessage("pendingRestoreFailed", [], "Cleared saves could not be restored."), "error"));
  });
  document.getElementById("exportPending").addEventListener("click", () => {
    exportPendingSaves().then(count => setStatus(count === 1
      ? extensionMessage("exportedOnePendingSave", [], "Exported 1 pending save")
      : extensionMessage("exportedPendingSaves", [String(count)], `Exported ${count} pending saves`), "success"))
      .catch(() => setStatus(extensionMessage("pendingExportFailed", [], "Pending saves could not be exported."), "error"));
  });
  refreshPendingPanel().catch(() => {});
  loadPopup().catch(() => setStatus(extensionMessage("activeTabLoadFailed", [], "Could not load the active tab."), "error"));
});
