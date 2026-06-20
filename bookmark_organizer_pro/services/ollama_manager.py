"""Ollama lifecycle management — detect, install, start, pull models.

Provides a single OllamaManager class that the AI settings dialog uses
to give users full control over local AI without touching a terminal.
"""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from bookmark_organizer_pro.logging_config import log


OLLAMA_DEFAULT_URL = "http://localhost:11434"

POPULAR_MODELS = [
    ("qwen3.5", "4.8 GB", "⭐ RECOMMENDED — Best overall quality. Smart, fast, great at tagging and categorizing."),
    ("phi4", "9.1 GB", "⭐ RECOMMENDED — Excellent reasoning. Best if you have 16+ GB RAM."),
    ("qwen3", "4.7 GB", "Great quality, strong with multiple languages."),
    ("gemma3", "3.3 GB", "Good and lightweight. Works well on most computers."),
    ("llama3.2", "2.0 GB", "Smallest download, runs on anything. OK quality for basic tasks."),
    ("mistral", "4.1 GB", "Solid all-rounder. Good speed, decent quality."),
    ("deepseek-r1:8b", "4.9 GB", "Thinks step-by-step. Good for complex analysis."),
    ("deepseek-r1", "4.7 GB", "Smaller reasoning model. Fast on modest hardware."),
    ("codellama", "3.8 GB", "Specialized for code. Best for developer bookmarks."),
    ("llava", "4.7 GB", "Can understand images. Unique but niche."),
    ("mixtral", "26 GB", "Very capable but large. Needs 32+ GB RAM."),
    ("command-r", "20 GB", "Optimized for search/RAG. Needs 24+ GB RAM."),
]


@dataclass
class OllamaStatus:
    installed: bool = False
    binary_path: str = ""
    running: bool = False
    version: str = ""
    models: List[Dict] = None

    def __post_init__(self):
        if self.models is None:
            self.models = []


class OllamaManager:
    """Detect, install, start, and manage Ollama and its models."""

    def __init__(self, base_url: str = OLLAMA_DEFAULT_URL):
        self.base_url = base_url.rstrip("/")

    # ── Detection ──────────────────────────────────────────────────────

    def detect(self) -> OllamaStatus:
        """Check if Ollama is installed and running. Returns full status."""
        status = OllamaStatus()

        binary = shutil.which("ollama")
        if binary:
            status.installed = True
            status.binary_path = binary
            try:
                result = subprocess.run(
                    [binary, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                version_text = result.stdout.strip() or result.stderr.strip()
                if version_text:
                    status.version = version_text.split()[-1] if version_text.split() else version_text
            except Exception:
                status.version = "unknown"
        else:
            for candidate in self._platform_binary_paths():
                if candidate.exists():
                    status.installed = True
                    status.binary_path = str(candidate)
                    break

        if status.installed:
            running, models = self._check_server()
            status.running = running
            status.models = models

        return status

    def _platform_binary_paths(self) -> List[Path]:
        """Platform-specific paths where Ollama might be installed."""
        paths = []
        if platform.system() == "Windows":
            local = os.environ.get("LOCALAPPDATA", "")
            if local:
                paths.append(Path(local) / "Programs" / "Ollama" / "ollama.exe")
            paths.append(Path("C:/Program Files/Ollama/ollama.exe"))
            paths.append(Path("C:/Program Files (x86)/Ollama/ollama.exe"))
        elif platform.system() == "Darwin":
            paths.append(Path("/usr/local/bin/ollama"))
            paths.append(Path("/opt/homebrew/bin/ollama"))
        else:
            paths.append(Path("/usr/local/bin/ollama"))
            paths.append(Path("/usr/bin/ollama"))
            paths.append(Path.home() / ".local" / "bin" / "ollama")
        return paths

    def _check_server(self) -> Tuple[bool, List[Dict]]:
        """Ping the Ollama API and list models if running."""
        try:
            requests = importlib.import_module("requests")
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                models = []
                for m in data.get("models", []):
                    name = m.get("name", "")
                    size_bytes = m.get("size", 0)
                    size_gb = f"{size_bytes / 1e9:.1f} GB" if size_bytes else ""
                    models.append({
                        "name": name,
                        "size": size_gb,
                        "modified": m.get("modified_at", ""),
                        "family": m.get("details", {}).get("family", ""),
                        "parameters": m.get("details", {}).get("parameter_size", ""),
                    })
                return True, models
            return False, []
        except Exception:
            return False, []

    # ── Installation ───────────────────────────────────────────────────

    def install(self, on_progress: Optional[Callable[[str], None]] = None,
                on_done: Optional[Callable[[bool, str], None]] = None):
        """Install Ollama. Runs in a background thread."""
        def _worker():
            try:
                system = platform.system()
                if system == "Windows":
                    ok, msg = self._install_windows(on_progress)
                elif system == "Darwin":
                    ok, msg = self._install_mac(on_progress)
                else:
                    ok, msg = self._install_linux(on_progress)
                if on_done:
                    on_done(ok, msg)
            except Exception as exc:
                log.error(f"Ollama install failed: {exc}")
                if on_done:
                    on_done(False, str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def _install_windows(self, progress) -> Tuple[bool, str]:
        """Install Ollama via winget or direct download."""
        if progress:
            progress("Checking winget…")
        if shutil.which("winget"):
            if progress:
                progress("Installing via winget…")
            try:
                subprocess.run(
                    ["winget", "install", "--id", "Ollama.Ollama",
                     "--accept-source-agreements", "--accept-package-agreements"],
                    check=True, timeout=300,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                return True, "Ollama installed via winget"
            except subprocess.CalledProcessError as e:
                return False, f"winget install failed: {e}"

        if progress:
            progress("Downloading Ollama installer…")
        try:
            requests = importlib.import_module("requests")
            url = "https://ollama.com/download/OllamaSetup.exe"
            installer = Path(os.environ.get("TEMP", ".")) / "OllamaSetup.exe"
            resp = requests.get(url, timeout=120, stream=True)
            resp.raise_for_status()
            with open(installer, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            if progress:
                progress("Running installer…")
            subprocess.run([str(installer), "/VERYSILENT", "/NORESTART"],
                           check=True, timeout=120)
            return True, "Ollama installed from ollama.com"
        except Exception as exc:
            return False, f"Download install failed: {exc}"

    def _install_mac(self, progress) -> Tuple[bool, str]:
        if shutil.which("brew"):
            if progress:
                progress("Installing via Homebrew…")
            try:
                subprocess.run(["brew", "install", "ollama"],
                               check=True, timeout=300,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return True, "Ollama installed via Homebrew"
            except subprocess.CalledProcessError as e:
                return False, f"brew install failed: {e}"
        return False, "Install Homebrew first, or download Ollama from ollama.com/download"

    def _install_linux(self, progress) -> Tuple[bool, str]:
        if progress:
            progress("Running Ollama install script…")
        try:
            subprocess.run(
                ["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
                check=True, timeout=300,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            return True, "Ollama installed via install script"
        except subprocess.CalledProcessError as e:
            return False, f"Install script failed: {e}"

    # ── Server control ─────────────────────────────────────────────────

    def start_server(self, on_done: Optional[Callable[[bool, str], None]] = None):
        """Start the Ollama server in the background."""
        def _worker():
            try:
                binary = shutil.which("ollama")
                if not binary:
                    status = self.detect()
                    binary = status.binary_path
                if not binary:
                    if on_done:
                        on_done(False, "Ollama binary not found")
                    return

                if platform.system() == "Windows":
                    subprocess.Popen(
                        [binary, "serve"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                    )
                else:
                    subprocess.Popen(
                        [binary, "serve"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )

                import time
                for _ in range(15):
                    time.sleep(1)
                    running, _ = self._check_server()
                    if running:
                        if on_done:
                            on_done(True, "Ollama server started")
                        return

                if on_done:
                    on_done(False, "Server started but not responding after 15s")
            except Exception as exc:
                log.error(f"Ollama start failed: {exc}")
                if on_done:
                    on_done(False, str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Model management ───────────────────────────────────────────────

    def pull_model(self, model_name: str,
                   on_progress: Optional[Callable[[str], None]] = None,
                   on_done: Optional[Callable[[bool, str], None]] = None):
        """Download a model. Runs in background thread with progress callbacks."""
        def _worker():
            try:
                requests = importlib.import_module("requests")
                if on_progress:
                    on_progress(f"Pulling {model_name}…")

                resp = requests.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model_name, "stream": True},
                    timeout=3600, stream=True,
                )
                resp.raise_for_status()

                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        import json
                        data = json.loads(line)
                        status_text = data.get("status", "")
                        total = data.get("total", 0)
                        completed = data.get("completed", 0)
                        if total and completed and on_progress:
                            pct = int(completed / total * 100)
                            on_progress(f"{status_text} — {pct}%")
                        elif status_text and on_progress:
                            on_progress(status_text)
                    except Exception:
                        pass

                if on_done:
                    on_done(True, f"{model_name} downloaded successfully")
            except Exception as exc:
                log.error(f"Model pull failed: {exc}")
                if on_done:
                    on_done(False, str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def delete_model(self, model_name: str) -> Tuple[bool, str]:
        """Delete a downloaded model."""
        try:
            requests = importlib.import_module("requests")
            resp = requests.delete(
                f"{self.base_url}/api/delete",
                json={"name": model_name},
                timeout=30,
            )
            if resp.status_code == 200:
                return True, f"{model_name} deleted"
            return False, f"HTTP {resp.status_code}"
        except Exception as exc:
            return False, str(exc)

    def list_local_models(self) -> List[Dict]:
        """List currently downloaded models."""
        _, models = self._check_server()
        return models

    @staticmethod
    def get_popular_models() -> List[Tuple[str, str, str]]:
        """Return list of popular models with (name, size, description)."""
        return POPULAR_MODELS
