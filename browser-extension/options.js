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

function storageSet(values) {
  if (api.storage.local.set.length === 1) {
    return api.storage.local.set(values);
  }
  return new Promise(resolve => api.storage.local.set(values, resolve));
}

function setStatus(message, tone = "info") {
  const status = document.getElementById("status");
  status.textContent = message;
  status.dataset.tone = tone;
}

async function loadOptions() {
  const values = { ...DEFAULTS, ...(await storageGet(DEFAULTS)) };
  document.getElementById("apiPort").value = values.apiPort;
  document.getElementById("apiToken").value = values.apiToken;
  document.getElementById("defaultCategory").value = values.defaultCategory;
}

async function saveOptions() {
  const port = Number.parseInt(document.getElementById("apiPort").value, 10);
  const apiToken = document.getElementById("apiToken").value.trim();
  const defaultCategory = document.getElementById("defaultCategory").value.trim() || DEFAULTS.defaultCategory;

  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    setStatus("Enter a valid TCP port.", "error");
    return;
  }

  await storageSet({ apiPort: port, apiToken, defaultCategory });
  setStatus("Options saved.", "success");
}

document.addEventListener("DOMContentLoaded", () => {
  loadOptions().catch(() => setStatus("Could not load options.", "error"));
  document.getElementById("saveOptions").addEventListener("click", () => {
    saveOptions().catch(() => setStatus("Could not save options.", "error"));
  });
});
