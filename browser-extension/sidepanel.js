/* global DEFAULTS, api, storageGet, queryTabs, executeScript, getConfig,
          baseUrl, authHeaders, isSaveableUrl, loadCategories */

async function apiFetch(path, config) {
  const response = await fetch(`${baseUrl(config)}${path}`, {
    headers: authHeaders(config)
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
  const p = document.createElement("p");
  p.className = "empty-state";
  p.textContent = message;
  container.appendChild(p);
}

async function loadRecent() {
  const list = document.getElementById("recentList");
  try {
    const config = await getConfig();
    if (!config.apiToken) {
      showEmpty(list, "Set API token in Options to connect.");
      return;
    }
    const data = await apiFetch("/bookmarks?limit=30", config);
    const bookmarks = data.bookmarks || [];
    if (!bookmarks.length) {
      showEmpty(list, "No bookmarks yet. Add one from the Add tab.");
      return;
    }
    list.innerHTML = "";
    for (const bm of bookmarks.slice(0, 30)) {
      list.appendChild(renderBookmark(bm));
    }
  } catch {
    showEmpty(list, "Cannot connect. Run: bop api-server");
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
  } catch {
    showEmpty(results, "Cannot connect. Run: bop api-server");
  }
}

async function checkConnection() {
  const dot = document.getElementById("statusDot");
  const text = document.getElementById("statusText");
  const count = document.getElementById("totalCount");
  try {
    const config = await getConfig();
    if (!config.apiToken) {
      text.textContent = "No API token";
      return;
    }
    const stats = await apiFetch("/stats", config);
    dot.classList.add("connected");
    text.textContent = "Connected";
    count.textContent = `${stats.total_bookmarks || 0} bookmarks`;
  } catch {
    dot.classList.remove("connected");
    text.textContent = "Disconnected";
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
    titleEl.textContent = "Open an HTTP/HTTPS page to save.";
    titleEl.dataset.url = "";
  }
}

async function saveBookmark() {
  const titleEl = document.getElementById("addPageTitle");
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
    const response = await fetch(`${baseUrl(config)}/bookmarks`, {
      method: "POST",
      headers: authHeaders(config),
      body: JSON.stringify(payload)
    });
    if (response.status === 201) {
      setAddStatus("Saved.", "success");
      loadRecent();
    } else if (response.status === 409) {
      setAddStatus("Already saved.", "success");
    } else if (response.status === 401) {
      setAddStatus("Invalid token. Check Options.", "error");
    } else {
      const body = await response.json().catch(() => ({}));
      setAddStatus(body.error || `Save failed (${response.status}).`, "error");
    }
  } catch {
    setAddStatus("API not reachable. Run: bop api-server", "error");
  }
}

function setAddStatus(message, tone) {
  const el = document.getElementById("addStatus");
  el.textContent = message;
  el.dataset.tone = tone || "info";
}

async function importReadingList() {
  if (!api.readingList || !api.readingList.query) {
    setAddStatus("Reading List API not available in this browser.", "error");
    return;
  }
  try {
    const config = await getConfig();
    if (!config.apiToken) {
      setAddStatus("Set API token in Options first.", "error");
      return;
    }
    const items = await api.readingList.query({});
    if (!items || items.length === 0) {
      setAddStatus("Reading list is empty.", "info");
      return;
    }
    let imported = 0;
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
      } catch { /* skip individual failures */ }
    }
    setAddStatus(`Imported ${imported} of ${items.length} reading list item(s).`, "success");
    if (imported > 0) loadRecent();
  } catch {
    setAddStatus("Could not access reading list.", "error");
  }
}

function switchTab(tabName) {
  for (const btn of document.querySelectorAll(".tab-btn")) {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  }
  for (const content of document.querySelectorAll(".tab-content")) {
    content.classList.toggle("active", content.id === `tab-${tabName}`);
  }
  if (tabName === "add") loadAddTab();
}

document.addEventListener("DOMContentLoaded", () => {
  for (const btn of document.querySelectorAll(".tab-btn")) {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  }

  document.getElementById("searchBtn").addEventListener("click", () => {
    doSearch(document.getElementById("searchInput").value);
  });
  document.getElementById("searchInput").addEventListener("keydown", e => {
    if (e.key === "Enter") doSearch(e.target.value);
  });

  document.getElementById("addSaveBtn").addEventListener("click", saveBookmark);
  document.getElementById("importReadingListBtn").addEventListener("click", importReadingList);

  checkConnection();
  loadRecent();
  loadCategories("categoryList");
});

if (api.tabs && api.tabs.onActivated) {
  api.tabs.onActivated.addListener(() => {
    const addTab = document.getElementById("tab-add");
    if (addTab && addTab.classList.contains("active")) loadAddTab();
  });
}
