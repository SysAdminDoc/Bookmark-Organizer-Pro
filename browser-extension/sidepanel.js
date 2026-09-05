/* global DEFAULTS, api, storageGet, queryTabs, executeScript, getConfig,
          baseUrl, authHeaders, isSaveableUrl, loadCategories, saveBookmarkPayload, captureSanitizedPage,
          getPendingSaves, retryPendingSaves, clearPendingSaves, getClearedPendingSaves,
          restoreClearedPendingSaves, renderPendingSaves, exportPendingSaves, loadTagsForInput,
          normalizeTagInput */

const RECENT_PAGE_SIZE = 30;
const SEARCH_PAGE_SIZE = 30;
let recentOffset = 0;
let recentHasMore = false;
let recentLoading = false;
let searchDebounceTimer = null;
let searchRequestId = 0;
let searchOffset = 0;
let searchQuery = "";
let searchLoading = false;

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

  const glyph = document.createElement("span");
  glyph.className = "bookmark-glyph";
  glyph.setAttribute("aria-hidden", "true");
  glyph.textContent = "B";

  const title = document.createElement("span");
  title.className = "bookmark-title";
  title.textContent = bm.title || bm.url;

  const meta = document.createElement("div");
  meta.className = "bookmark-meta";

  try {
    const domain = document.createElement("span");
    domain.className = "bookmark-domain";
    domain.textContent = new URL(bm.url).hostname.replace(/^www\./, "");
    glyph.textContent = domain.textContent.charAt(0) || "B";
    meta.appendChild(domain);
  } catch { /* ignore invalid URLs */ }

  if (bm.category && bm.category !== "Uncategorized / Needs Review") {
    const cat = document.createElement("span");
    cat.className = "badge";
    cat.textContent = bm.category.split(" / ").pop();
    meta.appendChild(cat);
  }

  const arrow = document.createElement("span");
  arrow.className = "bookmark-arrow";
  arrow.setAttribute("aria-hidden", "true");
  arrow.textContent = "›";

  a.appendChild(glyph);
  a.appendChild(title);
  a.appendChild(meta);
  a.appendChild(arrow);
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
    return extensionMessage("tokenRejectedDetail", [], "The API token was rejected. Open Options and replace it.");
  }
  if (error instanceof ApiResponseError) {
    return extensionMessage(
      "apiReturnedError",
      [String(error.status)],
      `The local API returned ${error.status}. Try again or check the app logs.`,
    );
  }
  return extensionMessage("apiUnavailable", [], "Cannot reach the local API. Start the app or run: bop api-server");
}

function setSearchLoadMore(hasMore) {
  const button = document.getElementById("loadMoreSearch");
  if (!button) return;
  button.hidden = !hasMore;
  button.disabled = false;
  button.textContent = extensionMessage("loadMore", [], "Load More");
}

function setRecentLoadMore(hasMore, label = "") {
  const button = document.getElementById("loadMoreRecent");
  if (!button) return;
  recentHasMore = Boolean(hasMore);
  button.hidden = !recentHasMore;
  button.disabled = false;
  button.textContent = label || extensionMessage("loadMore", [], "Load More");
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
  const text = document.getElementById("statusText");
  text.textContent = result.remaining
    ? extensionMessage("pendingSavesRemain", [String(result.remaining)], `${result.remaining} pending saves remain`)
    : extensionMessage("pendingSavesResolved", [], "Pending saves resolved");
  await refreshPendingPanel();
  if (result.resolved) loadRecent();
}

async function clearPendingQueue() {
  const cleared = await clearPendingSaves();
  document.getElementById("statusText").textContent = cleared === 1
    ? extensionMessage("clearedOnePendingSaveUndo", [], "Cleared 1 pending save. Restore it below.")
    : extensionMessage(
        "clearedPendingSavesUndo", [String(cleared)],
        `Cleared ${cleared} pending saves. Restore them below.`,
      );
  await refreshPendingPanel();
}

async function restorePendingQueue() {
  const restored = await restoreClearedPendingSaves();
  document.getElementById("statusText").textContent = restored === 1
    ? extensionMessage("restoredOnePendingSave", [], "Restored 1 pending save")
    : extensionMessage("restoredPendingSaves", [String(restored)], `Restored ${restored} pending saves`);
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
      showEmpty(list, extensionMessage("addTokenToConnect", [], "Add the local API token in Options to connect."));
      setRecentLoadMore(false);
      return;
    }
    if (!append) recentOffset = 0;
    const data = await apiFetch(`/bookmarks?limit=${RECENT_PAGE_SIZE}&offset=${recentOffset}`, config);
    const bookmarks = data.bookmarks || [];
    if (!bookmarks.length && !append) {
      showEmpty(list, extensionMessage("noBookmarksYet", [], "No bookmarks yet. Save the current page from the Add tab."));
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
      setRecentLoadMore(recentHasMore, extensionMessage("retry", [], "Retry"));
    } else {
      showEmpty(list, connectionMessage(error));
      setRecentLoadMore(false);
    }
  } finally {
    recentLoading = false;
    list.setAttribute("aria-busy", "false");
    const recentCount = document.getElementById("recentCount");
    if (recentCount) recentCount.textContent = String(list.querySelectorAll(".bookmark-item").length);
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

async function doSearch(query, { append = false } = {}) {
  const requestId = ++searchRequestId;
  const results = document.getElementById("searchResults");
  const searchButton = document.getElementById("searchBtn");
  const searchStatus = document.getElementById("searchStatus");
  const normalizedQuery = String(query || "").trim();
  if (!normalizedQuery) {
    searchLoading = false;
    results.setAttribute("aria-busy", "false");
    searchButton.disabled = false;
    searchButton.textContent = extensionMessage("search", [], "Search");
    searchStatus.setAttribute("aria-busy", "false");
    searchStatus.dataset.tone = "info";
    searchStatus.textContent = extensionMessage("searchReady", [], "Enter a query to search bookmarks.");
    showEmpty(results, extensionMessage("typeQuery", [], "Type a query and press Go."));
    return;
  }
  searchLoading = true;
  results.setAttribute("aria-busy", "true");
  searchStatus.setAttribute("aria-busy", "true");
  searchStatus.dataset.tone = "info";
  searchStatus.textContent = extensionMessage("searchLoading", [], "Searching bookmarks...");
  searchButton.disabled = true;
  searchButton.textContent = extensionMessage("loading", [], "Loading...");
  try {
    const config = await getConfig();
    if (!config.apiToken) {
      if (requestId !== searchRequestId) return;
      showEmpty(results, extensionMessage("addTokenToConnect", [], "Add the local API token in Options to connect."));
      searchStatus.dataset.tone = "error";
      searchStatus.textContent = extensionMessage("addTokenToConnect", [], "Add the local API token in Options to connect.");
      return;
    }
    if (!append) searchOffset = 0;
    searchQuery = normalizedQuery;
    const data = await apiFetch(
      `/search?q=${encodeURIComponent(normalizedQuery)}&limit=${SEARCH_PAGE_SIZE}&offset=${searchOffset}`,
      config,
    );
    const hits = data.results || [];
    const total = typeof data.count === "number" ? data.count : hits.length;
    if (requestId !== searchRequestId) return;
    if (!hits.length && !append) {
      setSearchLoadMore(false);
      showEmpty(results, extensionMessage("noSearchResults", [normalizedQuery], `No results for "${normalizedQuery}".`));
      searchStatus.dataset.tone = "info";
      searchStatus.textContent = extensionMessage(
        "searchNoMatches", [normalizedQuery], `No bookmarks matched "${normalizedQuery}".`,
      );
      return;
    }
    if (!append) results.innerHTML = "";
    for (const bm of hits) {
      results.appendChild(renderBookmark(bm));
    }
    searchOffset += hits.length;
    setSearchLoadMore(Boolean(data.has_more));
    searchStatus.dataset.tone = "success";
    // Report the real total, not the page size: the panel used to say
    // "50 bookmarks found" for a 300-hit query with no way to see more.
    searchStatus.textContent = total === 1
      ? extensionMessage("searchResultOne", [], "1 bookmark found")
      : extensionMessage("searchResultCount", [String(total)], `${total} bookmarks found`);
  } catch (error) {
    if (requestId !== searchRequestId) return;
    showEmpty(results, connectionMessage(error));
    searchStatus.dataset.tone = "error";
    searchStatus.textContent = extensionMessage(
      "searchError", [], "Search could not be completed. Check the local API and try again.",
    );
  } finally {
    if (requestId === searchRequestId) {
      searchLoading = false;
      results.setAttribute("aria-busy", "false");
      searchStatus.setAttribute("aria-busy", "false");
      searchButton.disabled = false;
      searchButton.textContent = extensionMessage("search", [], "Search");
    }
  }
}

function scheduleSearch(query) {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  const normalizedQuery = String(query || "").trim();
  if (!normalizedQuery) {
    doSearch("");
    return;
  }
  const searchStatus = document.getElementById("searchStatus");
  searchStatus.textContent = extensionMessage("searchWaiting", [], "Waiting to search...");
  searchDebounceTimer = setTimeout(() => {
    searchDebounceTimer = null;
    doSearch(normalizedQuery);
  }, 250);
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
    const total = stats.total_bookmarks || 0;
    count.textContent = total === 1
      ? extensionMessage("oneBookmark", [], "1 bookmark")
      : extensionMessage("bookmarkCount", [String(total)], `${total} bookmarks`);
  } catch (error) {
    dot.classList.remove("connected");
    dot.classList.add("error");
    text.textContent = error instanceof ApiResponseError && error.status === 401
      ? extensionMessage("tokenRejected", [], "Token rejected")
      : extensionMessage("disconnected", [], "Disconnected");
    count.textContent = "";
  }
}

async function loadAddTab() {
  const [tabs, config] = await Promise.all([
    queryTabs({ active: true, currentWindow: true }),
    getConfig().catch(() => normalizeConfig(DEFAULTS)),
  ]);
  const tab = tabs[0];
  document.getElementById("addCategory").value = config.defaultCategory;
  renderDefaultCategoryAffordance(
    "addCategory", "addCategoryDefault", "addCategoryHint", config.defaultCategory,
  );
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
  await loadTagsForInput("addTags", config, {
    listId: "addTagSuggestions",
    statusId: "addTagSuggestionStatus",
  });
}

async function saveBookmark() {
  const titleEl = document.getElementById("addPageTitle");
  const saveBtn = document.getElementById("addSaveBtn");
  const url = titleEl.dataset.url;
  if (!url) {
    setAddStatus(extensionMessage("noSaveablePage", [], "No saveable page."), "error");
    return;
  }
  const config = await getConfig();
  if (!config.apiToken) {
    setAddStatus(extensionMessage("addTokenBeforeSaving", [], "Add the local API token in Options before saving."), "error");
    return;
  }

  const payload = {
    url,
    title: titleEl.dataset.tabTitle || url,
    category: document.getElementById("addCategory").value.trim() || config.defaultCategory,
    tags: normalizeTagInput(document.getElementById("addTags").value),
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
    const result = await saveBookmarkPayload(payload, config, { source: "side_panel" });
    if (result.queued) {
      setAddStatus(extensionMessage("queuedSave", [], "API unavailable. Save added to the retry journal."), "warning");
      await refreshPendingPanel();
    } else if (result.dropped) {
      // The queue refused it. Reporting the transport status here would say
      // "Save failed (0)", which names neither what happened nor what to do.
      setAddStatus(result.message || extensionMessage(
        "queueFull", [], "Offline queue is full. Retry the queued saves to make room."
      ), "error");
      await refreshPendingPanel();
    } else if (isSavedStatus(result.status)) {
      // An attach keeps the title, tags, and notes already on the row, so it
      // must not be reported as though this form's fields were saved.
      const attached = result.body && result.body.attached_to_existing;
      const preserved = result.body && result.body.browser_snapshot;
      setAddStatus(attached
        ? extensionMessage("offlineCopyAddedToExisting", [], "Already in your library. Offline copy added; the saved details were kept.")
        : preserved
          ? extensionMessage("savedWithOfflineCopy", [], "Saved with a sanitized offline copy. No cookies were sent.")
          : extensionMessage("savedToLibrary", [], "Saved to your library."), "success");
      loadRecent();
    } else if (result.status === 409) {
      setAddStatus(extensionMessage("alreadyInLibrary", [], "Already in your library."), "success");
    } else if (result.status === 401) {
      setAddStatus(extensionMessage("invalidToken", [], "Invalid token. Check Options."), "error");
    } else {
      setAddStatus(extensionMessage("saveFailed", [String(result.status)], `Save failed (${result.status}).`), "error");
    }
  } catch (error) {
    setAddStatus(extensionMessage("apiUnavailable", [], "Cannot reach the local API. Start the app or run: bop api-server"), "error");
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
    setAddStatus(extensionMessage("readingListUnavailable", [], "Reading List API not available in this browser."), "error");
    return;
  }
  try {
    button.disabled = true;
    button.textContent = extensionMessage("importing", [], "Importing...");
    const config = await getConfig();
    if (!config.apiToken) {
      setAddStatus(extensionMessage("addTokenBeforeSaving", [], "Add the local API token in Options before saving."), "error");
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
    let queued = 0;
    let dropped = 0;
    for (const item of items) {
      if (!item.url || !/^https?:\/\//i.test(item.url)) continue;
      try {
        const result = await saveBookmarkPayload({
          url: item.url,
          title: item.title || item.url,
          category: config.defaultCategory,
          read_later: !item.hasBeenRead
        }, config, { source: "reading_list" });
        if (isSavedStatus(result.status)) imported++;
        else if (result.status === 409) duplicates++;
        else if (result.queued) queued++;
        // A refused queue is not a failed request: nothing was attempted and
        // retrying the same import will refuse it again until room is made.
        else if (result.dropped) dropped++;
        else failed++;
      } catch { failed++; }
    }
    const itemWord = items.length === 1
      ? extensionMessage("readingListItem", [], "item")
      : extensionMessage("readingListItems", [], "items");
    const detail = duplicates
      ? extensionMessage("readingListAlreadySaved", [String(duplicates)], `; ${duplicates} already saved`)
      : "";
    const queueDetail = queued
      ? extensionMessage("readingListQueued", [String(queued)], `; ${queued} queued for retry`)
      : "";
    const droppedDetail = dropped
      ? extensionMessage("readingListDropped", [String(dropped)], `; ${dropped} refused, the offline queue is full`)
      : "";
    const failureDetail = failed
      ? extensionMessage("readingListFailed", [String(failed)], `; ${failed} failed`)
      : "";
    const trailer = `${detail}${queueDetail}${droppedDetail}${failureDetail}`;
    setAddStatus(extensionMessage(
      "readingListImportSummary",
      [String(imported), String(items.length), itemWord, trailer],
      `Imported ${imported} of ${items.length} reading list ${itemWord}${trailer}.`,
    ), (failed || dropped) ? "error" : (queued ? "warning" : "success"));
    if (queued || dropped) await refreshPendingPanel();
    if (imported > 0) loadRecent();
  } catch {
    setAddStatus(extensionMessage("readingListAccessFailed", [], "Could not access reading list."), "error");
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
    if (searchLoading) return;
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = null;
    doSearch(document.getElementById("searchInput").value);
  });
  document.getElementById("loadMoreSearch").addEventListener("click", () => {
    if (searchLoading || !searchQuery) return;
    doSearch(searchQuery, { append: true });
  });
  document.getElementById("searchInput").addEventListener("input", e => {
    scheduleSearch(e.target.value);
  });
  document.getElementById("searchInput").addEventListener("keydown", e => {
    if (e.key === "Enter") {
      if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
      searchDebounceTimer = null;
      doSearch(e.target.value);
    }
  });

  document.getElementById("addSaveBtn").addEventListener("click", saveBookmark);
  document.getElementById("importReadingListBtn").addEventListener("click", importReadingList);
  document.getElementById("openOptions").addEventListener("click", () => {
    openOptionsPage().catch(() => {
      document.getElementById("statusText").textContent = extensionMessage("optionsOpenFailed", [], "Options could not be opened");
    });
  });
  document.getElementById("loadMoreRecent").addEventListener("click", () => {
    loadRecent({ append: true });
  });
  document.getElementById("retryPending").addEventListener("click", () => {
    retryPendingQueue().catch(() => {
      document.getElementById("statusText").textContent = extensionMessage("pendingRetryFailed", [], "Pending retry failed");
    });
  });
  document.getElementById("clearPending").addEventListener("click", () => {
    clearPendingQueue().catch(() => {
      document.getElementById("statusText").textContent = extensionMessage("pendingClearFailed", [], "Pending queue could not be cleared");
    });
  });
  document.getElementById("restorePending").addEventListener("click", () => {
    restorePendingQueue().catch(() => {
      document.getElementById("statusText").textContent = extensionMessage("pendingRestoreFailed", [], "Cleared saves could not be restored");
    });
  });
  document.getElementById("exportPending").addEventListener("click", () => {
    exportPendingSaves().then(count => {
      document.getElementById("statusText").textContent = count === 1
        ? extensionMessage("exportedOnePendingSave", [], "Exported 1 pending save")
        : extensionMessage("exportedPendingSaves", [String(count)], `Exported ${count} pending saves`);
    }).catch(() => {
      document.getElementById("statusText").textContent = extensionMessage("pendingExportFailed", [], "Pending saves could not be exported");
    });
  });

  checkConnection();
  refreshPendingPanel().catch(() => {});
  loadRecent();
  loadRediscover();
  renderDefaultCategoryAffordance(
    "addCategory", "addCategoryDefault", "addCategoryHint", DEFAULTS.defaultCategory,
  );
  loadCategories("categoryList");
});

if (api.tabs && api.tabs.onActivated) {
  api.tabs.onActivated.addListener(() => {
    const addTab = document.getElementById("tab-add");
    if (addTab && addTab.classList.contains("active")) loadAddTab();
  });
}
