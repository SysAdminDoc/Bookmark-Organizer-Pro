"""AI settings dialog actions for the app coordinator."""

from __future__ import annotations

import json
import re
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - optional runtime dependency
    requests = None

from bookmark_organizer_pro.ai import AI_PROVIDERS, create_ai_client
from bookmark_organizer_pro.core.category_manager import get_category_icon
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark, Category
from bookmark_organizer_pro.ui.components import ScrollableFrame
from bookmark_organizer_pro.ui.foundation import FONTS, pluralize
from bookmark_organizer_pro.ui.widgets import ModernButton, apply_window_chrome, get_theme


class AiSettingsMixin:
    """AI settings UI and provider connection testing workflow."""

    def _show_ai_settings(self):
        """Show AI settings dialog"""
        theme = get_theme()
        
        dialog = tk.Toplevel(self.root)
        dialog.title("AI Settings")
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("560x660")
        dialog.minsize(520, 560)
        dialog.transient(self.root)
        dialog.grab_set()
        apply_window_chrome(dialog)
        
        # Center dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 560) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 660) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Header
        header = tk.Frame(dialog, bg=theme.bg_secondary, padx=24, pady=18)
        header.pack(fill=tk.X)
        
        tk.Label(
            header, text="AI settings", bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(anchor="w")
        
        tk.Label(
            header,
            text="Choose the provider and pacing used for categorization, tags, descriptions, and title cleanup.",
            bg=theme.bg_secondary, fg=theme.text_secondary,
            font=FONTS.small(), wraplength=500, justify=tk.LEFT
        ).pack(anchor="w", pady=(5, 0))
        
        # Scrollable content
        scroll_area = ScrollableFrame(dialog, bg=theme.bg_primary)
        scroll_area.pack(fill=tk.BOTH, expand=True)
        content_frame = tk.Frame(scroll_area.inner, bg=theme.bg_primary, padx=24, pady=16)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Provider selection
        tk.Label(
            content_frame, text="Provider", bg=theme.bg_primary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(10, 5))
        
        provider_var = tk.StringVar(value=self.ai_config.get_provider())
        provider_frame = tk.Frame(content_frame, bg=theme.bg_primary)
        provider_frame.pack(fill=tk.X, pady=5)
        
        for provider_name, info in AI_PROVIDERS.items():
            rb = tk.Radiobutton(
                provider_frame, text=f"{info.display_name}",
                variable=provider_var, value=provider_name,
                bg=theme.bg_primary, fg=theme.text_primary,
                activebackground=theme.bg_primary, activeforeground=theme.text_primary,
                selectcolor=theme.bg_secondary, font=FONTS.small()
            )
            rb.pack(anchor="w", pady=2)
            
            desc = tk.Label(
                provider_frame, text=f"   {info.description}",
                bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.tiny()
            )
            desc.pack(anchor="w")
        
        # Model selection
        tk.Label(
            content_frame, text="Model", bg=theme.bg_primary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(15, 5))
        
        model_var = tk.StringVar(value=self.ai_config.get_model())
        model_combo = ttk.Combobox(content_frame, textvariable=model_var, state="readonly", width=44)
        model_combo.pack(anchor="w", pady=5, ipady=3)
        
        # API Key
        tk.Label(
            content_frame, text="API key", bg=theme.bg_primary,
            fg=theme.text_primary, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(15, 5))

        tk.Label(
            content_frame,
            text="Stored locally in this app. Ollama does not require a cloud API key.",
            bg=theme.bg_primary, fg=theme.text_muted,
            font=FONTS.tiny(), wraplength=480, justify=tk.LEFT
        ).pack(anchor="w", pady=(0, 5))
        
        api_key_var = tk.StringVar(value=self.ai_config.get_api_key())
        api_entry = tk.Entry(
            content_frame, textvariable=api_key_var, show="•",
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary,
            disabledbackground=theme.bg_tertiary,
            disabledforeground=theme.text_muted,
            font=FONTS.body(), relief=tk.FLAT, width=48,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.accent_primary
        )
        api_entry.pack(anchor="w", ipady=5, pady=5)
        
        # Show/Hide key button
        def toggle_key():
            if api_entry.cget('show') == '•':
                api_entry.configure(show='')
                show_btn.set_text("Hide key")
            else:
                api_entry.configure(show='•')
                show_btn.set_text("Show key")
        
        show_btn = ModernButton(content_frame, text="Show key", command=toggle_key, padx=10, pady=4, font=FONTS.tiny())
        show_btn.pack(anchor="w", pady=2)
        
        # Ollama server URL field
        ollama_frame = tk.Frame(content_frame, bg=theme.bg_primary)

        tk.Label(
            ollama_frame, text="Ollama server URL", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.small(bold=True)
        ).pack(anchor="w", pady=(0, 3))

        ollama_url_var = tk.StringVar(value=self.ai_config.get_ollama_url())
        ollama_url_entry = tk.Entry(
            ollama_frame, textvariable=ollama_url_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary,
            font=FONTS.body(), relief=tk.FLAT, width=46,
            highlightthickness=1, highlightbackground=theme.border_muted,
            highlightcolor=theme.accent_primary
        )
        ollama_url_entry.pack(anchor="w", ipady=4, pady=2)

        tk.Label(
            ollama_frame, text="Default: http://localhost:11434",
            bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.tiny()
        ).pack(anchor="w")

        # Detect Ollama models button
        def detect_ollama_models():
            raw_url = ollama_url_var.get().strip()
            if not raw_url:
                self._show_toast("Enter an Ollama server URL before detecting models.", "warning")
                ollama_url_entry.focus_set()
                return

            url = raw_url if "://" in raw_url else f"http://{raw_url}"
            url = url.rstrip("/")
            ollama_url_var.set(url)
            detect_btn.set_state("disabled")
            detect_btn.set_text("Detecting…")

            def finish(kind: str, payload):
                if not dialog.winfo_exists():
                    return
                detect_btn.set_state("normal")
                detect_btn.set_text("Detect models")
                if kind == "models":
                    models = payload
                    model_combo['values'] = models
                    if model_var.get() not in models:
                        model_var.set(models[0])
                    self._show_toast(f"Found {pluralize(len(models), 'Ollama model')}", "success")
                elif kind == "empty":
                    self._show_toast(
                        "Ollama is running, but no models are installed. Run: ollama pull llama3.2",
                        "warning"
                    )
                elif kind == "status":
                    self._show_toast(f"Ollama responded with HTTP {payload}. Check the server URL.", "error")
                else:
                    self._show_toast(f"Cannot reach Ollama at {url}: {str(payload)[:80]}", "error")

            def worker():
                try:
                    import requests as req
                    resp = req.get(f"{url}/api/tags", timeout=5)
                    if resp.status_code == 200:
                        models = [m["name"] for m in resp.json().get("models", []) if m.get("name")]
                        self.root.after(0, lambda models=models: finish("models" if models else "empty", models))
                    else:
                        self.root.after(0, lambda status=resp.status_code: finish("status", status))
                except Exception as e:
                    self.root.after(0, lambda error=e: finish("error", error))

            threading.Thread(target=worker, daemon=True).start()

        detect_btn = ModernButton(
            ollama_frame, text="Detect models", command=detect_ollama_models,
            style="primary", padx=12, pady=5, font=FONTS.tiny()
        )
        detect_btn.pack(anchor="w", pady=(5, 0))

        # Update models when provider changes
        def on_provider_change(*args):
            provider = provider_var.get()
            info = AI_PROVIDERS.get(provider)
            if info:
                model_combo['values'] = info.models
                if model_var.get() not in info.models:
                    model_var.set(info.default_model)
                # Update API key field
                api_key_var.set(self.ai_config.get_api_key(provider))

            # Show/hide Ollama-specific fields
            if provider == "ollama":
                ollama_frame.pack(fill=tk.X, pady=(10, 5), before=settings_frame)
                api_entry.configure(state="disabled")
            else:
                ollama_frame.pack_forget()
                api_entry.configure(state="normal")

        # Batch size and rate limit
        settings_frame = tk.Frame(content_frame, bg=theme.bg_primary)
        settings_frame.pack(fill=tk.X, pady=(15, 5))
        
        tk.Label(
            settings_frame, text="Batch size", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.small()
        ).grid(row=0, column=0, sticky="w", pady=5)
        
        batch_var = tk.IntVar(value=self.ai_config.get_batch_size())
        batch_spin = ttk.Spinbox(settings_frame, from_=5, to=50, textvariable=batch_var, width=8)
        batch_spin.grid(row=0, column=1, padx=10, pady=5)
        
        tk.Label(
            settings_frame, text="Rate limit (req/min)", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.small()
        ).grid(row=1, column=0, sticky="w", pady=5)
        
        rate_var = tk.IntVar(value=self.ai_config.get_rate_limit())
        rate_spin = ttk.Spinbox(settings_frame, from_=1, to=120, textvariable=rate_var, width=8)
        rate_spin.grid(row=1, column=1, padx=10, pady=5)

        provider_var.trace_add('write', on_provider_change)
        on_provider_change()  # Initialize after dependent fields are packed
        
        # Test connection button
        def test_connection():
            provider = provider_var.get()
            model = model_var.get()
            key = api_key_var.get()
            
            # Validate API key is provided (except for Ollama)
            if not key and provider != "ollama":
                provider_label = AI_PROVIDERS.get(provider).display_name if provider in AI_PROVIDERS else provider
                messagebox.showwarning(
                    "API Key Required",
                    f"Enter an API key for {provider_label} before testing the connection.\n\n"
                    "You can get an API key from:\n"
                    "• OpenAI: platform.openai.com/api-keys\n"
                    "• Anthropic: console.anthropic.com/settings/keys\n"
                    "• Google: aistudio.google.com/app/apikey\n"
                    "• Groq: console.groq.com/keys",
                    parent=dialog)
                return
            
            # Temporarily set provider, model, and key for test
            old_provider = self.ai_config.get_provider()
            old_model = self.ai_config.get_model()
            old_key = self.ai_config.get_api_key(provider)
            
            # Set all values temporarily (without saving to file)
            self.ai_config._config["provider"] = provider
            self.ai_config._config["model"] = model
            self.ai_config._config.setdefault("api_keys", {})[provider] = key
            
            try:
                client = create_ai_client(self.ai_config)
                success, message = client.test_connection()
                
                if success:
                    messagebox.showinfo(
                        "Connection Successful",
                        f"{self._ai_provider_name()} responded successfully.\n\n{message}",
                        parent=dialog
                    )
                else:
                    messagebox.showerror(
                        "Connection Failed",
                        f"The provider responded, but the connection test did not pass.\n\n{message}",
                        parent=dialog
                    )
            except Exception as e:
                error_msg = str(e)
                # Provide helpful hints based on error
                hint = ""
                if "API_KEY" in error_msg or "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
                    hint = "\n\nHint: Check that your API key is correct and active."
                elif "model" in error_msg.lower():
                    hint = f"\n\nHint: The model '{model}' may not be available for your account."
                elif "quota" in error_msg.lower() or "rate" in error_msg.lower():
                    hint = "\n\nHint: You may have exceeded your API quota or rate limit."
                
                messagebox.showerror(
                    "Connection Failed",
                    f"The connection test could not be completed.\n\n{error_msg[:300]}{hint}",
                    parent=dialog
                )
            finally:
                # Restore original values
                self.ai_config._config["provider"] = old_provider
                self.ai_config._config["model"] = old_model
                if old_key:
                    self.ai_config._config.setdefault("api_keys", {})[provider] = old_key
                elif provider in self.ai_config._config.get("api_keys", {}):
                    del self.ai_config._config["api_keys"][provider]
        
        test_btn = ModernButton(
            content_frame, text="Test connection", command=test_connection,
            style="primary", padx=16, pady=7
        )
        test_btn.pack(anchor="w", pady=(15, 5))
        
        # Buttons
        btn_frame = tk.Frame(dialog, bg=theme.bg_secondary, padx=20, pady=15)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        def save():
            self.ai_config.set_provider(provider_var.get())
            self.ai_config.set_model(model_var.get())
            self.ai_config.set_api_key(provider_var.get(), api_key_var.get())
            self.ai_config.set_batch_size(batch_var.get())
            self.ai_config.set_rate_limit(rate_var.get())
            # Save Ollama URL if using Ollama
            if provider_var.get() == "ollama":
                url = ollama_url_var.get().strip().rstrip('/')
                if url:
                    self.ai_config._config["ollama_url"] = url
            self.ai_config.save_config()
            dialog.destroy()
            self._show_toast("AI settings saved", "success")
        
        save_btn = ModernButton(btn_frame, text="Save settings", command=save, style="success", padx=22, pady=8)
        save_btn.pack(side=tk.RIGHT)
        
        cancel_btn = ModernButton(btn_frame, text="Cancel", command=dialog.destroy, padx=18, pady=8)
        cancel_btn.pack(side=tk.RIGHT, padx=(0, 10))
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.bind("<Control-Return>", lambda e: save())

