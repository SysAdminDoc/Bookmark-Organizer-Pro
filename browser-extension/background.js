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
});

async function quickSave(url, title, notes) {
  const values = { ...DEFAULTS, ...(await storageGet(DEFAULTS)) };
  if (!values.apiToken) return;
  if (!/^https?:\/\//i.test(url || "")) return;

  try {
    const response = await fetch(`http://127.0.0.1:${values.apiPort}/bookmarks`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${values.apiToken}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        url,
        title: title || url,
        category: values.defaultCategory,
        tags: [],
        notes: notes || ""
      })
    });
    if (response.status === 201 || response.status === 409) {
      return true;
    }
  } catch { /* API unreachable */ }
  return false;
}

api.contextMenus.onClicked.addListener(async (info, tab) => {
  let url = info.linkUrl || info.pageUrl || (tab && tab.url) || "";
  let title = tab && tab.title || url;
  let notes = "";

  if (info.menuItemId === "save-to-bop-selection" && info.selectionText) {
    notes = `Selected: ${info.selectionText.slice(0, 500)}`;
  }

  await quickSave(url, title, notes);
});
