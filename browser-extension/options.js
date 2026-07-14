/* global DEFAULTS, storageGet, storageSet, runtimeMessage, pairExtension */

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

async function currentConfig() {
  const stored = { ...DEFAULTS, ...(await storageGet(DEFAULTS)) };
  const response = await runtimeMessage({ type: "bop:get-config" });
  if (!response || !response.ok || !response.config) {
    throw new Error("Current credentials could not be read");
  }
  return { ...stored, ...response.config };
}

async function writeApiToken(apiToken) {
  const response = await runtimeMessage({ type: "bop:set-api-token", apiToken });
  if (!response || !response.ok) throw new Error("Credential operation failed");
}

async function restoreApiToken(apiToken) {
  const message = apiToken
    ? { type: "bop:set-api-token", apiToken }
    : { type: "bop:clear-api-token" };
  const response = await runtimeMessage(message);
  if (!response || !response.ok) throw new Error("Credential rollback failed");
}

async function persistPairedConfig(candidate, previous) {
  let tokenChanged = false;
  try {
    await writeApiToken(candidate.apiToken);
    tokenChanged = true;
    const { apiPort: port, defaultCategory } = candidate;
    await storageSet({ apiPort: port, defaultCategory });
  } catch (error) {
    const rollbacks = [
      storageSet({
        apiPort: previous.apiPort,
        defaultCategory: previous.defaultCategory
      })
    ];
    if (tokenChanged) rollbacks.push(restoreApiToken(previous.apiToken));
    const outcomes = await Promise.allSettled(rollbacks);
    if (outcomes.some(outcome => outcome.status === "rejected")) {
      throw new Error("Settings could not be stored or restored");
    }
    throw error;
  }
}

async function saveOptions({ replacePairing = false } = {}) {
  const port = Number.parseInt(document.getElementById("apiPort").value, 10);
  const apiToken = document.getElementById("apiToken").value.trim();
  const defaultCategory = document.getElementById("defaultCategory").value.trim() || DEFAULTS.defaultCategory;

  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    setStatus(extensionMessage("validPortRequired", [], "Enter a valid TCP port."), "error");
    return;
  }

  if (!apiToken) {
    setStatus(extensionMessage("tokenRequired", [], "Enter the local API token before saving."), "error");
    return;
  }

  let previous;
  try {
    previous = await currentConfig();
  } catch {
    setStatus("Could not read the current settings. Nothing was changed.", "error");
    return;
  }

  const candidate = { apiPort: port, apiToken, defaultCategory };
  let pairing;
  try {
    pairing = await pairExtension(candidate, { replace: replacePairing });
  } catch {
    setStatus("Cannot reach the local API. Start the app and try again. Previous settings were kept.", "error");
    return;
  }

  if (pairing.status === 409 && pairing.body.replace_required) {
    setStatus("This API is paired with another extension ID. Use Replace Pairing to recover this install. Previous settings were kept.", "error");
    return;
  }
  if (pairing.status === 401) {
    setStatus("Server reached but token is invalid. Previous settings were kept.", "error");
    return;
  }
  if (pairing.status !== 200 || !pairing.body.paired) {
    setStatus(`${pairing.body.error || `Pairing failed: HTTP ${pairing.status}`} Previous settings were kept.`, "error");
    return;
  }

  try {
    await persistPairedConfig(candidate, previous);
  } catch (error) {
    const restored = error && error.message !== "Settings could not be stored or restored";
    setStatus(restored
      ? "Pairing succeeded, but settings could not be stored. Previous settings were restored."
      : "Pairing succeeded, but settings could not be stored or restored. Reopen Options before saving bookmarks.", "error");
    return;
  }
  setStatus(replacePairing
    ? extensionMessage("pairingReplaced", [], "Settings saved and pairing replaced.")
    : extensionMessage("settingsSavedPaired", [], "Settings saved and extension paired."), "success");
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

  setStatus(extensionMessage("testingConnection", [], "Testing connection..."));
  const button = document.getElementById("testConnection");
  button.disabled = true;
  button.textContent = extensionMessage("testing", [], "Testing...");

  try {
    const response = await fetch(`http://127.0.0.1:${port}/extension/pair`, {
      headers: token ? { "Authorization": `Bearer ${token}` } : {}
    });
    const body = await response.json().catch(() => ({}));
    if (response.ok && body.paired) {
      setStatus(extensionMessage("connectedPaired", [], "Connected and paired with this extension."), "success");
    } else if (response.ok) {
      setStatus(extensionMessage("connectedUnpaired", [], "Connected, but this extension is not paired. Save Settings to pair it."), "error");
    } else if (response.status === 401) {
      setStatus(extensionMessage("serverInvalidToken", [], "Server reached but token is invalid."), "error");
    } else {
      setStatus(`Unexpected response: ${response.status}`, "error");
    }
  } catch {
    setStatus(extensionMessage("apiUnavailable", [], "Cannot reach the local API. Start the app or run: bop api-server"), "error");
  } finally {
    button.disabled = false;
    button.textContent = extensionMessage("testApi", [], "Test API");
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
  document.getElementById("replacePairing").addEventListener("click", () => {
    saveOptions({ replacePairing: true }).catch(() => setStatus("Could not replace pairing.", "error"));
  });
});
