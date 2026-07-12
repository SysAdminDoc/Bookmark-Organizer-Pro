/* global DEFAULTS, storageGet, storageSet, runtimeMessage */

function setStatus(message, tone = "info") {
  const status = document.getElementById("status");
  status.textContent = message;
  status.dataset.tone = tone;
}

async function loadOptions() {
  const stored = { ...DEFAULTS, ...(await storageGet(DEFAULTS)) };
  const response = await runtimeMessage({ type: "bop:get-config" });
  const values = response && response.ok ? { ...stored, ...response.config } : stored;
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

  if (!apiToken) {
    setStatus("Enter the local API token before saving.", "error");
    return;
  }

  await storageSet({ apiPort: port, defaultCategory });
  const response = await runtimeMessage({ type: "bop:set-api-token", apiToken });
  if (!response || !response.ok) throw new Error("Credential operation failed");
  setStatus("Settings saved.", "success");
}

async function testConnection() {
  const port = Number.parseInt(document.getElementById("apiPort").value, 10);
  const token = document.getElementById("apiToken").value.trim();

  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    setStatus("Enter a valid TCP port first.", "error");
    return;
  }
  if (!token) {
    setStatus("Enter the local API token before testing.", "error");
    return;
  }

  setStatus("Testing connection...");
  const button = document.getElementById("testConnection");
  button.disabled = true;
  button.textContent = "Testing...";

  try {
    const response = await fetch(`http://127.0.0.1:${port}/`, {
      headers: token ? { "Authorization": `Bearer ${token}` } : {}
    });
    const body = await response.json().catch(() => ({}));
    if (response.ok && body.name) {
      setStatus(`Connected to ${body.name} v${body.version}.`, "success");
    } else if (response.status === 401) {
      setStatus("Server reached but token is invalid.", "error");
    } else {
      setStatus(`Unexpected response: ${response.status}`, "error");
    }
  } catch {
    setStatus("Cannot reach the local API. Start the app or run: bop api-server", "error");
  } finally {
    button.disabled = false;
    button.textContent = "Test API";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadOptions().catch(() => setStatus("Could not load options.", "error"));
  document.getElementById("saveOptions").addEventListener("click", () => {
    saveOptions().catch(() => setStatus("Could not save options.", "error"));
  });
  document.getElementById("testConnection").addEventListener("click", () => {
    testConnection().catch(() => setStatus("Connection test failed.", "error"));
  });
});
