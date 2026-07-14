"""AI settings dialog with integrated Ollama management."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from bookmark_organizer_pro.ai import AI_PROVIDERS, create_ai_client
from bookmark_organizer_pro.i18n import _, format_message
from bookmark_organizer_pro.services.ollama_manager import (
    OLLAMA_DEFAULT_URL,
    OllamaManager,
    OllamaStatus,
)
from bookmark_organizer_pro.ui.components import ScrollableFrame
from bookmark_organizer_pro.ui.foundation import FONTS, pluralize
from bookmark_organizer_pro.ui.widgets import ModernButton, apply_window_chrome, get_theme


class AiSettingsMixin:
    """AI settings UI and provider connection testing workflow."""

    def _show_ai_settings(self):
        theme = get_theme()

        dialog = tk.Toplevel(self.root)
        dialog.title(_("Assistant Settings"))
        dialog.configure(bg=theme.bg_primary)
        dialog.geometry("660x720")
        dialog.minsize(600, 620)
        dialog.transient(self.root)
        dialog.grab_set()
        apply_window_chrome(dialog)

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 660) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 720) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")

        # ── Header ──
        header = tk.Frame(dialog, bg=theme.bg_secondary, padx=24, pady=16)
        header.pack(fill=tk.X)

        tk.Label(
            header, text=_("Assistant Settings"), bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.title(bold=True),
        ).pack(anchor="w")

        tk.Label(
            header,
            text=_("Choose how bookmark categorization, tag suggestions, summaries, and library chat should run."),
            bg=theme.bg_secondary, fg=theme.text_secondary,
            font=FONTS.small(), wraplength=600, justify=tk.LEFT,
        ).pack(anchor="w", pady=(4, 0))

        # ── Scrollable content ──
        scroll = ScrollableFrame(dialog, bg=theme.bg_primary)
        scroll.pack(fill=tk.BOTH, expand=True)
        body = tk.Frame(scroll.inner, bg=theme.bg_primary, padx=24, pady=14)
        body.pack(fill=tk.BOTH, expand=True)

        # ── Provider selection ──
        tk.Label(
            body, text=_("Provider"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body(bold=True),
        ).pack(anchor="w", pady=(8, 6))

        provider_var = tk.StringVar(value=self.ai_config.get_provider())
        provider_frame = tk.Frame(body, bg=theme.bg_primary)
        provider_frame.pack(fill=tk.X, pady=(0, 8))

        for pname, info in AI_PROVIDERS.items():
            row = tk.Frame(provider_frame, bg=theme.bg_primary)
            row.pack(fill=tk.X, pady=1)

            rb = tk.Radiobutton(
                row, text=info.display_name, variable=provider_var, value=pname,
                bg=theme.bg_primary, fg=theme.text_primary,
                activebackground=theme.bg_primary, activeforeground=theme.text_primary,
                selectcolor=theme.bg_secondary, font=FONTS.body(),
            )
            rb.pack(side=tk.LEFT)

            badge = ""
            if info.free_tier:
                badge = " · Free" if not info.local else " · Free · Local"
            tk.Label(
                row, text=format_message('  {value_0}{value_1}', value_0=info.description, value_1=badge),
                bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.small(),
                wraplength=430, justify=tk.LEFT,
            ).pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)

        # ── Separator ──
        tk.Frame(body, bg=theme.border_muted, height=1).pack(fill=tk.X, pady=10)

        # ── Model selection ──
        tk.Label(
            body, text=_("Model"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body(bold=True),
        ).pack(anchor="w", pady=(0, 4))

        model_var = tk.StringVar(value=self.ai_config.get_model())
        model_combo = ttk.Combobox(body, textvariable=model_var, state="readonly", width=48)
        model_combo.pack(anchor="w", pady=(0, 8), ipady=3)

        # ── API key section ──
        api_key_frame = tk.Frame(body, bg=theme.bg_primary)

        tk.Label(
            api_key_frame, text=_("API key"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body(bold=True),
        ).pack(anchor="w", pady=(0, 4))

        api_key_var = tk.StringVar(value=self.ai_config.get_api_key())
        api_entry = tk.Entry(
            api_key_frame, textvariable=api_key_var, show="•",
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, font=FONTS.body(),
            relief=tk.FLAT, width=52, highlightthickness=1,
            highlightbackground=theme.border_muted, highlightcolor=theme.accent_primary,
        )
        api_entry.pack(anchor="w", ipady=5, pady=(0, 4))

        key_row = tk.Frame(api_key_frame, bg=theme.bg_primary)
        key_row.pack(anchor="w")

        def toggle_key():
            if api_entry.cget("show") == "•":
                api_entry.configure(show="")
                show_btn.set_text(_("Hide"))
            else:
                api_entry.configure(show="•")
                show_btn.set_text(_("Show"))

        show_btn = ModernButton(key_row, text=_("Show"), command=toggle_key, padx=8, pady=3, font=FONTS.small())
        show_btn.pack(side=tk.LEFT, padx=(0, 8))

        provider_info = AI_PROVIDERS.get(provider_var.get())
        if provider_info and provider_info.api_key_url:
            def _open_key_url():
                import webbrowser
                info = AI_PROVIDERS.get(provider_var.get())
                if info and info.api_key_url:
                    webbrowser.open(info.api_key_url)

            get_key_btn = ModernButton(key_row, text=_("Get API key"), command=_open_key_url, padx=8, pady=3, font=FONTS.small())
            get_key_btn.pack(side=tk.LEFT)

        # ── Ollama management panel ──
        ollama_panel = tk.Frame(body, bg=theme.bg_secondary, padx=16, pady=14,
                                highlightbackground=theme.border_muted, highlightthickness=1)

        OllamaManager(self.ai_config.get_ollama_url())

        # Status line
        ollama_status_var = tk.StringVar(value=_("Checking Ollama…"))
        ollama_status_label = tk.Label(
            ollama_panel, textvariable=ollama_status_var,
            bg=theme.bg_secondary, fg=theme.text_secondary, font=FONTS.body(),
        )

        # Status indicator dot
        ollama_dot = tk.Label(
            ollama_panel, text=_("●"), bg=theme.bg_secondary,
            fg=theme.text_muted, font=FONTS.body(),
        )

        # Header row
        ollama_header = tk.Frame(ollama_panel, bg=theme.bg_secondary)
        ollama_header.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            ollama_header, text=_("Ollama Local"), bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.body(bold=True),
        ).pack(side=tk.LEFT)

        ollama_dot.pack(in_=ollama_header, side=tk.RIGHT)
        ollama_status_label.pack(in_=ollama_header, side=tk.RIGHT, padx=(0, 6))

        # URL field
        url_row = tk.Frame(ollama_panel, bg=theme.bg_secondary)
        url_row.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            url_row, text=_("Server"), bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small(),
        ).pack(side=tk.LEFT, padx=(0, 6))

        ollama_url_var = tk.StringVar(value=self.ai_config.get_ollama_url())
        ollama_url_entry = tk.Entry(
            url_row, textvariable=ollama_url_var,
            bg=theme.bg_primary, fg=theme.text_primary,
            insertbackground=theme.text_primary, font=FONTS.small(),
            relief=tk.FLAT, width=30, highlightthickness=1,
            highlightbackground=theme.border_muted, highlightcolor=theme.accent_primary,
        )
        ollama_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        # Action buttons row
        action_row = tk.Frame(ollama_panel, bg=theme.bg_secondary)
        action_row.pack(fill=tk.X, pady=(0, 8))

        install_btn = ModernButton(action_row, text=_("Install Ollama"), style="primary", padx=10, pady=4, font=FONTS.small())
        install_btn.pack(side=tk.LEFT, padx=(0, 6))

        start_btn = ModernButton(action_row, text=_("Start Server"), padx=10, pady=4, font=FONTS.small())
        start_btn.pack(side=tk.LEFT, padx=(0, 6))

        refresh_btn = ModernButton(action_row, text=_("Refresh"), padx=10, pady=4, font=FONTS.small())
        refresh_btn.pack(side=tk.LEFT)

        # Model download section
        download_frame = tk.Frame(ollama_panel, bg=theme.bg_secondary)
        download_frame.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            download_frame, text=_("Download model"), bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small(),
        ).pack(side=tk.LEFT, padx=(0, 6))

        popular = OllamaManager.get_popular_models()
        model_names_for_pull = [f"{m[0]}  ({m[1]}) — {m[2]}" for m in popular]

        pull_var = tk.StringVar(value=model_names_for_pull[0] if model_names_for_pull else "")
        pull_combo = ttk.Combobox(download_frame, textvariable=pull_var, values=model_names_for_pull, state="readonly", width=40)
        pull_combo.pack(side=tk.LEFT, padx=(0, 6), ipady=2)

        # Progress label for downloads
        progress_var = tk.StringVar(value="")
        progress_label = tk.Label(
            ollama_panel, textvariable=progress_var,
            bg=theme.bg_secondary, fg=theme.accent_primary, font=FONTS.small(),
        )

        # Local models list
        local_models_frame = tk.Frame(ollama_panel, bg=theme.bg_secondary)
        local_models_label = tk.Label(
            local_models_frame, text="", bg=theme.bg_secondary,
            fg=theme.text_secondary, font=FONTS.small(), justify=tk.LEFT, anchor="w",
        )
        local_models_label.pack(anchor="w")

        def _update_ollama_status(status: OllamaStatus):
            if not dialog.winfo_exists():
                return
            if not status.installed:
                ollama_status_var.set(_("Not installed"))
                ollama_dot.configure(fg=theme.accent_error)
                install_btn.set_state("normal")
                start_btn.set_state("disabled")
            elif not status.running:
                ollama_status_var.set(_("Installed (v{version}) — server stopped").format(version=status.version))
                ollama_dot.configure(fg=theme.accent_warning)
                install_btn.set_state("disabled")
                start_btn.set_state("normal")
            else:
                n = len(status.models)
                ollama_status_var.set(_("Running — {models} available").format(models=pluralize(n, 'model')))
                ollama_dot.configure(fg=theme.accent_success)
                install_btn.set_state("disabled")
                start_btn.set_state("disabled")

                # Update model combo with local models
                local_names = [m["name"] for m in status.models]
                current_vals = list(model_combo["values"] or [])
                merged = list(dict.fromkeys(local_names + current_vals))
                model_combo["values"] = merged

                if model_var.get() not in merged and merged:
                    model_var.set(merged[0])

                # Show local models list
                if status.models:
                    lines = [_("Installed models:")]
                    for m in status.models:
                        lines.append(f"  • {m['name']}  ({m.get('size', '')})")
                    local_models_label.configure(text="\n".join(lines))
                    local_models_frame.pack(fill=tk.X, pady=(6, 0))
                else:
                    local_models_frame.pack_forget()

        def _refresh_ollama():
            ollama_status_var.set(_("Checking…"))
            ollama_dot.configure(fg=theme.text_muted)

            def worker():
                mgr = OllamaManager(ollama_url_var.get().strip() or OLLAMA_DEFAULT_URL)
                status = mgr.detect()
                self.root.after(0, lambda: _update_ollama_status(status))

            threading.Thread(target=worker, daemon=True).start()

        def _install_ollama():
            install_btn.set_state("disabled")
            install_btn.set_text(_("Installing…"))
            progress_var.set(_("Starting installation…"))
            progress_label.pack(fill=tk.X, pady=(4, 0))

            def on_progress(msg):
                self.root.after(0, lambda: progress_var.set(msg))

            def on_done(ok, msg):
                def update():
                    if not dialog.winfo_exists():
                        return
                    install_btn.set_text(_("Install Ollama"))
                    if ok:
                        progress_var.set(_("Installed! Starting server…"))
                        _start_ollama()
                    else:
                        progress_var.set(f"Install failed: {msg[:80]}")
                        install_btn.set_state("normal")
                self.root.after(0, update)

            OllamaManager().install(on_progress=on_progress, on_done=on_done)

        def _start_ollama():
            start_btn.set_state("disabled")
            start_btn.set_text(_("Starting…"))
            progress_var.set(_("Starting Ollama server…"))
            progress_label.pack(fill=tk.X, pady=(4, 0))

            def on_done(ok, msg):
                def update():
                    if not dialog.winfo_exists():
                        return
                    start_btn.set_text(_("Start Server"))
                    if ok:
                        progress_var.set(_("Server is running!"))
                        _refresh_ollama()
                    else:
                        progress_var.set(f"Start failed: {msg[:80]}")
                        start_btn.set_state("normal")
                self.root.after(0, update)

            OllamaManager(ollama_url_var.get().strip() or OLLAMA_DEFAULT_URL).start_server(on_done=on_done)

        def _pull_model():
            selected = pull_var.get()
            if not selected:
                return
            model_name = selected.split("  (")[0].strip()
            pull_btn.set_state("disabled")
            pull_btn.set_text(_("Downloading…"))
            progress_var.set(_("Pulling {model}…").format(model=model_name))
            progress_label.pack(fill=tk.X, pady=(4, 0))

            def on_progress(msg):
                self.root.after(0, lambda: progress_var.set(msg[:80]))

            def on_done(ok, msg):
                def update():
                    if not dialog.winfo_exists():
                        return
                    pull_btn.set_text(_("Download"))
                    pull_btn.set_state("normal")
                    if ok:
                        progress_var.set(_("{model} ready!").format(model=model_name))
                        _refresh_ollama()
                    else:
                        progress_var.set(f"Pull failed: {msg[:80]}")
                self.root.after(0, update)

            OllamaManager(ollama_url_var.get().strip() or OLLAMA_DEFAULT_URL).pull_model(
                model_name, on_progress=on_progress, on_done=on_done,
            )

        pull_btn = ModernButton(download_frame, text=_("Download"), style="primary", padx=10, pady=4, font=FONTS.small())
        pull_btn.pack(side=tk.LEFT)

        install_btn.command = _install_ollama
        start_btn.command = _start_ollama
        refresh_btn.command = _refresh_ollama

        # ── Failover settings ──
        tk.Frame(body, bg=theme.border_muted, height=1).pack(fill=tk.X, pady=10)

        tk.Label(
            body, text=_("Reliability"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body(bold=True),
        ).pack(anchor="w", pady=(0, 4))
        tk.Label(
            body,
            text=_("Use a second provider only when the first result has low confidence."),
            bg=theme.bg_primary, fg=theme.text_muted,
            font=FONTS.small(), wraplength=590, justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 6))

        failover_frame = tk.Frame(body, bg=theme.bg_primary)
        failover_frame.pack(fill=tk.X, pady=(0, 8))

        failover_enabled_var = tk.BooleanVar(value=self.ai_config.get_failover_enabled())
        tk.Checkbutton(
            failover_frame,
            text=_("Retry uncertain results with a second provider"),
            variable=failover_enabled_var,
            bg=theme.bg_primary, fg=theme.text_primary,
            activebackground=theme.bg_primary, activeforeground=theme.text_primary,
            selectcolor=theme.bg_secondary, font=FONTS.body(),
        ).pack(anchor="w")

        failover_detail = tk.Frame(failover_frame, bg=theme.bg_primary, padx=20)
        failover_detail.pack(fill=tk.X, pady=(4, 0))

        tk.Label(
            failover_detail, text=_("Failover provider:"), bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.small(),
        ).grid(row=0, column=0, sticky="w", pady=2)

        fo_providers = [n for n in AI_PROVIDERS if n != "ollama"]
        fo_provider_var = tk.StringVar(value=self.ai_config.get_failover_provider())
        fo_combo = ttk.Combobox(failover_detail, textvariable=fo_provider_var,
                                values=fo_providers, state="readonly", width=16)
        fo_combo.grid(row=0, column=1, padx=8, pady=2)

        tk.Label(
            failover_detail, text=_("Model:"), bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.small(),
        ).grid(row=0, column=2, sticky="w", pady=2)

        fo_model_var = tk.StringVar(value=self.ai_config.get_failover_model())
        fo_model_combo = ttk.Combobox(failover_detail, textvariable=fo_model_var, width=20)
        fo_model_combo.grid(row=0, column=3, padx=8, pady=2)

        def _update_fo_models(*_):
            fp = fo_provider_var.get()
            info = AI_PROVIDERS.get(fp)
            if info:
                fo_model_combo["values"] = info.models
                if fo_model_var.get() not in info.models:
                    fo_model_var.set(info.default_model)
        fo_provider_var.trace_add("write", _update_fo_models)
        _update_fo_models()

        tk.Label(
            failover_detail, text=_("Threshold:"), bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.small(),
        ).grid(row=1, column=0, sticky="w", pady=2)

        fo_thresh_var = tk.DoubleVar(value=self.ai_config.get_failover_confidence_threshold())
        ttk.Spinbox(failover_detail, from_=0.1, to=1.0, increment=0.1,
                     textvariable=fo_thresh_var, width=6, format="%.1f").grid(row=1, column=1, padx=8, pady=2)

        tk.Label(
            failover_detail, text=_("Results below this confidence retry with the failover provider"),
            bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.small(),
        ).grid(row=1, column=2, columnspan=2, sticky="w", pady=2)

        # ── Pacing settings ──
        tk.Frame(body, bg=theme.border_muted, height=1).pack(fill=tk.X, pady=10)

        tk.Label(
            body, text=_("Processing Limits"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body(bold=True),
        ).pack(anchor="w", pady=(0, 4))
        tk.Label(
            body,
            text=_("Keep batch size and request rate conservative for steadier long runs."),
            bg=theme.bg_primary, fg=theme.text_muted,
            font=FONTS.small(), wraplength=590, justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 6))

        settings_frame = tk.Frame(body, bg=theme.bg_primary)
        settings_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            settings_frame, text=_("Batch size"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.small(),
        ).grid(row=0, column=0, sticky="w", pady=4)

        batch_var = tk.IntVar(value=self.ai_config.get_batch_size())
        ttk.Spinbox(settings_frame, from_=5, to=50, textvariable=batch_var, width=8).grid(row=0, column=1, padx=10, pady=4)

        tk.Label(
            settings_frame, text=_("Rate limit (req/min)"), bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.small(),
        ).grid(row=1, column=0, sticky="w", pady=4)

        rate_var = tk.IntVar(value=self.ai_config.get_rate_limit())
        ttk.Spinbox(settings_frame, from_=1, to=120, textvariable=rate_var, width=8).grid(row=1, column=1, padx=10, pady=4)

        # ── Provider change handler ──
        def on_provider_change(*_):
            provider = provider_var.get()
            info = AI_PROVIDERS.get(provider)
            if info:
                model_combo["values"] = info.models
                if model_var.get() not in info.models:
                    model_var.set(info.default_model)
                api_key_var.set(self.ai_config.get_api_key(provider))

            if provider == "ollama":
                ollama_panel.pack(fill=tk.X, pady=(8, 4), before=failover_frame)
                api_key_frame.pack_forget()
                _refresh_ollama()
            else:
                ollama_panel.pack_forget()
                api_key_frame.pack(fill=tk.X, pady=(0, 8), before=failover_frame)

        provider_var.trace_add("write", on_provider_change)
        on_provider_change()

        # ── Test connection ──
        def test_connection():
            provider = provider_var.get()
            model = model_var.get()
            key = api_key_var.get()

            if not key and provider not in ("ollama",):
                pl = AI_PROVIDERS.get(provider)
                messagebox.showwarning(
                    _("API Key Required"),
                    _("Enter an API key for {provider} before testing.").format(provider=pl.display_name if pl else provider),
                    parent=dialog,
                )
                return

            old_provider = self.ai_config.get_provider()
            old_model = self.ai_config.get_model()
            old_key = self.ai_config.get_api_key(provider)

            self.ai_config._config["provider"] = provider
            self.ai_config._config["model"] = model
            self.ai_config._config.setdefault("api_keys", {})[provider] = key
            if provider == "ollama":
                self.ai_config._config["ollama_url"] = ollama_url_var.get().strip() or OLLAMA_DEFAULT_URL

            try:
                client = create_ai_client(self.ai_config)
                success, message = client.test_connection()
                if success:
                    messagebox.showinfo(_("Connection Successful"), message, parent=dialog)
                else:
                    messagebox.showerror(_("Connection Failed"), message, parent=dialog)
            except Exception as e:
                messagebox.showerror(_("Connection Failed"), str(e)[:300], parent=dialog)
            finally:
                self.ai_config._config["provider"] = old_provider
                self.ai_config._config["model"] = old_model
                if old_key:
                    self.ai_config._config.setdefault("api_keys", {})[provider] = old_key
                elif provider in self.ai_config._config.get("api_keys", {}):
                    del self.ai_config._config["api_keys"][provider]

        test_btn = ModernButton(
            body, text=_("Test Provider"), command=test_connection,
            style="primary", padx=14, pady=6,
        )
        test_btn.pack(anchor="w", pady=(8, 4))

        # ── Footer buttons ──
        footer = tk.Frame(dialog, bg=theme.bg_secondary, padx=20, pady=14)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        def save():
            self.ai_config.set_provider(provider_var.get())
            self.ai_config.set_model(model_var.get())
            self.ai_config.set_api_key(provider_var.get(), api_key_var.get())
            self.ai_config.set_batch_size(batch_var.get())
            self.ai_config.set_rate_limit(rate_var.get())
            if provider_var.get() == "ollama":
                url = ollama_url_var.get().strip().rstrip("/")
                if url:
                    self.ai_config._config["ollama_url"] = url
            # Failover
            self.ai_config._config["failover_enabled"] = failover_enabled_var.get()
            self.ai_config._config["failover_provider"] = fo_provider_var.get()
            self.ai_config._config["failover_model"] = fo_model_var.get()
            self.ai_config._config["failover_confidence_threshold"] = fo_thresh_var.get()
            self.ai_config.save_config()
            dialog.destroy()
            self._show_toast(_("Assistant settings saved"), "success")

        ModernButton(footer, text=_("Save Settings"), command=save, style="success", padx=20, pady=7).pack(side=tk.RIGHT)
        ModernButton(footer, text=_("Cancel"), command=dialog.destroy, padx=16, pady=7).pack(side=tk.RIGHT, padx=(0, 8))
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.bind("<Control-Return>", lambda e: save())
