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

async function getPendingSaves() {
  const stored = await storageGet({ [PENDING_SAVES_KEY]: [] });
  return Array.isArray(stored[PENDING_SAVES_KEY]) ? stored[PENDING_SAVES_KEY] : [];
}

async function enqueuePendingSave(payload, reason) {
  const pending = await getPendingSaves();
  const normalized = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    source: "context_menu",
    reason,
    attempts: 0,
    created_at: new Date().toISOString(),
    payload
  };
  const duplicate = pending.find(item => item.payload && item.payload.url === payload.url);
  if (duplicate) {
    duplicate.payload = payload;
    duplicate.reason = reason;
    duplicate.created_at = normalized.created_at;
  } else {
    pending.push(normalized);
  }
  await storageSet({ [PENDING_SAVES_KEY]: pending.slice(-50) });
}

api.runtime.onInstalled.addListener(() => {
  api.contextMenus.create({
    id: "save-to-bop",
    title: "Save to Bookmark Organizer Pro",
    contexts: ["page", "link"]
  });
  api.contextMenus.create({
    id: "save-to-bop-selection",
    title: "Save to BOP with selection",
    contexts: ["selection"]
  });
  api.contextMenus.create({
    id: "open-bop-sidepanel",
    title: "Open BOP Side Panel",
    contexts: ["page"]
  });

  if (api.sidePanel && api.sidePanel.setPanelBehavior) {
    api.sidePanel.setPanelBehavior({ openPanelOnActionClick: false })
      .catch(() => {});
  }
});

async function quickSave(url, title, notes) {
  const values = { ...DEFAULTS, ...(await storageGet(DEFAULTS)) };
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
