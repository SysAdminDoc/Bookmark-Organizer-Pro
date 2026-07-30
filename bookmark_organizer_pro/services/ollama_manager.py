"""Ollama lifecycle management — detect, install, start, pull models.

Provides a single OllamaManager class that the AI settings dialog uses
to give users full control over local AI without touching a terminal.
"""

from __future__ import annotations

import importlib
import hashlib
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit

from bookmark_organizer_pro.logging_config import log


OLLAMA_DEFAULT_URL = "http://localhost:11434"
OLLAMA_INSTALL_VERSION = "0.32.5"
OLLAMA_RELEASE_BASE = (
    "https://github.com/ollama/ollama/releases/download/"
    f"v{OLLAMA_INSTALL_VERSION}"
)
OLLAMA_INSTALL_REDIRECT_HOSTS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)
OLLAMA_INSTALL_MAX_REDIRECTS = 5

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


@dataclass(frozen=True)
class OllamaInstallAsset:
    """Pinned third-party artifact allowed by the installer workflow."""

    name: str
    url: str
    sha256: str
    max_bytes: int


OLLAMA_WINDOWS_INSTALLER = OllamaInstallAsset(
    name="OllamaSetup.exe",
    url=f"{OLLAMA_RELEASE_BASE}/OllamaSetup.exe",
    sha256="b7eeef038ddcbd09ac665b11872baff1bc9b42794be41b5ef187b2f4b16a4498",
    max_bytes=1_650_000_000,
)
OLLAMA_MAC_INSTALLER = OllamaInstallAsset(
    name="Ollama.dmg",
    url=f"{OLLAMA_RELEASE_BASE}/Ollama.dmg",
    sha256="76c68f717f9d195481effe68fd7a93f1bb16142943c74d4b6040e400d3f186e9",
    max_bytes=200_000_000,
)
OLLAMA_LINUX_AMD64 = OllamaInstallAsset(
    name="ollama-linux-amd64.tar.zst",
    url=f"{OLLAMA_RELEASE_BASE}/ollama-linux-amd64.tar.zst",
    sha256="f7d6bdbcf71b83aa8670c4e7dc4b6936c0952fcf8b114eaf6a11cbadb9684214",
    max_bytes=1_500_000_000,
)
OLLAMA_LINUX_ARM64 = OllamaInstallAsset(
    name="ollama-linux-arm64.tar.zst",
    url=f"{OLLAMA_RELEASE_BASE}/ollama-linux-arm64.tar.zst",
    sha256="aa7e06b5683ee66c4a3ec68ea7236db43b5a5d0821f0dfe2c5a215f4462bddf4",
    max_bytes=1_650_000_000,
)


class OllamaInstallCancelled(RuntimeError):
    """Raised when the user cancels a download or installer process."""


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

    def install(
        self,
        on_progress: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
        *,
        confirmed: bool = False,
        cancel_event: Optional[threading.Event] = None,
    ) -> threading.Event:
        """Install Ollama after explicit confirmation, in a background thread."""
        cancellation = cancel_event or threading.Event()
        if not confirmed:
            if on_done:
                on_done(False, "Ollama installation requires explicit confirmation.")
            return cancellation

        def _worker():
            try:
                system = platform.system()
                if system == "Windows":
                    ok, msg = self._install_windows(on_progress, cancellation)
                elif system == "Darwin":
                    ok, msg = self._install_mac(on_progress, cancellation)
                else:
                    ok, msg = self._install_linux(on_progress, cancellation)
                if on_done:
                    on_done(ok, msg)
            except Exception as exc:
                log.error(f"Ollama install failed: {exc}")
                if on_done:
                    on_done(False, str(exc))

        threading.Thread(target=_worker, daemon=True).start()
        return cancellation

    @staticmethod
    def _validate_install_url(url: str) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or (parsed.hostname or "").lower() not in OLLAMA_INSTALL_REDIRECT_HOSTS
        ):
            raise ValueError("Ollama download redirected outside the approved HTTPS sources")

    def _download_verified_asset(
        self,
        asset: OllamaInstallAsset,
        destination: Path,
        cancel_event: threading.Event,
        progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Download one allowlisted release asset and atomically verify its digest."""
        requests = importlib.import_module("requests")
        current_url = asset.url
        response = None

        for redirect_count in range(OLLAMA_INSTALL_MAX_REDIRECTS + 1):
            self._validate_install_url(current_url)
            response = requests.get(
                current_url,
                timeout=(10, 120),
                stream=True,
                allow_redirects=False,
                headers={"User-Agent": "Bookmark-Organizer-Pro/OllamaInstaller"},
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location", "")
                response.close()
                if not location or redirect_count >= OLLAMA_INSTALL_MAX_REDIRECTS:
                    raise ValueError("Ollama download exceeded the redirect limit")
                current_url = urljoin(current_url, location)
                continue
            break
        else:  # pragma: no cover - loop bound is defensive
            raise ValueError("Ollama download exceeded the redirect limit")

        if response is None:  # pragma: no cover - defensive
            raise RuntimeError("Ollama download did not return a response")

        part_path = destination.with_name(f"{destination.name}.part")
        try:
            response.raise_for_status()
            self._validate_install_url(getattr(response, "url", current_url))
            declared_size = response.headers.get("Content-Length")
            if declared_size:
                try:
                    if int(declared_size) > asset.max_bytes:
                        raise ValueError("Ollama download exceeds the configured byte limit")
                except ValueError as exc:
                    if "exceeds" in str(exc):
                        raise
                    raise ValueError("Ollama download returned an invalid Content-Length") from exc

            digest = hashlib.sha256()
            downloaded = 0
            next_progress = 64 * 1024 * 1024
            destination.parent.mkdir(parents=True, exist_ok=True)
            with part_path.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if cancel_event.is_set():
                        raise OllamaInstallCancelled("Ollama installation cancelled")
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > asset.max_bytes:
                        raise ValueError("Ollama download exceeds the configured byte limit")
                    digest.update(chunk)
                    handle.write(chunk)
                    if progress and downloaded >= next_progress:
                        progress(
                            f"Downloading verified Ollama {OLLAMA_INSTALL_VERSION}"
                            f" — {downloaded / (1024 ** 2):.0f} MiB"
                        )
                        next_progress += 64 * 1024 * 1024

            if cancel_event.is_set():
                raise OllamaInstallCancelled("Ollama installation cancelled")
            actual_digest = digest.hexdigest()
            if actual_digest != asset.sha256:
                raise ValueError(
                    "Ollama installer SHA-256 mismatch; the download was discarded"
                )
            os.replace(part_path, destination)
        finally:
            response.close()
            part_path.unlink(missing_ok=True)

    @staticmethod
    def _run_windows_installer(
        installer: Path,
        cancel_event: threading.Event,
    ) -> None:
        if cancel_event.is_set():
            raise OllamaInstallCancelled("Ollama installation cancelled")
        process = subprocess.Popen([str(installer), "/VERYSILENT", "/NORESTART"])
        deadline = time.monotonic() + 300
        while process.poll() is None:
            if cancel_event.wait(0.2):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                raise OllamaInstallCancelled("Ollama installation cancelled")
            if time.monotonic() >= deadline:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                raise TimeoutError("Ollama installer exceeded the five-minute limit")
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, process.args)

    def _install_windows(
        self,
        progress: Optional[Callable[[str], None]],
        cancel_event: threading.Event,
    ) -> Tuple[bool, str]:
        """Install one pinned Windows release after digest verification."""
        if platform.machine().lower() not in {"amd64", "x86_64"}:
            return (
                False,
                f"Manual install required for Ollama {OLLAMA_INSTALL_VERSION}: "
                "the verified automatic installer supports Windows x64 only. "
                f"Choose the matching asset at {OLLAMA_RELEASE_BASE} and verify "
                "it against that release's sha256sum.txt before opening it.",
            )
        if progress:
            progress(f"Downloading verified Ollama {OLLAMA_INSTALL_VERSION} installer…")
        work_dir = Path(tempfile.mkdtemp(prefix="bop-ollama-install-"))
        installer = work_dir / OLLAMA_WINDOWS_INSTALLER.name
        try:
            self._download_verified_asset(
                OLLAMA_WINDOWS_INSTALLER,
                installer,
                cancel_event,
                progress,
            )
            if progress:
                progress(
                    f"SHA-256 verified; running Ollama {OLLAMA_INSTALL_VERSION} installer…"
                )
            self._run_windows_installer(installer, cancel_event)
            return True, f"Ollama {OLLAMA_INSTALL_VERSION} installed from GitHub Releases"
        except OllamaInstallCancelled:
            return False, "Ollama installation cancelled"
        except Exception as exc:
            return False, f"Verified install failed: {exc}"
        finally:
            shutil.rmtree(work_dir)

    def _install_mac(
        self,
        progress: Optional[Callable[[str], None]],
        cancel_event: threading.Event,
    ) -> Tuple[bool, str]:
        del progress, cancel_event
        return False, self.manual_install_instructions("Darwin")

    def _install_linux(
        self,
        progress: Optional[Callable[[str], None]],
        cancel_event: threading.Event,
    ) -> Tuple[bool, str]:
        del progress, cancel_event
        return False, self.manual_install_instructions("Linux")

    @staticmethod
    def manual_install_instructions(system: Optional[str] = None) -> str:
        """Return pinned, verify-before-open instructions for non-Windows hosts."""
        target = system or platform.system()
        if target == "Darwin":
            asset = OLLAMA_MAC_INSTALLER
            return (
                f"Manual install required for Ollama {OLLAMA_INSTALL_VERSION}.\n\n"
                f"curl --fail --location --proto '=https' --tlsv1.2 "
                f"--output {asset.name} {asset.url}\n"
                f"echo '{asset.sha256}  {asset.name}' > ollama.sha256\n"
                "shasum -a 256 --check ollama.sha256\n"
                f"open {asset.name}\n\n"
                "Only open the disk image after the checksum reports OK."
            )

        machine = platform.machine().lower()
        if machine in {"aarch64", "arm64"}:
            asset = OLLAMA_LINUX_ARM64
        elif machine in {"amd64", "x86_64"}:
            asset = OLLAMA_LINUX_AMD64
        else:
            return (
                f"Manual install required for Ollama {OLLAMA_INSTALL_VERSION}: "
                f"architecture {machine or 'unknown'} is not in the pinned asset manifest. "
                f"Choose the matching asset at {OLLAMA_RELEASE_BASE} and verify it "
                "against that release's sha256sum.txt before installing."
            )
        return (
            f"Manual install required for Ollama {OLLAMA_INSTALL_VERSION}.\n\n"
            f"curl --fail --location --proto '=https' --tlsv1.2 "
            f"--output {asset.name} {asset.url}\n"
            f"echo '{asset.sha256}  {asset.name}' > ollama.sha256\n"
            "sha256sum --check ollama.sha256\n"
            f"sudo tar --zstd -xf {asset.name} -C /usr/local\n\n"
            "Extract only after the checksum reports OK; no remote script is piped to a shell."
        )

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
