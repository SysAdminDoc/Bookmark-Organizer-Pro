"""Headless extension options tests for pair-before-persist behavior."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "browser-extension"


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is required")
def test_pairing_failures_preserve_the_previous_working_configuration() -> None:
    harness = r"""
const fs = require("fs");
const vm = require("vm");

async function scenario(kind) {
  const prior = { apiPort: 8765, defaultCategory: "Work" };
  const state = { ...prior };
  let token = "old-token";
  let storageFailed = false;
  const fields = {
    apiPort: { value: "9123" },
    apiToken: { value: "new-token" },
    defaultCategory: { value: "Research" },
    status: { textContent: "", dataset: {} },
    saveOptions: { addEventListener() {} },
    testConnection: { addEventListener() {} },
    replacePairing: { addEventListener() {} }
  };
  const chrome = {
    storage: { local: {
      async get(defaults) { return { ...defaults, ...state }; },
      async set(values) {
        if (kind === "storage" && !storageFailed) {
          storageFailed = true;
          throw new Error("quota unavailable");
        }
        Object.assign(state, values);
      }
    } },
    runtime: {
      id: "test-extension",
      lastError: null,
      getURL(path) { return path; },
      async sendMessage(message) {
        if (message.type === "bop:get-config") {
          return { ok: true, config: { ...state, apiToken: token } };
        }
        if (message.type === "bop:set-api-token") {
          token = message.apiToken;
          return { ok: true };
        }
        if (message.type === "bop:clear-api-token") {
          token = "";
          return { ok: true };
        }
        return { ok: false };
      }
    }
  };
  const context = vm.createContext({
    chrome,
    console,
    document: {
      addEventListener() {},
      getElementById(id) { return fields[id]; }
    },
    extensionMessage(_key, _subs, fallback) { return fallback; },
    fetch: async () => {
      if (kind === "network") throw new Error("connection refused");
      const status = kind === "unauthorized" ? 401 : kind === "conflict" ? 409 : 200;
      const body = kind === "conflict"
        ? { replace_required: true }
        : kind === "unauthorized" ? { error: "invalid token" } : { paired: true };
      return { status, async json() { return body; } };
    },
    setTimeout,
    clearTimeout,
    TextEncoder,
    TextDecoder,
    URL,
    Date,
    Math
  });
  context.globalThis = context;
  vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
  vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), context);
  await vm.runInContext("saveOptions()", context);
  return { kind, state, token, status: fields.status.textContent, tone: fields.status.dataset.tone };
}

(async () => {
  const results = [];
  for (const kind of ["success", "unauthorized", "conflict", "network", "storage"]) {
    results.push(await scenario(kind));
  }
  process.stdout.write(JSON.stringify(results));
})().catch(error => { process.stderr.write(String(error.stack || error)); process.exit(1); });
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            harness,
            str(EXTENSION / "shared.js"),
            str(EXTENSION / "options.js"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert completed.returncode == 0, completed.stderr
    results = {item["kind"]: item for item in json.loads(completed.stdout)}
    success = results.pop("success")
    assert success["state"] == {"apiPort": 9123, "defaultCategory": "Research"}
    assert success["token"] == "new-token"
    assert success["tone"] == "success"

    for failure in results.values():
        assert failure["state"] == {"apiPort": 8765, "defaultCategory": "Work"}
        assert failure["token"] == "old-token"
        assert failure["tone"] == "error"
        assert "Previous settings were" in failure["status"]
