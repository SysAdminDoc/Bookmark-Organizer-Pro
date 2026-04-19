"""AI provider configuration and client implementations.

Supports OpenAI, Anthropic Claude, Google Gemini, Groq, and Ollama (local).
"""

import importlib
import json
import os
import re
import subprocess
import sys
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
        models=["llama3.2", "llama3.1", "mistral", "qwen2.5", "phi3",
                "gemma2", "deepseek-coder-v2"],
        default_model="llama3.2",
        description="Run locally, completely free",
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
            except Exception:
                pass

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

    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            log.error(f"Error saving AI config: {e}")

    def get_provider(self) -> str:
        return self._config.get("provider", "google")

    def get_model(self) -> str:
        return self._config.get("model", "gemini-2.0-flash")

    def get_batch_size(self) -> int:
        return self._config.get("batch_size", 20)

    def get_rate_limit(self) -> int:
        return self._config.get("requests_per_minute", 30)

    def get_auto_create_categories(self) -> bool:
        return self._config.get("auto_create_categories", True)

    def get_fetch_metadata(self) -> bool:
        return self._config.get("fetch_metadata", False)

    def get_ollama_url(self) -> str:
        return self._config.get("ollama_url", "http://localhost:11434")

    def get_min_confidence(self) -> float:
        return self._config.get("min_confidence", 0.5)

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
        self._config["provider"] = v
        self.save_config()

    def set_model(self, v):
        self._config["model"] = v
        self.save_config()

    def set_api_key(self, provider: str, key: str):
        self._config.setdefault("api_keys", {})[provider] = key
        self.save_config()

    def set_batch_size(self, v):
        self._config["batch_size"] = max(5, min(50, v))
        self.save_config()

    def set_rate_limit(self, v):
        self._config["requests_per_minute"] = max(1, min(120, v))
        self.save_config()

    def set_auto_create_categories(self, v):
        self._config["auto_create_categories"] = bool(v)
        self.save_config()

    def set_fetch_metadata(self, v):
        self._config["fetch_metadata"] = bool(v)
        self.save_config()

    def set_min_confidence(self, v):
        self._config["min_confidence"] = max(0.0, min(1.0, float(v)))
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
                results = data.get("results", [])
            else:
                data = json.loads(cleaned_text)
                results = data.get("results", [])

            cleaned = []
            for r in results:
                if "url" in r and "category" in r:
                    cleaned.append({
                        "url": r["url"],
                        "category": str(r["category"]).strip(),
                        "confidence": min(1.0, max(0.0, float(r.get("confidence", 0.5)))),
                        "new_category": bool(r.get("new_category", False)),
                        "tags": r.get("tags", []),
                        "reasoning": r.get("reasoning", "")
                    })

            found_urls = {r["url"] for r in cleaned}
            for bm in original:
                if bm["url"] not in found_urls:
                    cleaned.append({
                        "url": bm["url"],
                        "category": "Uncategorized / Needs Review",
                        "confidence": 0.0,
                        "new_category": False,
                        "tags": []
                    })

            return cleaned
        except Exception as e:
            log.error(f"JSON Parse Error: {e}")
            return [{
                "url": bm["url"],
                "category": "Uncategorized / Needs Review",
                "confidence": 0.0,
                "new_category": False,
                "tags": []
            } for bm in original]

    def _build_prompt(self, bookmarks: List[Dict], categories: List[str],
                     allow_new: bool, suggest_tags: bool) -> str:
        """Build the prompt for categorization"""
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
