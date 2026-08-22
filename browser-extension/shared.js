const DEFAULTS = {
  apiPort: 8765,
  apiToken: "",
  defaultCategory: "Uncategorized / Needs Review"
};
const PENDING_SAVES_KEY = "pendingSaves";
const CLEARED_SAVES_KEY = "lastClearedPendingSaves";

function normalizeDefaultCategory(value) {
  const category = typeof value === "string" ? value.trim() : "";
  return category || DEFAULTS.defaultCategory;
}

function normalizeConfig(config) {
  const values = {
    ...DEFAULTS,
    ...config
  };
  values.defaultCategory = normalizeDefaultCategory(values.defaultCategory);
  return values;
}

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
  return new Promise((resolve, reject) => api.storage.local.set(values, () => {
    const error = api.runtime.lastError;
    if (error) { reject(new Error("Extension settings could not be stored")); return; }
    resolve();
  }));
}

function runtimeMessage(message) {
  if (api.runtime.sendMessage.length === 1) {
    return api.runtime.sendMessage(message);
  }
  return new Promise((resolve, reject) => {
    api.runtime.sendMessage(message, response => {
      const error = api.runtime.lastError;
      if (error) { reject(new Error("Extension service unavailable")); return; }
      resolve(response);
    });
  });
}

function queryTabs(queryInfo) {
  if (api.tabs.query.length === 1) {
    return api.tabs.query(queryInfo);
  }
  return new Promise(resolve => api.tabs.query(queryInfo, resolve));
}

function executeScript(tabId, func, args = []) {
  if (!api.scripting || !api.scripting.executeScript) return Promise.resolve([]);
  const details = { target: { tabId }, func, args };
  if (api.scripting.executeScript.length === 1) {
    return api.scripting.executeScript(details);
  }
  return new Promise((resolve, reject) => {
    api.scripting.executeScript(details, result => {
      const error = api.runtime.lastError;
      if (error) { reject(new Error(error.message)); return; }
      resolve(result);
    });
  });
}

async function getConfig() {
  const response = await runtimeMessage({ type: "bop:get-config" });
  if (!response || !response.ok || !response.config) {
    throw new Error("Extension credential service unavailable");
  }
  return normalizeConfig({ ...DEFAULTS, ...response.config });
}

function baseUrl(config) {
  return `http://127.0.0.1:${config.apiPort}`;
}

function authHeaders(config) {
  return {
    "Authorization": `Bearer ${config.apiToken}`,
    "Content-Type": "application/json"
  };
}

async function pairExtension(config, { replace = false } = {}) {
  const response = await fetch(`${baseUrl(config)}/extension/pair`, {
    method: "POST",
    headers: authHeaders(config),
    body: JSON.stringify({ replace })
  });
  let body = {};
  try { body = await response.json(); } catch { /* response body is optional */ }
  return { status: response.status, body };
}

// A capture replayed against a bookmark the previous attempt already
// persisted comes back 200, not 201: the row was updated, not created.
function isSavedStatus(status) {
  return status === 200 || status === 201;
}

function isRetryableSaveStatus(status) {
  return status === 408 || status === 425 || status === 429 || status >= 500;
}

async function saveBookmarkPayload(payload, config, { source = "unknown", journal = true } = {}) {
  const normalizedPayload = {
    ...payload,
    category: normalizeDefaultCategory(payload.category || config?.defaultCategory)
  };
  const headers = authHeaders(config);
  if (normalizedPayload.browser_snapshot) headers["X-BOP-Capture-Version"] = "1";
  try {
    const response = await fetch(`${baseUrl(config)}/bookmarks`, {
      method: "POST",
      headers,
      body: JSON.stringify(normalizedPayload)
    });
    let body = {};
    try { body = await response.json(); } catch { /* response body is optional */ }
    const queued = journal && isRetryableSaveStatus(response.status);
    if (queued) await enqueuePendingSave(normalizedPayload, `HTTP ${response.status}`, source);
    return { status: response.status, body, queued };
  } catch {
    if (journal) await enqueuePendingSave(normalizedPayload, "API unavailable", source);
    return { status: 0, body: {}, queued: Boolean(journal) };
  }
}

async function capturePageInDocument(options = {}) {
    const limits = {
      per_resource_bytes: 524288,
      total_resource_bytes: 3000000,
      resource_count: 48,
      html_bytes: 4500000,
      fetch_timeout_ms: 4000,
      capture_timeout_ms: 12000
    };
    const captureStartedAt = Date.now();
    const inlineResources = options.inlineResources !== false;
    const diagnostics = {
      count: 0,
      inlined: 0,
      inlined_bytes: 0,
      omitted: 0,
      omitted_by_reason: {},
      limits
    };
    const fetched = new Map();
    let fetchedResources = 0;

    function omit(reason) {
      diagnostics.omitted += 1;
      diagnostics.omitted_by_reason[reason] = (diagnostics.omitted_by_reason[reason] || 0) + 1;
    }

    function bytesToBase64(bytes) {
      let binary = "";
      for (let offset = 0; offset < bytes.length; offset += 32768) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
      }
      return btoa(binary);
    }

    function acceptedMime(kind, mime) {
      if (kind === "css") return mime === "text/css";
      if (kind === "image") {
        return /^image\/(?:png|jpeg|gif|webp|avif|bmp|x-icon|vnd\.microsoft\.icon)$/.test(mime);
      }
      if (kind === "font") {
        return /^(?:font\/(?:woff2?|ttf|otf)|application\/(?:font-woff|font-sfnt|vnd\.ms-fontobject|octet-stream))$/.test(mime);
      }
      return acceptedMime("image", mime) || acceptedMime("font", mime);
    }

    async function fetchResource(rawUrl, kind, baseUrl = location.href) {
      diagnostics.count += 1;
      if (!inlineResources) {
        omit("inlining-disabled");
        return null;
      }
      let url;
      try { url = new URL(rawUrl, baseUrl); } catch {
        omit("invalid-url");
        return null;
      }
      if (!/^https?:$/.test(url.protocol)) {
        omit("unsupported-scheme");
        return null;
      }
      if (url.origin !== location.origin) {
        omit("cross-origin");
        return null;
      }
      const key = `${kind}:${url.href}`;
      if (fetched.has(key)) return fetched.get(key);
      if (fetchedResources >= limits.resource_count) {
        omit("resource-count-limit");
        return null;
      }
      const captureRemaining = limits.capture_timeout_ms - (Date.now() - captureStartedAt);
      if (captureRemaining <= 0) {
        omit("capture-time-limit");
        return null;
      }
      fetchedResources += 1;
      const pending = (async () => {
        const controller = new AbortController();
        const timeout = setTimeout(
          () => controller.abort(),
          Math.min(limits.fetch_timeout_ms, captureRemaining)
        );
        try {
          const response = await fetch(url.href, {
            credentials: "include",
            cache: "force-cache",
            redirect: "follow",
            signal: controller.signal
          });
          if (!response.ok) {
            omit("http-error");
            return null;
          }
          const finalUrl = new URL(response.url || url.href);
          if (finalUrl.origin !== location.origin) {
            omit("cross-origin-redirect");
            return null;
          }
          const mime = String(response.headers.get("content-type") || "")
            .split(";", 1)[0].trim().toLowerCase();
          if (!acceptedMime(kind, mime)) {
            omit("unsupported-type");
            return null;
          }
          const declared = Number(response.headers.get("content-length") || 0);
          if (declared > limits.per_resource_bytes) {
            omit("per-resource-limit");
            return null;
          }
          const chunks = [];
          let size = 0;
          const reader = response.body && response.body.getReader ? response.body.getReader() : null;
          if (!reader) {
            const bytes = new Uint8Array(await response.arrayBuffer());
            chunks.push(bytes);
            size = bytes.byteLength;
          } else {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              size += value.byteLength;
              if (size > limits.per_resource_bytes) {
                await reader.cancel();
                omit("per-resource-limit");
                return null;
              }
              chunks.push(value);
            }
          }
          if (size > limits.per_resource_bytes) {
            omit("per-resource-limit");
            return null;
          }
          if (diagnostics.inlined_bytes + size > limits.total_resource_bytes) {
            omit("total-resource-limit");
            return null;
          }
          const bytes = new Uint8Array(size);
          let offset = 0;
          for (const chunk of chunks) {
            bytes.set(chunk, offset);
            offset += chunk.byteLength;
          }
          diagnostics.inlined += 1;
          diagnostics.inlined_bytes += size;
          if (kind === "css") return { text: new TextDecoder().decode(bytes), url: finalUrl.href };
          return { dataUri: `data:${mime};base64,${bytesToBase64(bytes)}`, url: finalUrl.href };
        } catch (error) {
          omit(error && error.name === "AbortError" ? "fetch-timeout" : "fetch-failed");
          return null;
        } finally {
          clearTimeout(timeout);
        }
      })();
      fetched.set(key, pending);
      return pending;
    }

    async function replaceAsync(value, regex, replacer) {
      const matches = [...value.matchAll(regex)];
      let output = "";
      let cursor = 0;
      for (const match of matches) {
        output += value.slice(cursor, match.index);
        output += await replacer(match);
        cursor = match.index + match[0].length;
      }
      return output + value.slice(cursor);
    }

    async function inlineCss(css, baseUrl, depth = 0) {
      let safeCss = String(css || "")
        .replace(/expression\s*\([^)]*\)/gi, "")
        .replace(/-moz-binding\s*:[^;]+;?/gi, "")
        .replace(/(?:-webkit-)?image-set\([^)]*\)/gi, () => {
          omit("unsupported-css-image-set");
          return "none";
        });
      safeCss = await replaceAsync(
        safeCss,
        /@import\s+(?:url\(\s*)?["']?([^"')\s;]+)["']?\s*\)?[^;]*;/gi,
        async match => {
          if (depth >= 1) {
            omit("css-import-depth");
            return "";
          }
          const resource = await fetchResource(match[1], "css", baseUrl);
          return resource ? await inlineCss(resource.text, resource.url, depth + 1) : "";
        }
      );
      return replaceAsync(
        safeCss,
        /url\(\s*(["']?)(?!data:|#)([^"')]+)\1\s*\)/gi,
        async match => {
          const extension = match[2].split(/[?#]/, 1)[0].toLowerCase();
          const kind = /\.(?:woff2?|ttf|otf|eot)$/.test(extension) ? "font" : "asset";
          const resource = await fetchResource(match[2].trim(), kind, baseUrl);
          return resource ? `url("${resource.dataUri}")` : "none";
        }
      );
    }

    const clone = document.documentElement.cloneNode(true);
    let removedElements = 0;
    let removedAttributes = 0;
    const originalImages = [...document.querySelectorAll("img")];
    const clonedImages = [...clone.querySelectorAll("img")];
    for (let index = 0; index < originalImages.length; index += 1) {
      const source = originalImages[index].currentSrc || originalImages[index].getAttribute("src");
      if (!source || !clonedImages[index]) continue;
      const resource = await fetchResource(source, "image");
      if (resource) clonedImages[index].setAttribute("src", resource.dataUri);
    }
    for (const stylesheet of document.querySelectorAll('link[rel~="stylesheet"][href]')) {
      const resource = await fetchResource(stylesheet.href, "css");
      if (!resource) continue;
      const style = clone.ownerDocument.createElement("style");
      style.textContent = await inlineCss(resource.text, resource.url);
      (clone.querySelector("head") || clone).appendChild(style);
    }
    for (const style of clone.querySelectorAll("style")) {
      style.textContent = await inlineCss(style.textContent, location.href);
    }
    for (const element of clone.querySelectorAll("[style]")) {
      element.setAttribute("style", await inlineCss(element.getAttribute("style"), location.href));
    }
    const blocked = "script,iframe,frame,frameset,object,embed,applet,portal,base,meta,link,form,input,button,select,textarea";
    for (const element of clone.querySelectorAll(blocked)) {
      element.remove();
      removedElements += 1;
    }
    const remoteAttrs = new Set(["src", "srcset", "poster", "background", "action", "formaction", "ping"]);
    for (const element of clone.querySelectorAll("*")) {
      for (const attribute of [...element.attributes]) {
        const name = attribute.name.toLowerCase();
        const value = attribute.value.trim().toLowerCase();
        if (name.startsWith("on") || name === "srcdoc" || name === "nonce" || name === "integrity" || name === "srcset" ||
            (remoteAttrs.has(name) && !value.startsWith("data:")) ||
            (name.endsWith("href") && element.localName !== "a" && !value.startsWith("data:")) ||
            (name === "href" && /^(javascript:|data:|file:|blob:)/.test(value))) {
          element.removeAttribute(attribute.name);
          removedAttributes += 1;
        }
      }
    }
    const selection = String(window.getSelection() || "").slice(0, 500);
    const html = "<!doctype html>\n" + clone.outerHTML;
    const byteLength = new TextEncoder().encode(html).byteLength;
    if (byteLength > limits.html_bytes) {
      return { error: "This page is larger than the 4.5 MB browser capture limit." };
    }
    return {
      html,
      source_url: location.href,
      title: document.title.slice(0, 500),
      selection,
      resources: {
        ...diagnostics,
        removed_elements: removedElements,
        removed_attributes: removedAttributes
      }
    };
}

async function captureSanitizedPage(tabId, options = {}) {
  const frames = await executeScript(tabId, capturePageInDocument, [options]);
  const result = frames && frames[0] ? frames[0].result : null;
  if (!result) throw new Error("The page did not allow browser capture.");
  if (result.error) throw new Error(result.error);
  return result;
}

function isSaveableUrl(url) {
  return /^https?:\/\//i.test(url || "");
}

async function loadCategories(datalistId) {
  try {
    const datalist = document.getElementById(datalistId);
    const resp = await fetch(api.runtime.getURL("categories.json"));
    const categories = await resp.json();
    for (const cat of categories) {
      const opt = document.createElement("option");
      opt.value = cat;
      datalist.appendChild(opt);
    }
  } catch { /* bundled file missing */ }
}

function normalizeTagText(value) {
  const text = String(value ?? "").trim();
  return text.normalize ? text.normalize("NFKC") : text;
}

function tagKey(value) {
  const text = normalizeTagText(value);
  try { return text.toLocaleLowerCase("und"); } catch { return text.toLowerCase(); }
}

function splitTagInput(value) {
  return String(value ?? "").split(/[,\n]/).map(normalizeTagText).filter(Boolean);
}

function uniqueTagValues(values) {
  const source = typeof values === "string" ? splitTagInput(values) : (Array.isArray(values) ? values : [values]);
  const result = [];
  const seen = new Set();
  for (const value of source) {
    const tag = normalizeTagText(value);
    const key = tagKey(tag);
    if (tag && !seen.has(key)) {
      seen.add(key);
      result.push(tag);
    }
  }
  return result;
}

function normalizeTagInput(value) {
  return uniqueTagValues(splitTagInput(value)).join(", ");
}

function tagInputQuery(value) {
  const chunks = String(value ?? "").split(/[,\n]/);
  return normalizeTagText(chunks[chunks.length - 1] || "");
}

function rankTagSuggestions(query, availableTags, selectedTags = [], limit = 8) {
  const selected = new Set(uniqueTagValues(selectedTags).map(tagKey));
  const queryKey = tagKey(query);
  const ranked = [];
  for (const value of uniqueTagValues(availableTags)) {
    const key = tagKey(value);
    if (selected.has(key)) continue;
    let rank = 3;
    if (queryKey) {
      if (key === queryKey) rank = 0;
      else if (key.startsWith(queryKey)) rank = 1;
      else if (key.split(/\s+/).some(token => token.startsWith(queryKey))) rank = 2;
      else if (!key.includes(queryKey)) continue;
    }
    ranked.push({ value, key, rank });
  }
  const safeLimit = Math.max(1, Math.min(50, Number.parseInt(limit, 10) || 8));
  ranked.sort((left, right) => (
    left.rank - right.rank
    || (queryKey ? left.key.length - right.key.length : 0)
    || (left.key < right.key ? -1 : left.key > right.key ? 1 : 0)
    || (left.value < right.value ? -1 : left.value > right.value ? 1 : 0)
  ));
  return ranked.slice(0, safeLimit).map(item => item.value);
}

function replaceCurrentTagInput(value, replacement) {
  const raw = String(value ?? "");
  const match = /^(.*[,\n])[^,\n]*$/.exec(raw);
  return match ? `${match[1]} ${replacement}` : replacement;
}

async function loadTagVocabulary(config) {
  if (!config || !config.apiToken) return [];
  try {
    const response = await fetch(`${baseUrl(config)}/tags`, {
      headers: authHeaders(config)
    });
    if (!response.ok) return [];
    const body = await response.json();
    return uniqueTagValues((body.tags || []).map(item => typeof item === "string" ? item : item.name));
  } catch {
    return [];
  }
}

function attachTagAutocomplete(inputId, availableTags, { listId, statusId } = {}) {
  const input = document.getElementById(inputId);
  const list = document.getElementById(listId);
  const status = document.getElementById(statusId);
  if (!input || !list || !status) return null;

  const state = { availableTags: uniqueTagValues(availableTags), suggestions: [], activeIndex: -1 };
  input.setAttribute("aria-controls", list.id);
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("autocomplete", "off");

  function announce(key, substitutions, fallback) {
    status.textContent = typeof extensionMessage === "function"
      ? extensionMessage(key, substitutions, fallback)
      : fallback;
  }

  function hide() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    state.activeIndex = -1;
  }

  function render({ announceCount = true } = {}) {
    state.suggestions = rankTagSuggestions(
      tagInputQuery(input.value),
      state.availableTags,
      splitTagInput(input.value),
    );
    list.replaceChildren();
    state.suggestions.forEach((value, index) => {
      const option = document.createElement("div");
      option.className = "tag-suggestion-option";
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", String(index === state.activeIndex));
      option.tabIndex = -1;
      option.textContent = value;
      option.addEventListener("mousedown", event => {
        event.preventDefault();
        choose(index);
      });
      list.appendChild(option);
    });
    if (!state.suggestions.length) {
      hide();
      if (announceCount && tagInputQuery(input.value)) {
        announce("tagNoMatches", [], "No matching tags. Press Enter to keep a new tag.");
      }
      return;
    }
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (state.activeIndex >= 0 && state.activeIndex < state.suggestions.length) {
      const selected = list.children[state.activeIndex];
      selected.setAttribute("aria-selected", "true");
      announce(
        "tagSuggestionSelected",
        [state.suggestions[state.activeIndex]],
        `Selected tag ${state.suggestions[state.activeIndex]}.`,
      );
    } else if (announceCount) {
      announce(
        "tagSuggestionsCount",
        [String(state.suggestions.length)],
        `${state.suggestions.length} tag suggestions. Use Arrow Down to choose.`,
      );
    }
  }

  function choose(index) {
    if (index < 0 || index >= state.suggestions.length) return;
    const value = state.suggestions[index];
    input.value = replaceCurrentTagInput(input.value, value);
    hide();
    announce("tagSuggestionChosen", [value], `Tag ${value} selected.`);
    input.focus();
  }

  input.addEventListener("input", () => {
    state.activeIndex = -1;
    render();
  });
  input.addEventListener("focus", () => render());
  input.addEventListener("blur", () => setTimeout(() => {
    if (document.activeElement !== input) hide();
  }, 120));
  input.addEventListener("keydown", event => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!state.suggestions.length) return;
      const direction = event.key === "ArrowDown" ? 1 : -1;
      state.activeIndex = state.activeIndex < 0
        ? (direction > 0 ? 0 : state.suggestions.length - 1)
        : (state.activeIndex + direction + state.suggestions.length) % state.suggestions.length;
      render({ announceCount: false });
      event.preventDefault();
      return;
    }
    if (event.key === "Enter") {
      if (state.activeIndex >= 0) choose(state.activeIndex);
      else {
        input.value = normalizeTagInput(input.value);
        hide();
        announce("tagsReadyToSave", [], "Tags are ready to save.");
      }
      event.preventDefault();
      return;
    }
    if (event.key === "Escape") {
      hide();
      announce("tagSuggestionsDismissed", [], "Tag suggestions dismissed.");
      event.preventDefault();
      return;
    }
    if (event.key === "Tab") {
      if (state.activeIndex >= 0) choose(state.activeIndex);
      else input.value = normalizeTagInput(input.value);
      hide();
      // Do not preventDefault: Tab must continue to the next control.
    }
  });
  render({ announceCount: false });
  return state;
}

async function loadTagsForInput(inputId, config, ids) {
  const vocabulary = await loadTagVocabulary(config);
  return attachTagAutocomplete(inputId, vocabulary, ids);
}

function renderDefaultCategoryAffordance(inputId, defaultId, hintId, category) {
  if (typeof document === "undefined") return;
  const effective = normalizeDefaultCategory(category);
  const input = document.getElementById(inputId);
  const defaultLabel = document.getElementById(defaultId);
  const hint = document.getElementById(hintId);
  if (input) {
    input.dataset.defaultCategory = effective;
    input.setAttribute("placeholder", typeof extensionMessage === "function"
      ? extensionMessage("categoryBlankPlaceholder", [effective], "Use the default category")
      : "Use the default category");
  }
  if (defaultLabel) {
    defaultLabel.textContent = typeof extensionMessage === "function"
      ? extensionMessage("categoryDefaultValue", [effective], `Default: ${effective}`)
      : `Default: ${effective}`;
  }
  if (hint) {
    hint.textContent = typeof extensionMessage === "function"
      ? extensionMessage(
        "categoryBlankHint",
        [effective],
        `Leave blank to use ${effective}. A blank category is never saved.`,
      )
      : `Leave blank to use ${effective}. A blank category is never saved.`;
  }
}

function normalizePendingSave(payload, reason = "API unavailable", source = "context_menu") {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    source,
    reason,
    attempts: 0,
    created_at: new Date().toISOString(),
    payload: {
      url: payload.url,
      title: payload.title || payload.url,
      category: normalizeDefaultCategory(payload.category),
      tags: Array.isArray(payload.tags) ? payload.tags : (payload.tags || []),
      notes: payload.notes || "",
      read_later: Boolean(payload.read_later)
    }
  };
}

async function getPendingSaves() {
  const stored = await storageGet({ [PENDING_SAVES_KEY]: [] });
  return Array.isArray(stored[PENDING_SAVES_KEY]) ? stored[PENDING_SAVES_KEY] : [];
}

async function setPendingSaves(items) {
  await storageSet({ [PENDING_SAVES_KEY]: items.slice(-50) });
}

async function enqueuePendingSave(payload, reason = "API unavailable", source = "context_menu") {
  const pending = await getPendingSaves();
  const normalized = normalizePendingSave(payload, reason, source);
  const duplicate = pending.find(item => item.payload && item.payload.url === normalized.payload.url);
  if (duplicate) {
    duplicate.payload = normalized.payload;
    duplicate.reason = reason;
    duplicate.source = source;
    duplicate.created_at = normalized.created_at;
  } else {
    pending.push(normalized);
  }
  await setPendingSaves(pending);
  return pending.length;
}

async function retryPendingSaves() {
  const config = await getConfig();
  const pending = await getPendingSaves();
  const remaining = [];
  let resolved = 0;
  for (const item of pending) {
    try {
      const result = await saveBookmarkPayload(
        item.payload, config, { source: item.source || "retry", journal: false }
      );
      if (isSavedStatus(result.status) || result.status === 409) {
        resolved += 1;
      } else {
        remaining.push({
          ...item,
          attempts: (item.attempts || 0) + 1,
          reason: result.status ? `HTTP ${result.status}` : "API unavailable"
        });
      }
    } catch {
      remaining.push({ ...item, attempts: (item.attempts || 0) + 1, reason: "API unavailable" });
    }
  }
  await setPendingSaves(remaining);
  return { attempted: pending.length, resolved, remaining: remaining.length };
}

async function getClearedPendingSaves() {
  const stored = await storageGet({ [CLEARED_SAVES_KEY]: null });
  const snapshot = stored[CLEARED_SAVES_KEY];
  return snapshot && Array.isArray(snapshot.items) ? snapshot : null;
}

async function clearPendingSaves({ confirmed = false } = {}) {
  if (!confirmed) throw new Error("Pending-save clear requires confirmation");
  const pending = await getPendingSaves();
  await storageSet({
    [CLEARED_SAVES_KEY]: {
      schema: "bookmark-organizer-pro/pending-saves",
      cleared_at: new Date().toISOString(),
      items: pending
    }
  });
  await setPendingSaves([]);
  return pending.length;
}

async function restoreClearedPendingSaves() {
  const snapshot = await getClearedPendingSaves();
  if (!snapshot) return 0;
  const pending = await getPendingSaves();
  const merged = [...pending];
  for (const item of snapshot.items) {
    const index = merged.findIndex(existing => existing.payload?.url === item.payload?.url);
    if (index >= 0) merged[index] = item;
    else merged.push(item);
  }
  await setPendingSaves(merged);
  await storageSet({ [CLEARED_SAVES_KEY]: null });
  return snapshot.items.length;
}

function renderPendingSaves(container, pending) {
  if (!container) return;
  container.innerHTML = "";
  for (const item of pending) {
    const row = document.createElement("li");
    const title = item.payload?.title || item.payload?.url
      || extensionMessage("untitledSave", [], "Untitled save");
    const when = item.created_at ? new Date(item.created_at).toLocaleString()
      : extensionMessage("unknownTime", [], "Unknown time");
    const source = item.source || extensionMessage("unknownSource", [], "unknown");
    const reason = item.reason || extensionMessage("retryPending", [], "retry pending");
    row.textContent = `${title} · ${source} · ${when} · ${reason}`;
    container.appendChild(row);
  }
}

async function exportPendingSaves() {
  const pending = await getPendingSaves();
  const payload = JSON.stringify({
    schema: "bookmark-organizer-pro/pending-saves",
    exported_at: new Date().toISOString(),
    items: pending
  }, null, 2);
  const url = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = `bookmark-organizer-pro-pending-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
  } finally {
    URL.revokeObjectURL(url);
  }
  return pending.length;
}
