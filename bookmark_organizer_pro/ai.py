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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import AI_CONFIG_FILE
from .logging_config import log


def ensure_package(package: str, import_name: str = None):
    """Ensure a package is installed, install if missing"""
    import_name = import_name or package
    try:
        return importlib.import_module(import_name)
    except ImportError:
        log.info(f"Installing missing package: {package}")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package, "-q"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return importlib.import_module(import_name)
        except Exception as e:
            log.error(f"Error installing {package}: {e}")
            raise ImportError(f"Could not install {package}. Please install it manually.")


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
    "ollama": AIProviderInfo(
        name="ollama",
        display_name="Ollama (Local)",
        api_key_url="https://ollama.com/download",
        api_key_env="",
        models=["llama3.2", "llama3.3", "llama3.1", "mistral", "mistral-nemo",
                "qwen2.5", "qwen3", "phi4", "phi3", "gemma2", "gemma3",
                "deepseek-r1", "deepseek-coder-v2", "codellama", "command-r",
                "mixtral", "wizard-vicuna", "neural-chat", "starling-lm"],
        default_model="llama3.2",
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
            except Exception:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise
        except Exception as e:
            log.error(f"Error saving AI config: {e}")

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
        key = self._config.get("api_keys", {}).get(provider, "")
        if not key:
            info = AI_PROVIDERS.get(provider)
            if info and info.api_key_env:
                key = os.environ.get(info.api_key_env, "")
        return key

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
        keys = self._config.setdefault("api_keys", {})
        key = str(key or "").strip()
        if key:
            keys[provider] = key
        else:
            keys.pop(provider, None)
        self.save_config()

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
        # Cap bookmark count to prevent oversized prompts (API token limits)
        if len(bookmarks) > 50:
            bookmarks = bookmarks[:50]
        cats_str = ', '.join(f'"{c}"' for c in categories[:50])

        tags_instruction = ""
        if suggest_tags:
            tags_instruction = """
5. Suggest 1-3 relevant tags for each bookmark (short, lowercase, no spaces)
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


class OpenAIClient(AIClient):
    """OpenAI API client"""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("OpenAI API key is required. Get one at platform.openai.com/api-keys")
            openai = ensure_package("openai")
            self._client = openai.OpenAI(api_key=self.api_key)
        return self._client

    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You categorize bookmarks. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        return self._parse_response((response.choices[0].message.content if response.choices else ''), bookmarks)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            if not self.api_key:
                return False, "OpenAI API key is required. Get one at platform.openai.com/api-keys"
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=10
            )
            return True, f"Connected to OpenAI ({self.model})"
        except Exception as e:
            return False, f"Error: {str(e)[:200]}"

    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 800, temperature: float = 0.2) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content if response.choices else ""


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
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
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
            return False, f"Error: {str(e)[:200]}"

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
        response = self.client.messages.create(**kwargs)
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

    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)
        response = self.client.generate_content(prompt)
        return self._parse_response(response.text, bookmarks)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            if not self.api_key:
                return False, "Google API key is required. Get one at aistudio.google.com/app/apikey"
            self.client.generate_content("Say OK")
            return True, f"Connected to Google Gemini ({self.model})"
        except Exception as e:
            return False, f"Error: {str(e)[:200]}"

    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 800, temperature: float = 0.2) -> str:
        full = f"{system}\n\n{prompt}" if system else prompt
        response = self.client.generate_content(
            full,
            generation_config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        return getattr(response, "text", "") or ""


class GroqClient(AIClient):
    """Groq API client"""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model = model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("Groq API key is required. Get one at console.groq.com/keys")
            groq = ensure_package("groq")
            self._client = groq.Groq(api_key=self.api_key)
        return self._client

    def categorize_bookmarks(self, bookmarks: List[Dict], categories: List[str],
                            allow_new: bool = True, suggest_tags: bool = True) -> List[Dict]:
        prompt = self._build_prompt(bookmarks, categories, allow_new, suggest_tags)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You categorize bookmarks. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        return self._parse_response((response.choices[0].message.content if response.choices else ''), bookmarks)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            if not self.api_key:
                return False, "Groq API key is required. Get one at console.groq.com/keys"
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=10
            )
            return True, f"Connected to Groq ({self.model})"
        except Exception as e:
            return False, f"Error: {str(e)[:200]}"

    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 800, temperature: float = 0.2) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content if response.choices else ""


class OllamaClient(AIClient):
    """Ollama local API client"""

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


def create_ai_client(config: AIConfigManager) -> AIClient:
    """Factory function to create the appropriate AI client"""
    provider = config.get_provider()
    model = config.get_model()

    if provider == "openai":
        return OpenAIClient(config.get_api_key(), model)
    elif provider == "anthropic":
        return AnthropicClient(config.get_api_key(), model)
    elif provider == "google":
        return GoogleClient(config.get_api_key(), model)
    elif provider == "groq":
        return GroqClient(config.get_api_key(), model)
    elif provider == "ollama":
        return OllamaClient(config.get_ollama_url(), model)
    else:
        raise ValueError(f"Unknown provider: {provider}")
