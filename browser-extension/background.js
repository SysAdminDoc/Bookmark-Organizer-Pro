importScripts("i18n.js", "shared.js");
importScripts("credential-vault.js");

function storageRemove(keys) {
  if (api.storage.local.remove.length === 1) {
    return api.storage.local.remove(keys);
  }
  return new Promise(resolve => api.storage.local.remove(keys, resolve));
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
  return { ...DEFAULTS, ...stored, apiToken: await CredentialVault.getToken() };
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
  return null;
}

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const trustedRoot = api.runtime.getURL("");
  if (!sender || sender.id !== api.runtime.id || !String(sender.url || "").startsWith(trustedRoot)) return false;
  if (!message || !["bop:get-config", "bop:set-api-token"].includes(message.type)) return false;
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

async function quickSave(url, title, notes) {
  const values = await getTrustedConfig();
  if (!values.apiToken) return;
  if (!/^https?:\/\//i.test(url || "")) return;
  const payload = {
    url,
    title: title || url,
    category: values.defaultCategory,
    tags: [],
    notes: notes || ""
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
    if (response.status === 201 || response.status === 409) {
      return true;
    }
    await enqueuePendingSave(payload, `HTTP ${response.status}`);
  } catch {
    await enqueuePendingSave(payload, "API unavailable");
  }
  return false;
}

api.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "open-bop-sidepanel") {
    if (api.sidePanel && api.sidePanel.open) {
      try {
        await api.sidePanel.open({ windowId: tab.windowId });
      } catch { /* sidePanel API unavailable in this browser */ }
    }
    return;
  }

  let url = info.linkUrl || info.pageUrl || (tab && tab.url) || "";
  let title = tab && tab.title || url;
  let notes = "";

  if (info.menuItemId === "save-to-bop-selection" && info.selectionText) {
    notes = `Selected: ${info.selectionText.slice(0, 500)}`;
  }

  await quickSave(url, title, notes);
});
