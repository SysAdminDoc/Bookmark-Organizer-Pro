// Chromium runs this file as a service worker and needs importScripts.
// Firefox loads the same dependencies first through background.scripts.
if (typeof importScripts === "function") {
  importScripts("i18n.js", "shared.js");
  importScripts("credential-vault.js");
}

function storageRemove(keys) {
  if (api.storage.local.remove.length === 1) {
    return api.storage.local.remove(keys);
  }
  return new Promise((resolve, reject) => api.storage.local.remove(keys, () => {
    const error = api.runtime.lastError;
    if (error) { reject(new Error("Legacy credentials could not be removed")); return; }
    resolve();
  }));
}

async function restrictLocalStorageAccess() {
  if (!api.storage.local.setAccessLevel) return;
  try {
    await api.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" });
  } catch {
    // Firefox does not currently expose setAccessLevel. The credential is kept
    // in background-owned IndexedDB there, never in extension local storage.
  }
}

async function initializeCredentialVault() {
  await restrictLocalStorageAccess();
  const legacy = await storageGet({ apiToken: "" });
  const legacyToken = typeof legacy.apiToken === "string" ? legacy.apiToken.trim() : "";
  if (!legacyToken) return;
  await CredentialVault.setToken(legacyToken);
  await storageRemove("apiToken");
}

const credentialReady = initializeCredentialVault();

async function getTrustedConfig() {
  await credentialReady;
  const publicDefaults = {
    apiPort: DEFAULTS.apiPort,
    defaultCategory: DEFAULTS.defaultCategory
  };
  const stored = await storageGet(publicDefaults);
  return normalizeConfig({ ...stored, apiToken: await CredentialVault.getToken() });
}

async function handleTrustedMessage(message) {
  if (!message || typeof message !== "object") return null;
  if (message.type === "bop:get-config") {
    return { ok: true, config: await getTrustedConfig() };
  }
  if (message.type === "bop:set-api-token") {
    await credentialReady;
    await CredentialVault.setToken(message.apiToken);
    await storageRemove("apiToken");
    return { ok: true };
  }
  if (message.type === "bop:clear-api-token") {
    await credentialReady;
    await CredentialVault.clearToken();
    await storageRemove("apiToken");
    return { ok: true };
  }
  return null;
}

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const trustedRoot = api.runtime.getURL("");
  if (!sender || sender.id !== api.runtime.id || !String(sender.url || "").startsWith(trustedRoot)) return false;
  if (!message || ![
    "bop:get-config", "bop:set-api-token", "bop:clear-api-token"
  ].includes(message.type)) return false;
  handleTrustedMessage(message)
    .then(result => sendResponse(result))
    .catch(() => sendResponse({ ok: false, error: "Credential operation failed" }));
  return true;
});

api.runtime.onInstalled.addListener(() => {
  api.contextMenus.create({
    id: "save-to-bop",
    title: extensionMessage("popupTitle", [], "Save to Bookmark Organizer Pro"),
    contexts: ["page", "link"]
  });
  api.contextMenus.create({
    id: "save-to-bop-selection",
    title: extensionMessage("saveWithSelection", [], "Save to BOP with selection"),
    contexts: ["selection"]
  });
  api.contextMenus.create({
    id: "open-bop-sidepanel",
    title: extensionMessage("openSidePanel", [], "Open BOP Side Panel"),
    contexts: ["page"]
  });

  if (api.sidePanel && api.sidePanel.setPanelBehavior) {
    api.sidePanel.setPanelBehavior({ openPanelOnActionClick: false })
      .catch(() => {});
  }
});

async function quickSave(url, title, notes, source = "context_menu") {
  const values = await getTrustedConfig();
  if (!values.apiToken) {
    return { outcome: "not_configured", saved: false, queued: false, dropped: false };
  }
  if (!/^https?:\/\//i.test(url || "")) {
    return { outcome: "unsupported_url", saved: false, queued: false, dropped: false };
  }
  const payload = {
    url,
    title: title || url,
    category: values.defaultCategory,
    tags: [],
    notes: notes || ""
  };

  // The shared client owns enqueuePendingSave so every capture surface deduplicates identically.
  const result = await saveBookmarkPayload(payload, values, { source });
  const saved = isSavedStatus(result.status) || result.status === 409;
  // Every capture surface reports the same three outcomes. Returning a bare
  // boolean here meant a context-menu save that was queued, or refused because
  // the queue was full, looked exactly like a failure that had been recorded.
  if (saved) return { outcome: "saved", saved: true, queued: false, dropped: false };
  if (result.queued) return { outcome: "queued", saved: false, queued: true, dropped: false };
  if (result.dropped) {
    return { outcome: "dropped", saved: false, queued: false, dropped: true, message: result.message };
  }
  return { outcome: "failed", saved: false, queued: false, dropped: false };
}

api.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "open-bop-sidepanel") {
    if (api.sidePanel && api.sidePanel.open) {
      try {
        await api.sidePanel.open({ windowId: tab.windowId });
      } catch { /* sidePanel API unavailable in this browser */ }
    } else if (api.sidebarAction && api.sidebarAction.open) {
      try {
        await api.sidebarAction.open();
      } catch { /* Firefox sidebar could not be opened for this window */ }
    }
    return;
  }

  let url = info.linkUrl || info.pageUrl || (tab && tab.url) || "";
  let title = tab && tab.title || url;
  let notes = "";

  if (info.menuItemId === "save-to-bop-selection" && info.selectionText) {
    notes = `Selected: ${info.selectionText.slice(0, 500)}`;
  }

  const source = info.menuItemId === "save-to-bop-selection" ? "selection" : "context_menu";
  const result = await quickSave(url, title, notes, source);
  // A context-menu save has no panel to report into, so the badge is the only
  // place the outcome can land. Ignoring it was how a queued or refused capture
  // became invisible.
  await refreshPendingBadge();
  return result;
});
