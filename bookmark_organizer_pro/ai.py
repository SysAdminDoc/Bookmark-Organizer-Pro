"""AI provider configuration and client implementations.

Supports OpenAI, Anthropic Claude, Google Gemini, Groq, and Ollama (local).
"""

import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .constants import AI_CONFIG_FILE
from .logging_config import log

# Per-request network timeout (seconds) applied to every remote provider so a
# hung connection can never block an AI worker thread indefinitely.
REQUEST_TIMEOUT = 60

# Transient-error hints used to decide whether a failed request is worth
# retrying with backoff (rate limits, gateway/5xx errors, timeouts, etc.).
_RETRYABLE_HINTS = (
    "timeout", "timed out", "rate limit", "ratelimit", "429", "500", "502",
    "503", "504", "overloaded", "temporarily", "unavailable", "connection",
    "reset by peer", "try again",
)

# Hints that a request failed because the selected model is gone/renamed, so we
# can point the user at AI settings instead of showing a raw stack trace.
_MODEL_ERROR_HINTS = (
    "model", "not found", "does not exist", "no such", "404",
    "decommission", "deprecated", "unsupported", "invalid model",
)


def _is_retryable(exc: Exception) -> bool:
    """Heuristically decide whether a provider error is worth retrying."""
    msg = str(exc).lower()
    return any(hint in msg for hint in _RETRYABLE_HINTS)


def _retry(fn: Callable, *, attempts: int = 3, base_delay: float = 1.0, label: str = "") -> Any:
    """Call ``fn`` with exponential backoff on transient provider failures.

    Non-transient errors (bad request, auth, unknown model) are raised
    immediately so the user sees the real problem without waiting on retries.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - re-raised below
            last_exc = exc
            if attempt == attempts - 1 or not _is_retryable(exc):
                raise
            delay = base_delay * (2 ** attempt)
            log.info(
                f"Retrying {label or 'AI request'} after transient error "
                f"({attempt + 1}/{attempts}): {str(exc)[:120]} — waiting {delay:.1f}s"
            )
            time.sleep(delay)
    if last_exc:  # pragma: no cover - defensive
        raise last_exc


def _friendly_model_error(exc: Exception, provider_label: str, model: str) -> str:
    """Turn a raw provider exception into actionable guidance for the user."""
    msg = str(exc)
    if any(hint in msg.lower() for hint in _MODEL_ERROR_HINTS):
        return (
            f"{provider_label} could not use model '{model}'. It may have been "
            f"renamed or retired — open AI settings and pick a current model. "
            f"({msg[:160]})"
        )
    return f"Error: {msg[:200]}"


def ensure_package(package: str, import_name: str = None):
    """Import a package, raising a clear install instruction if missing."""
    import_name = import_name or package
    try:
        return importlib.import_module(import_name)
    except ImportError:
        raise ImportError(
            f"Required package '{package}' is not installed.\n"
            f"Install it with: pip install {package}"
        )


@dataclass
class AIProviderInfo:
    """Information about an AI provider"""
    name: str
    display_name: str
    api_key_url: str
    api_key_env: str
    models: List[str]
    default_model: str
    description: str
    requires_api_key: bool = True
    free_tier: bool = False
    local: bool = False


AI_PROVIDERS = {
    "openai": AIProviderInfo(
        name="openai",
        display_name="OpenAI",
        api_key_url="https://platform.openai.com/api-keys",
        api_key_env="OPENAI_API_KEY",
        models=["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini", "gpt-3.5-turbo"],
        default_model="gpt-4o-mini",
        description="GPT models - reliable and fast"
    ),
    "anthropic": AIProviderInfo(
        name="anthropic",
        display_name="Anthropic Claude",
        api_key_url="https://console.anthropic.com/settings/keys",
        api_key_env="ANTHROPIC_API_KEY",
        models=["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022", "claude-3-haiku-20240307"],
        default_model="claude-sonnet-4-20250514",
        description="Claude models - excellent reasoning"
    ),
    "google": AIProviderInfo(
        name="google",
        display_name="Google Gemini",
        api_key_url="https://aistudio.google.com/app/apikey",
        api_key_env="GOOGLE_API_KEY",
        models=["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash",
                "gemini-2.5-pro", "gemini-1.5-flash"],
        default_model="gemini-2.0-flash",
        description="Free tier available, fast",
        free_tier=True
    ),
    "groq": AIProviderInfo(
        name="groq",
        display_name="Groq",
        api_key_url="https://console.groq.com/keys",
        api_key_env="GROQ_API_KEY",
        models=["llama-3.3-70b-versatile", "llama3-70b-8192", "llama3-8b-8192",
                "gemma2-9b-it", "mixtral-8x7b-32768"],
        default_model="llama-3.3-70b-versatile",
        description="Ultra-fast inference, free tier",
        free_tier=True
    ),
    "deepseek": AIProviderInfo(
        name="deepseek",
        display_name="DeepSeek",
        api_key_url="https://platform.deepseek.com/api_keys",
        api_key_env="DEEPSEEK_API_KEY",
        models=["deepseek-chat", "deepseek-reasoner"],
        default_model="deepseek-chat",
        description="DeepSeek V3/R1 — powerful and affordable",
        free_tier=False,
    ),
    "ollama": AIProviderInfo(
        name="ollama",
        display_name="Ollama (Local)",
        api_key_url="https://ollama.com/download",
        api_key_env="",
        models=["qwen3.5", "phi4", "qwen3", "gemma3", "llama3.2",
                "mistral", "deepseek-r1:8b", "deepseek-r1",
                "codellama", "command-r", "mixtral", "llava"],
        default_model="qwen3.5",
        description="Run models locally via Ollama — completely free, no API key needed",
        requires_api_key=False,
        free_tier=True,
        local=True
    ),
}


class AIConfigManager:
    """Manages AI provider configuration."""

    def __init__(self, filepath: Path = AI_CONFIG_FILE):
        self.filepath = filepath
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self):
        """Load configuration from file"""
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                if not isinstance(self._config, dict):
                    log.warning("AI config is not an object; using defaults")
                    self._config = {}
            except Exception as e:
                log.warning(f"Could not load AI config: {e}")
                self._config = {}

        self._config.setdefault("provider", "google")
        self._config.setdefault("model", "gemini-2.0-flash")
        self._config.setdefault("api_keys", {})
        self._config.setdefault("batch_size", 20)
        self._config.setdefault("requests_per_minute", 30)
        self._config.setdefault("auto_create_categories", True)
        self._config.setdefault("fetch_metadata", False)
        self._config.setdefault("ollama_url", "http://localhost:11434")
        self._config.setdefault("min_confidence", 0.5)
        self._config.setdefault("auto_apply", False)
        self._config.setdefault("suggest_tags", True)
        self._config.setdefault("failover_enabled", False)
        self._config.setdefault("failover_provider", "google")
        self._config.setdefault("failover_model", "gemini-2.0-flash")
        self._config.setdefault("failover_confidence_threshold", 0.6)
        self._normalize_config()

    def _bounded_int(self, value, default: int, lower: int, upper: int) -> int:
        try:
            return max(lower, min(upper, int(value)))
        except (TypeError, ValueError):
            return default

    def _bounded_float(self, value, default: float, lower: float, upper: float) -> float:
        try:
            return max(lower, min(upper, float(value)))
        except (TypeError, ValueError):
            return default

    def _normalize_config(self):
        """Normalize config loaded from disk before callers consume it."""
        provider = str(self._config.get("provider", "google")).strip().lower()
        if provider not in AI_PROVIDERS:
            log.warning(f"Unknown AI provider '{provider}', falling back to Google")
            provider = "google"
        self._config["provider"] = provider

        info = AI_PROVIDERS[provider]
        model = str(self._config.get("model") or info.default_model).strip()
        if provider != "ollama" and info.models and model not in info.models:
            model = info.default_model
        self._config["model"] = model

        api_keys = self._config.get("api_keys", {})
        if not isinstance(api_keys, dict):
            api_keys = {}
        self._config["api_keys"] = {
            str(k): str(v) for k, v in api_keys.items()
            if k in AI_PROVIDERS and v
        }

        self._config["batch_size"] = self._bounded_int(
            self._config.get("batch_size"), 20, 5, 50
        )
        self._config["requests_per_minute"] = self._bounded_int(
            self._config.get("requests_per_minute"), 30, 1, 120
        )
        self._config["min_confidence"] = self._bounded_float(
            self._config.get("min_confidence"), 0.5, 0.0, 1.0
        )
        self._config["auto_create_categories"] = bool(self._config.get("auto_create_categories", True))
        self._config["fetch_metadata"] = bool(self._config.get("fetch_metadata", False))
        self._config["auto_apply"] = bool(self._config.get("auto_apply", False))
        self._config["suggest_tags"] = bool(self._config.get("suggest_tags", True))

        ollama_url = str(self._config.get("ollama_url") or "http://localhost:11434").strip().rstrip("/")
        if not ollama_url.startswith(("http://", "https://")):
            ollama_url = "http://localhost:11434"
        try:
            from urllib.parse import urlparse as _urlparse
            host = _urlparse(ollama_url).hostname or ""
            if host not in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                log.warning(f"Ollama URL '{ollama_url}' is not localhost — restricting to localhost for SSRF safety")
                ollama_url = "http://localhost:11434"
        except Exception:
            ollama_url = "http://localhost:11434"
        self._config["ollama_url"] = ollama_url

    def save_config(self):
        """Save configuration to file"""
        try:
            self._normalize_config()
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(
                dir=self.filepath.parent, suffix='.tmp', text=True
            )
            try:
                if os.name != "nt":
                    os.fchmod(fd, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, indent=2)
                os.replace(temp_path, self.filepath)
                self._restrict_permissions()
            except Exception:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise
        except Exception as e:
            log.error(f"Error saving AI config: {e}")

    def _restrict_permissions(self):
        """Lock down the config file — it can hold plaintext API keys when the
        OS keyring is unavailable. POSIX permissions are set via fchmod before
        the rename; on Windows, restrict the ACL to the current user."""
        if os.name != "nt":
            return
        username = os.environ.get("USERNAME", "")
        if not username:
            return
        try:
            subprocess.run(
                ["icacls", str(self.filepath), "/inheritance:r",
                 "/grant:r", f"{username}:(F)"],
                capture_output=True, check=False,
            )
        except Exception as exc:  # pragma: no cover - best-effort hardening
            log.debug(f"Could not restrict AI config permissions: {exc}")

    def get_provider(self) -> str:
        return self._config.get("provider", "google")

    def get_model(self) -> str:
        return self._config.get("model", "gemini-2.0-flash")

    def get_batch_size(self) -> int:
        return self._bounded_int(self._config.get("batch_size"), 20, 5, 50)

    def get_rate_limit(self) -> int:
        return self._bounded_int(self._config.get("requests_per_minute"), 30, 1, 120)

    def get_auto_create_categories(self) -> bool:
        return self._config.get("auto_create_categories", True)

    def get_fetch_metadata(self) -> bool:
        return self._config.get("fetch_metadata", False)

    def get_ollama_url(self) -> str:
        return self._config.get("ollama_url", "http://localhost:11434")

    def get_min_confidence(self) -> float:
        return self._bounded_float(self._config.get("min_confidence"), 0.5, 0.0, 1.0)

    def get_auto_apply(self) -> bool:
        return self._config.get("auto_apply", False)

    def get_suggest_tags(self) -> bool:
        return self._config.get("suggest_tags", True)

    def get_api_key(self, provider: str = None) -> str:
        provider = provider or self.get_provider()
        key = self._get_key_from_keyring(provider)
        if not key:
            key = self._config.get("api_keys", {}).get(provider, "")
        if not key:
            info = AI_PROVIDERS.get(provider)
            if info and info.api_key_env:
                key = os.environ.get(info.api_key_env, "")
        return key

    @staticmethod
    def _get_key_from_keyring(provider: str) -> str:
        try:
            import keyring
            val = keyring.get_password("bookmark-organizer-pro", f"api_key_{provider}")
            return val or ""
        except Exception:
            return ""

    @staticmethod
    def _set_key_in_keyring(provider: str, key: str) -> bool:
        try:
            import keyring
            if key:
                keyring.set_password("bookmark-organizer-pro", f"api_key_{provider}", key)
            else:
                keyring.delete_password("bookmark-organizer-pro", f"api_key_{provider}")
            return True
        except Exception:
            return False

    def set_provider(self, v):
        provider = str(v or "").strip().lower()
        self._config["provider"] = provider if provider in AI_PROVIDERS else "google"
        self.save_config()

    def set_model(self, v):
        self._config["model"] = str(v or "").strip()
        self.save_config()

    def set_api_key(self, provider: str, key: str):
        provider = str(provider or "").strip().lower()
        if provider not in AI_PROVIDERS:
            return
        key = str(key or "").strip()
        if self._set_key_in_keyring(provider, key):
            self._config.get("api_keys", {}).pop(provider, None)
            log.info(f"API key for {provider} stored in OS keyring")
        else:
            keys = self._config.setdefault("api_keys", {})
            if key:
                keys[provider] = key
            else:
                keys.pop(provider, None)
        self.save_config()

    # Failover settings
    def get_failover_enabled(self) -> bool:
        return bool(self._config.get("failover_enabled", False))

    def set_failover_enabled(self, v: bool):
        self._config["failover_enabled"] = bool(v)
        self.save_config()

    def get_failover_provider(self) -> str:
        return self._config.get("failover_provider", "google")

    def set_failover_provider(self, v: str):
        self._config["failover_provider"] = str(v or "google").strip().lower()
        self.save_config()

    def get_failover_model(self) -> str:
        return self._config.get("failover_model", "gemini-2.0-flash")

    def set_failover_model(self, v: str):
        self._config["failover_model"] = str(v or "").strip()
        self.save_config()

    def get_failover_confidence_threshold(self) -> float:
        return self._bounded_float(self._config.get("failover_confidence_threshold"), 0.6, 0.1, 1.0)

    def set_batch_size(self, v):
        self._config["batch_size"] = self._bounded_int(v, 20, 5, 50)
        self.save_config()

    def set_rate_limit(self, v):
        self._config["requests_per_minute"] = self._bounded_int(v, 30, 1, 120)
        self.save_config()

    def set_auto_create_categories(self, v):
        self._config["auto_create_categories"] = bool(v)
        self.save_config()

    def set_fetch_metadata(self, v):
        self._config["fetch_metadata"] = bool(v)
        self.save_config()

    def set_min_confidence(self, v):
        self._config["min_confidence"] = self._bounded_float(v, 0.5, 0.0, 1.0)
        self.save_config()

    def set_auto_apply(self, v):
        self._config["auto_apply"] = bool(v)
        self.save_config()

    def set_suggest_tags(self, v):
        self._config["suggest_tags"] = bool(v)
        self.save_config()

    def is_configured(self) -> bool:
        """Check if AI is configured and ready"""
        provider = self.get_provider()
        info = AI_PROVIDERS.get(provider)
        if info and not info.requires_api_key:
            return True
        return bool(self.get_api_key())

    def get_provider_info(self) -> Optional[AIProviderInfo]:
        return AI_PROVIDERS.get(self.get_provider())


class AIClient:
    """Base class for AI provider clients."""

    supports_native_streaming = False

    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        raise NotImplementedError

    def test_connection(self) -> Tuple[bool, str]:
        raise NotImplementedError

    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 800, temperature: float = 0.2) -> str:
        """Single-turn text completion. Must be overridden by subclasses
        that support free-form generation."""
        raise NotImplementedError

    def stream_complete(self, prompt: str, system: str = "",
                        max_tokens: int = 800,
                        temperature: float = 0.2) -> Iterator[str]:
        text = self.complete(prompt, system, max_tokens, temperature)
        if text:
            yield text

    @staticmethod
    def _safe_confidence(value, default: float = 0.5) -> float:
        try:
            return min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clean_tags(value) -> List[str]:
        if isinstance(value, str):
            raw_tags = value.split(",")
        elif isinstance(value, list):
            raw_tags = value
        else:
            return []

        cleaned = []
        seen = set()
        for tag in raw_tags:
            text = re.sub(r"\s+", "-", str(tag or "").strip().lower())
            if not text:
                continue
            if text in seen:
                continue
            cleaned.append(text[:40])
            seen.add(text)
        return cleaned

    @staticmethod
    def _optional_text(value) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() in {"none", "null", "n/a"}:
            return None
        return text

    def _parse_response(self, text: str, original: List[Dict]) -> List[Dict]:
        """Parse AI response into structured results"""
        try:
            cleaned_text = text.strip()

            if "```json" in cleaned_text:
                match = re.search(r"```json\s*([\s\S]*?)\s*```", cleaned_text)
                if match:
                    cleaned_text = match.group(1)
            elif "```" in cleaned_text:
                match = re.search(r"```\s*([\s\S]*?)\s*```", cleaned_text)
                if match:
                    cleaned_text = match.group(1)

            start = cleaned_text.find('{')
            end = cleaned_text.rfind('}')

            if start != -1 and end != -1:
                json_str = cleaned_text[start:end+1]
                data = json.loads(json_str)
            else:
                data = json.loads(cleaned_text)

            if isinstance(data, dict):
                results = data.get("results", [])
            elif isinstance(data, list):
                results = data
            else:
                results = []

            cleaned = []
            for r in results:
                if not isinstance(r, dict) or "url" not in r or "category" not in r:
                    continue
                category = str(r.get("category") or "").strip()
                url = str(r.get("url") or "").strip()
                if not url or not category:
                    continue
                cleaned.append({
                    "url": url,
                    "category": category[:120],
                    "confidence": self._safe_confidence(r.get("confidence", 0.5)),
                    "new_category": bool(r.get("new_category", False)),
                    "tags": self._clean_tags(r.get("tags", [])),
                    "reasoning": str(r.get("reasoning") or "").strip()[:1000],
                    "suggested_title": self._optional_text(r.get("suggested_title")),
                })

            found_urls = {r["url"] for r in cleaned}
            for bm in original:
                url = str(bm.get("url") or "").strip()
                if url and url not in found_urls:
                    cleaned.append({
                        "url": url,
                        "category": "Uncategorized / Needs Review",
                        "confidence": 0.0,
                        "new_category": False,
                        "tags": [],
                        "reasoning": "",
                        "suggested_title": None,
                    })

            return cleaned
        except Exception as e:
            log.error(f"JSON Parse Error: {e}")
            return [{
                "url": str(bm.get("url") or ""),
                "category": "Uncategorized / Needs Review",
                "confidence": 0.0,
                "new_category": False,
                "tags": [],
                "reasoning": "",
                "suggested_title": None,
            } for bm in original if bm.get("url")]

    def _build_prompt(self, bookmarks: List[Dict], categories: List[str],
                     allow_new: bool, suggest_tags: bool) -> str:
        """Build the prompt for categorization (capped to prevent token overflow)."""
        # Cap bookmark count to prevent oversized prompts (API token limits).
        # Callers batch by the configured batch size (<= 50), so this is a
        # safety net — but if it ever trips it would silently drop bookmarks, so
        # make the truncation visible in the logs instead of losing them quietly.
        if len(bookmarks) > 50:
            log.warning(
                f"Categorization prompt received {len(bookmarks)} bookmarks; "
                f"capping to 50 to stay within token limits. The caller should "
                f"batch by ai_config batch_size so no bookmarks are dropped."
            )
            bookmarks = bookmarks[:50]
        cats_str = ', '.join(f'"{c}"' for c in categories[:50])

        tags_instruction = ""
        if suggest_tags:
            tags_instruction = """
5. Suggest 3-5 DESCRIPTIVE tags for each bookmark (short, lowercase, hyphens-ok)
   IMPORTANT TAG RULES:
   - Tags must describe the CONTENT TOPIC, not the website name
   - NEVER use the domain name as a tag (no "reddit", "youtube", "amazon", "github", etc.)
   - NEVER use generic words like "blog", "website", "page", "online", "app", "site"
   - Good tags: "python-tutorial", "home-repair", "stock-trading", "meal-prep", "cybersecurity"
   - Bad tags: "reddit", "google", "amazon", "website", "blog", "account"
6. Suggest a better title if the current one is poor (too generic, has junk like "Home |", etc.)"""

        return f"""You are a bookmark categorization expert. Analyze each bookmark and assign the most appropriate category.

AVAILABLE CATEGORIES:
{cats_str}

{"You MAY suggest a new category if none fit well. Set 'new_category': true for suggested categories." if allow_new else "Use ONLY the categories listed above."}

BOOKMARKS TO CATEGORIZE:
{json.dumps(bookmarks, indent=2)}

INSTRUCTIONS:
1. Analyze each bookmark's URL and title to determine content type
2. Match to the most specific relevant category
3. Assign a confidence score (0.0-1.0)
4. If the URL is clearly technical (github, stackoverflow, etc.) categorize as Development{tags_instruction}

Respond with ONLY valid JSON in this exact format (no markdown, no explanation):
{{"results": [{{"url": "https://example.com", "category": "Category Name", "confidence": 0.9, "new_category": false, "tags": ["tag1", "tag2"], "suggested_title": "Better Title Here or null if current is fine"}}]}}"""


def _iter_openai_chat_stream(stream) -> Iterator[str]:
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        content = getattr(delta, "content", None)
        if content:
            yield content


class OpenAICompatibleClient(AIClient):
    """Shared implementation for OpenAI-compatible chat APIs.

    OpenAI, Groq, and DeepSeek expose the identical ``chat.completions.create``
    surface; they differ only in which SDK/base URL builds the client and in the
    user-facing provider name. Subclasses override :meth:`_client_factory` (and
    the ``provider_label`` / ``api_key_hint`` class attributes); everything else
    — categorize, complete, stream, connection test, retries — is shared.
    """

    supports_native_streaming = True
    provider_label = "OpenAI"
    api_key_hint = "platform.openai.com/api-keys"
    json_mode = True  # request_format={"type": "json_object"} for categorize

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _client_factory(self):  # pragma: no cover - overridden by subclasses
        openai = ensure_package("openai")
        return openai.OpenAI(api_key=self.api_key, timeout=REQUEST_TIMEOUT)

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    f"{self.provider_label} API key is required. Get one at {self.api_key_hint}"
                )
            self._client = self._client_factory()
        return self._client

    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)

        def _call():
            kwargs = dict(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You categorize bookmarks. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            if self.json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            return self.client.chat.completions.create(**kwargs)

        response = _retry(_call, label=f"{self.provider_label} categorize")
        return self._parse_response((response.choices[0].message.content if response.choices else ''), bookmarks)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            if not self.api_key:
                return False, f"{self.provider_label} API key is required. Get one at {self.api_key_hint}"
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=10,
            )
            return True, f"Connected to {self.provider_label} ({self.model})"
        except Exception as e:
            return False, _friendly_model_error(e, self.provider_label, self.model)

    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 800, temperature: float = 0.2) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        def _call():
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        response = _retry(_call, label=f"{self.provider_label} complete")
        return response.choices[0].message.content if response.choices else ""

    def stream_complete(self, prompt: str, system: str = "",
                        max_tokens: int = 800,
                        temperature: float = 0.2) -> Iterator[str]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        yield from _iter_openai_chat_stream(stream)


class OpenAIClient(OpenAICompatibleClient):
    """OpenAI API client."""

    provider_label = "OpenAI"
    api_key_hint = "platform.openai.com/api-keys"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        super().__init__(api_key, model)

    def _client_factory(self):
        openai = ensure_package("openai")
        return openai.OpenAI(api_key=self.api_key, timeout=REQUEST_TIMEOUT)


class AnthropicClient(AIClient):
    """Anthropic Claude API client"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("Anthropic API key is required. Get one at console.anthropic.com/settings/keys")
            anthropic = ensure_package("anthropic")
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=REQUEST_TIMEOUT)
        return self._client

    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)
        response = _retry(lambda: self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        ), label="Anthropic categorize")
        return self._parse_response((response.content[0].text if response.content else ''), bookmarks)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            if not self.api_key:
                return False, "Anthropic API key is required. Get one at console.anthropic.com/settings/keys"
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Say OK"}]
            )
            return True, f"Connected to Anthropic ({self.model})"
        except Exception as e:
            return False, _friendly_model_error(e, "Anthropic", self.model)

    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 800, temperature: float = 0.2) -> str:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = _retry(lambda: self.client.messages.create(**kwargs), label="Anthropic complete")
        return response.content[0].text if response.content else ""


class GoogleClient(AIClient):
    """Google Gemini API client"""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self._client = None
        self._genai = None

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("Google API key is required. Get one at aistudio.google.com/app/apikey")
            self._genai = ensure_package("google-generativeai", "google.generativeai")
            self._genai.configure(api_key=self.api_key)
            self._client = self._genai.GenerativeModel(self.model)
        return self._client

    def _generate(self, content, **gen_kwargs):
        """Call generate_content with a request timeout when the SDK supports it.

        Older ``google-generativeai`` builds don't accept ``request_options``;
        fall back gracefully rather than crashing on a TypeError.
        """
        try:
            return self.client.generate_content(
                content, request_options={"timeout": REQUEST_TIMEOUT}, **gen_kwargs)
        except TypeError:
            return self.client.generate_content(content, **gen_kwargs)

    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)
        response = _retry(lambda: self._generate(prompt), label="Google categorize")
        return self._parse_response(response.text, bookmarks)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            if not self.api_key:
                return False, "Google API key is required. Get one at aistudio.google.com/app/apikey"
            self._generate("Say OK")
            return True, f"Connected to Google Gemini ({self.model})"
        except Exception as e:
            return False, _friendly_model_error(e, "Google Gemini", self.model)

    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 800, temperature: float = 0.2) -> str:
        full = f"{system}\n\n{prompt}" if system else prompt
        response = _retry(lambda: self._generate(
            full,
            generation_config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            },
        ), label="Google complete")
        return getattr(response, "text", "") or ""


class GroqClient(OpenAICompatibleClient):
    """Groq API client (OpenAI-compatible surface, Groq SDK)."""

    provider_label = "Groq"
    api_key_hint = "console.groq.com/keys"

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        super().__init__(api_key, model)

    def _client_factory(self):
        groq = ensure_package("groq")
        return groq.Groq(api_key=self.api_key, timeout=REQUEST_TIMEOUT)


class DeepSeekClient(OpenAICompatibleClient):
    """DeepSeek API client (OpenAI-compatible, OpenAI SDK + custom base URL)."""

    provider_label = "DeepSeek"
    api_key_hint = "platform.deepseek.com/api_keys"

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        super().__init__(api_key, model)

    def _client_factory(self):
        openai = ensure_package("openai")
        return openai.OpenAI(
            api_key=self.api_key, base_url="https://api.deepseek.com", timeout=REQUEST_TIMEOUT)


class OllamaClient(AIClient):
    """Ollama local API client"""

    supports_native_streaming = True

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2"):
        self.base_url = base_url.rstrip('/')
        self.model = model

    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        requests = importlib.import_module('requests')
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)

        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3}
            },
            timeout=120
        )
        response.raise_for_status()
        return self._parse_response(response.json()["response"], bookmarks)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            requests = importlib.import_module('requests')
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = [m["name"] for m in response.json().get("models", [])]
                if self.model in models or any(self.model in m for m in models):
                    return True, f"Connected to Ollama ({self.model})"
                return False, f"Model {self.model} not found. Available: {', '.join(models[:5])}"
            return False, "Ollama not responding"
        except Exception as e:
            return False, f"Error: {str(e)[:150]}"

    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 800, temperature: float = 0.2) -> str:
        requests = importlib.import_module('requests')
        full = f"{system}\n\n{prompt}" if system else prompt
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": full,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=180,
        )
        response.raise_for_status()
        return response.json().get("response", "")

    def stream_complete(self, prompt: str, system: str = "",
                        max_tokens: int = 800,
                        temperature: float = 0.2) -> Iterator[str]:
        requests = importlib.import_module('requests')
        full = f"{system}\n\n{prompt}" if system else prompt
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": full,
                "stream": True,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=180,
            stream=True,
        )
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = payload.get("response", "")
            if text:
                yield text


def _create_client_for(config: AIConfigManager, provider: str, model: str) -> AIClient:
    """Create a client for a specific provider/model pair."""
    if provider == "openai":
        return OpenAIClient(config.get_api_key("openai"), model)
    elif provider == "anthropic":
        return AnthropicClient(config.get_api_key("anthropic"), model)
    elif provider == "google":
        return GoogleClient(config.get_api_key("google"), model)
    elif provider == "groq":
        return GroqClient(config.get_api_key("groq"), model)
    elif provider == "deepseek":
        return DeepSeekClient(config.get_api_key("deepseek"), model)
    elif provider == "ollama":
        return OllamaClient(config.get_ollama_url(), model)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def create_ai_client(config: AIConfigManager) -> AIClient:
    """Factory function to create the appropriate AI client."""
    return _create_client_for(config, config.get_provider(), config.get_model())


def create_failover_client(config: AIConfigManager) -> "FailoverAIClient":
    """Create a client that falls back to a secondary provider on low confidence."""
    primary = create_ai_client(config)
    if not config.get_failover_enabled():
        return FailoverAIClient(primary, None, config)
    secondary = _create_client_for(
        config, config.get_failover_provider(), config.get_failover_model(),
    )
    return FailoverAIClient(primary, secondary, config)


class FailoverAIClient:
    """Wraps a primary AI client with automatic failover to a secondary on low confidence.

    On categorize: if ALL results from the primary are below the confidence threshold,
    retries with the secondary. On individual low-confidence results, retries just those.
    Callers see which provider was used via .last_provider / .last_model.
    """

    def __init__(self, primary: AIClient, secondary: Optional[AIClient],
                 config: AIConfigManager):
        self.primary = primary
        self.secondary = secondary
        self.config = config
        self.threshold = config.get_failover_confidence_threshold()
        self.last_provider = config.get_provider()
        self.last_model = config.get_model()
        self._failover_count = 0

    @property
    def failover_count(self) -> int:
        return self._failover_count

    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                             allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        results = self.primary.categorize_bookmarks(bookmarks, categories, allow_new, suggest_tags)
        self.last_provider = self.config.get_provider()
        self.last_model = self.config.get_model()

        if not self.secondary:
            return results

        low_confidence = []
        for i, r in enumerate(results):
            conf = r.get("confidence", 0)
            if conf < self.threshold:
                low_confidence.append(i)

        if low_confidence:
            retry_bms = [bookmarks[i] for i in low_confidence]
            try:
                retry_results = self.secondary.categorize_bookmarks(
                    retry_bms, categories, allow_new, suggest_tags,
                )
                for j, idx in enumerate(low_confidence):
                    if j < len(retry_results):
                        retry_conf = retry_results[j].get("confidence", 0)
                        if retry_conf > results[idx].get("confidence", 0):
                            results[idx] = retry_results[j]
                            results[idx]["_failover"] = True
                            results[idx]["_failover_provider"] = self.config.get_failover_provider()
                            results[idx]["_failover_model"] = self.config.get_failover_model()
                            self._failover_count += 1
                            log.info(
                                f"Failover: {bookmarks[idx].get('url', '')[:60]} "
                                f"({results[idx].get('confidence', 0):.0%} from "
                                f"{self.config.get_failover_provider()})"
                            )
            except Exception as exc:
                log.warning(f"Failover provider failed: {exc}")

        return results

    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 800, temperature: float = 0.2) -> str:
        try:
            result = self.primary.complete(prompt, system, max_tokens, temperature)
            self.last_provider = self.config.get_provider()
            self.last_model = self.config.get_model()
            return result
        except Exception as exc:
            if self.secondary:
                log.info(f"Primary AI failed, falling back: {exc}")
                self.last_provider = self.config.get_failover_provider()
                self.last_model = self.config.get_failover_model()
                self._failover_count += 1
                return self.secondary.complete(prompt, system, max_tokens, temperature)
            raise

    def test_connection(self) -> Tuple[bool, str]:
        return self.primary.test_connection()
