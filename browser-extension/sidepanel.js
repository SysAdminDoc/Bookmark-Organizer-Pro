/* global DEFAULTS, api, storageGet, queryTabs, executeScript, getConfig,
          baseUrl, authHeaders, isSaveableUrl, loadCategories, saveBookmarkPayload, captureSanitizedPage,
          getPendingSaves, retryPendingSaves, clearPendingSaves */

const RECENT_PAGE_SIZE = 30;
let recentOffset = 0;
let recentHasMore = false;
let recentLoading = false;

class ApiResponseError extends Error {
  constructor(status) {
    super(`HTTP ${status}`);
    this.status = status;
  }
}

async function apiFetch(path, config) {
  const response = await fetch(`${baseUrl(config)}${path}`, {
    headers: authHeaders(config)
  });
  if (!response.ok) throw new ApiResponseError(response.status);
  return response.json();
}

function renderBookmark(bm) {
  const li = document.createElement("li");
  const a = document.createElement("a");
  a.className = "bookmark-item";
  a.href = bm.url;
  a.target = "_blank";
  a.rel = "noopener";

  const title = document.createElement("span");
  title.className = "bookmark-title";
  title.textContent = bm.title || bm.url;

  const meta = document.createElement("div");
  meta.className = "bookmark-meta";

  try {
    const domain = document.createElement("span");
    domain.className = "bookmark-domain";
    domain.textContent = new URL(bm.url).hostname.replace(/^www\./, "");
    meta.appendChild(domain);
  } catch { /* ignore invalid URLs */ }

  if (bm.category && bm.category !== "Uncategorized / Needs Review") {
    const cat = document.createElement("span");
    cat.className = "badge";
    cat.textContent = bm.category.split(" / ").pop();
    meta.appendChild(cat);
  }

  a.appendChild(title);
  a.appendChild(meta);
  li.appendChild(a);
  return li;
}

function showEmpty(container, message) {
  container.innerHTML = "";
  const empty = document.createElement(container.tagName === "UL" ? "li" : "p");
  empty.className = "empty-state";
  empty.textContent = message;
  container.appendChild(empty);
}

function connectionMessage(error) {
  if (error instanceof ApiResponseError && error.status === 401) {
    return "The API token was rejected. Open Options and replace it.";
  }
  if (error instanceof ApiResponseError) {
    return `The local API returned ${error.status}. Try again or check the app logs.`;
  }
  return "Cannot reach the local API. Start the app or run: bop api-server";
}

function setRecentLoadMore(hasMore, label = "Load More") {
  const button = document.getElementById("loadMoreRecent");
  if (!button) return;
  recentHasMore = Boolean(hasMore);
  button.hidden = !recentHasMore;
  button.disabled = false;
  button.textContent = label;
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
  const text = document.getElementById("statusText");
  text.textContent = result.remaining ? `${result.remaining} pending save(s) remain` : "Pending saves resolved";
  await refreshPendingPanel();
  if (result.resolved) loadRecent();
}

async function clearPendingQueue() {
  const cleared = await clearPendingSaves();
  document.getElementById("statusText").textContent = `Cleared ${cleared} pending save(s)`;
  await refreshPendingPanel();
}

async function loadRecent({ append = false } = {}) {
  if (recentLoading) return;
  recentLoading = true;
  const list = document.getElementById("recentList");
  list.setAttribute("aria-busy", "true");
  const loadMore = document.getElementById("loadMoreRecent");
  if (loadMore) {
    loadMore.disabled = true;
    loadMore.textContent = append
      ? extensionMessage("loading", [], "Loading...")
      : extensionMessage("loadMore", [], "Load More");
  }
  try {
    const config = await getConfig();
    if (!config.apiToken) {
      showEmpty(list, "Add the API token in Options to connect.");
      setRecentLoadMore(false);
      return;
    }
    if (!append) recentOffset = 0;
    const data = await apiFetch(`/bookmarks?limit=${RECENT_PAGE_SIZE}&offset=${recentOffset}`, config);
    const bookmarks = data.bookmarks || [];
    if (!bookmarks.length && !append) {
      showEmpty(list, "No bookmarks yet. Save the current page from the Add tab.");
      setRecentLoadMore(false);
      return;
    }
    if (!append) list.innerHTML = "";
    for (const bm of bookmarks) {
      list.appendChild(renderBookmark(bm));
    }
    recentOffset = Number.isInteger(data.next_offset) ? data.next_offset : recentOffset + bookmarks.length;
    setRecentLoadMore(Boolean(data.has_more));
  } catch (error) {
    if (append) {
      setRecentLoadMore(recentHasMore, "Retry");
    } else {
      showEmpty(list, connectionMessage(error));
      setRecentLoadMore(false);
    }
  } finally {
    recentLoading = false;
    list.setAttribute("aria-busy", "false");
  }
}

async function loadRediscover() {
  const section = document.getElementById("rediscoverSection");
  const list = document.getElementById("rediscoverList");
  try {
    const config = await getConfig();
    if (!config.apiToken) return;
    const data = await apiFetch("/digest?count=5", config);
    const allBookmarks = (data.sections || []).flatMap(s => s.bookmarks || []);
    if (!allBookmarks.length) return;
    list.innerHTML = "";
    for (const bm of allBookmarks.slice(0, 5)) {
      list.appendChild(renderBookmark(bm));
    }
    section.style.display = "block";
  } catch {
    /* silently skip if digest unavailable */
  }
}

async function doSearch(query) {
  const results = document.getElementById("searchResults");
  if (!query.trim()) {
    showEmpty(results, "Type a query and press Go.");
    return;
  }
  try {
    const config = await getConfig();
    const data = await apiFetch(`/search?q=${encodeURIComponent(query)}`, config);
    const hits = data.results || [];
    if (!hits.length) {
      showEmpty(results, `No results for "${query}".`);
      return;
    }
    results.innerHTML = "";
    for (const bm of hits.slice(0, 50)) {
      results.appendChild(renderBookmark(bm));
    }
  } catch (error) {
    showEmpty(results, connectionMessage(error));
  }
}

async function checkConnection() {
  const dot = document.getElementById("statusDot");
  const text = document.getElementById("statusText");
  const count = document.getElementById("totalCount");
  try {
    const config = await getConfig();
    if (!config.apiToken) {
      dot.classList.remove("connected", "error");
      text.textContent = extensionMessage("noApiToken", [], "No API token");
      return;
    }
    const stats = await apiFetch("/stats", config);
    dot.classList.add("connected");
    dot.classList.remove("error");
    text.textContent = extensionMessage("connected", [], "Connected");
    count.textContent = `${stats.total_bookmarks || 0} bookmarks`;
  } catch (error) {
    dot.classList.remove("connected");
    dot.classList.add("error");
    text.textContent = error instanceof ApiResponseError && error.status === 401
      ? "Token rejected"
      : "Disconnected";
    count.textContent = "";
  }
}

async function loadAddTab() {
  const [tab] = await queryTabs({ active: true, currentWindow: true });
  const titleEl = document.getElementById("addPageTitle");
  if (tab && tab.url && isSaveableUrl(tab.url)) {
    titleEl.textContent = tab.title || tab.url;
    titleEl.dataset.url = tab.url;
    titleEl.dataset.tabTitle = tab.title || tab.url;
    titleEl.dataset.tabId = tab.id;
  } else {
    titleEl.textContent = extensionMessage("openWebPage", [], "Open an HTTP/HTTPS page to save.");
    titleEl.dataset.url = "";
  }
}

async function saveBookmark() {
  const titleEl = document.getElementById("addPageTitle");
  const saveBtn = document.getElementById("addSaveBtn");
  const url = titleEl.dataset.url;
  if (!url) {
    setAddStatus("No saveable page.", "error");
    return;
  }
  const config = await getConfig();
  if (!config.apiToken) {
    setAddStatus("Set API token in Options.", "error");
    return;
  }

  const payload = {
    url,
    title: titleEl.dataset.tabTitle || url,
    category: document.getElementById("addCategory").value.trim() || config.defaultCategory,
    tags: document.getElementById("addTags").value,
    notes: document.getElementById("addNotes").value,
    read_later: document.getElementById("addReadLater").checked
  };

  try {
    saveBtn.disabled = true;
    saveBtn.textContent = extensionMessage("saving", [], "Saving...");
    if (document.getElementById("addCaptureSnapshot").checked) {
      setAddStatus(extensionMessage("sanitizingPage", [], "Sanitizing this page before upload..."), "info");
      const tabs = await queryTabs({ active: true, currentWindow: true });
      if (!tabs[0] || tabs[0].url !== url) throw new Error("The active page changed before capture.");
      payload.browser_snapshot = await captureSanitizedPage(tabs[0].id);
    }
    const result = await saveBookmarkPayload(payload, config);
    if (result.status === 201) {
      const preserved = result.body && result.body.browser_snapshot;
      setAddStatus(preserved
        ? extensionMessage("savedWithOfflineCopy", [], "Saved with a sanitized offline copy. No cookies were sent.")
        : extensionMessage("savedToLibrary", [], "Saved to your library."), "success");
      loadRecent();
    } else if (result.status === 409) {
      setAddStatus(extensionMessage("alreadyInLibrary", [], "Already in your library."), "success");
    } else if (result.status === 401) {
      setAddStatus(extensionMessage("invalidToken", [], "Invalid token. Check Options."), "error");
    } else {
      setAddStatus(`Save failed (${result.status}).`, "error");
    }
  } catch (error) {
    setAddStatus(error?.message || "Cannot reach the local API. Start the app or run: bop api-server", "error");
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = extensionMessage("saveBookmark", [], "Save Bookmark");
  }
}

function setAddStatus(message, tone) {
  const el = document.getElementById("addStatus");
  el.textContent = message;
  el.dataset.tone = tone || "info";
}

async function importReadingList() {
  const button = document.getElementById("importReadingListBtn");
  if (!api.readingList || !api.readingList.query) {
    setAddStatus("Reading List API not available in this browser.", "error");
    return;
  }
  try {
    button.disabled = true;
    button.textContent = extensionMessage("importing", [], "Importing...");
    const config = await getConfig();
    if (!config.apiToken) {
      setAddStatus("Set API token in Options first.", "error");
      return;
    }
    const items = await api.readingList.query({});
    if (!items || items.length === 0) {
      setAddStatus(extensionMessage("readingListEmpty", [], "Reading list is empty."), "info");
      return;
    }
    let imported = 0;
    let duplicates = 0;
    let failed = 0;
    for (const item of items) {
      if (!item.url || !/^https?:\/\//i.test(item.url)) continue;
      try {
        const response = await fetch(`${baseUrl(config)}/bookmarks`, {
          method: "POST",
          headers: authHeaders(config),
          body: JSON.stringify({
            url: item.url,
            title: item.title || item.url,
            category: config.defaultCategory,
            read_later: !item.hasBeenRead
          })
        });
        if (response.status === 201) imported++;
        else if (response.status === 409) duplicates++;
        else failed++;
      } catch { failed++; }
    }
    const itemWord = items.length === 1 ? "item" : "items";
    const detail = duplicates ? `; ${duplicates} already saved` : "";
    const failureDetail = failed ? `; ${failed} failed` : "";
    setAddStatus(`Imported ${imported} of ${items.length} reading list ${itemWord}${detail}${failureDetail}.`, failed ? "error" : "success");
    if (imported > 0) loadRecent();
  } catch {
    setAddStatus("Could not access reading list.", "error");
  } finally {
    button.disabled = false;
    button.textContent = extensionMessage("readingList", [], "Reading List");
  }
}

function openOptionsPage() {
  if (api.runtime.openOptionsPage.length === 0) {
    return Promise.resolve(api.runtime.openOptionsPage());
  }
  return new Promise(resolve => api.runtime.openOptionsPage(resolve));
}

function switchTab(tabName) {
  for (const btn of document.querySelectorAll(".tab-btn")) {
    const active = btn.dataset.tab === tabName;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
    btn.tabIndex = active ? 0 : -1;
  }
  for (const content of document.querySelectorAll(".tab-content")) {
    const active = content.id === `tab-${tabName}`;
    content.classList.toggle("active", active);
    content.hidden = !active;
  }
  if (tabName === "add") loadAddTab();
}

document.addEventListener("DOMContentLoaded", () => {
  const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
  for (const btn of tabButtons) {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    btn.addEventListener("keydown", event => {
      const current = tabButtons.indexOf(btn);
      let next = current;
      if (event.key === "ArrowRight") next = (current + 1) % tabButtons.length;
      else if (event.key === "ArrowLeft") next = (current - 1 + tabButtons.length) % tabButtons.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabButtons.length - 1;
      else return;
      event.preventDefault();
      tabButtons[next].focus();
      switchTab(tabButtons[next].dataset.tab);
    });
  }

  document.getElementById("searchBtn").addEventListener("click", () => {
    doSearch(document.getElementById("searchInput").value);
  });
  document.getElementById("searchInput").addEventListener("keydown", e => {
    if (e.key === "Enter") doSearch(e.target.value);
  });

  document.getElementById("addSaveBtn").addEventListener("click", saveBookmark);
  document.getElementById("importReadingListBtn").addEventListener("click", importReadingList);
  document.getElementById("openOptions").addEventListener("click", () => {
    openOptionsPage().catch(() => {
      document.getElementById("statusText").textContent = "Options could not be opened";
    });
  });
  document.getElementById("loadMoreRecent").addEventListener("click", () => {
    loadRecent({ append: true });
  });
  document.getElementById("retryPending").addEventListener("click", () => {
    retryPendingQueue().catch(() => {
      document.getElementById("statusText").textContent = "Pending retry failed";
    });
  });
  document.getElementById("clearPending").addEventListener("click", () => {
    clearPendingQueue().catch(() => {
      document.getElementById("statusText").textContent = "Pending queue could not be cleared";
    });
  });

  checkConnection();
  refreshPendingPanel().catch(() => {});
  loadRecent();
  loadRediscover();
  loadCategories("categoryList");
});

if (api.tabs && api.tabs.onActivated) {
  api.tabs.onActivated.addListener(() => {
    const addTab = document.getElementById("tab-add");
    if (addTab && addTab.classList.contains("active")) loadAddTab();
  });
}
