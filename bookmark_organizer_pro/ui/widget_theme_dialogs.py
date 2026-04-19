"""Theme selection and custom-theme editor dialogs."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Dict, List, Tuple

from .foundation import FONTS
from .theme import ThemeInfo, ThemeManager
from .widget_controls import ModernButton, ThemedWidget
from .widget_runtime import apply_window_chrome, get_theme

# =============================================================================
# Custom Theme Creator Dialog
# =============================================================================
class ThemeCreatorDialog(tk.Toplevel, ThemedWidget):
    """Dialog for creating and editing custom themes"""
    
    COLOR_FIELDS = [
        ("Background", [
            ("bg_dark", "Dark Background"),
            ("bg_primary", "Primary Background"),
            ("bg_secondary", "Secondary Background"),
            ("bg_tertiary", "Tertiary Background"),
            ("bg_hover", "Hover Background"),
        ]),
        ("Text", [
            ("text_primary", "Primary Text"),
            ("text_secondary", "Secondary Text"),
            ("text_muted", "Muted Text"),
            ("text_link", "Link Text"),
        ]),
        ("Accents", [
            ("accent_primary", "Primary Accent"),
            ("accent_success", "Success"),
            ("accent_warning", "Warning"),
            ("accent_error", "Error"),
            ("accent_purple", "Purple"),
            ("accent_cyan", "Cyan"),
        ]),
        ("UI Elements", [
            ("border", "Border"),
            ("selection", "Selection"),
            ("scrollbar_thumb", "Scrollbar"),
        ]),
    ]
    
    def __init__(self, parent, theme_manager: ThemeManager, 
                 base_theme: ThemeInfo = None):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.base_theme = base_theme or theme_manager.current_theme
        self.result = None
        self.color_vars: Dict[str, tk.StringVar] = {}
        self.color_buttons: Dict[str, tk.Button] = {}
        self.base_display_to_name: Dict[str, str] = {}
        self.base_name_to_display: Dict[str, str] = {}
        
        theme = get_theme()
        
        self.title("Create Custom Theme")
        self.geometry("700x650")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        apply_window_chrome(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header, text="🎨 Create Custom Theme", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Main content with scrolling
        main = tk.Frame(self, bg=theme.bg_primary)
        main.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(main, bg=theme.bg_primary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=theme.bg_primary)
        
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw", width=680)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Theme name
        name_frame = tk.Frame(content, bg=theme.bg_primary)
        name_frame.pack(fill=tk.X, pady=15, padx=10)
        
        tk.Label(
            name_frame, text="Theme Name:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(side=tk.LEFT)
        
        self.name_var = tk.StringVar(value="My Custom Theme")
        name_entry = tk.Entry(
            name_frame, textvariable=self.name_var,
            bg=theme.bg_secondary, fg=theme.text_primary,
            insertbackground=theme.text_primary, bd=0,
            font=FONTS.body(), width=30
        )
        name_entry.pack(side=tk.LEFT, padx=10, ipady=5)
        
        # Dark mode toggle
        self.is_dark_var = tk.BooleanVar(value=self.base_theme.is_dark)
        dark_check = ttk.Checkbutton(
            name_frame, text="Dark Theme", variable=self.is_dark_var
        )
        dark_check.pack(side=tk.RIGHT)
        
        # Base theme selector
        base_frame = tk.Frame(content, bg=theme.bg_primary)
        base_frame.pack(fill=tk.X, pady=(0, 15), padx=10)
        
        tk.Label(
            base_frame, text="Base Theme:", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        ).pack(side=tk.LEFT)
        
        base_displays = []
        for name, info in self.theme_manager.built_in_themes.items():
            display = info.display_name or name
            base_displays.append(display)
            self.base_display_to_name[display] = name
            self.base_name_to_display[name] = display

        self.base_var = tk.StringVar(
            value=self.base_name_to_display.get(self.base_theme.name, self.base_theme.name)
        )
        base_combo = ttk.Combobox(
            base_frame, textvariable=self.base_var,
            values=base_displays,
            state="readonly", width=25
        )
        base_combo.pack(side=tk.LEFT, padx=10)
        base_combo.bind("<<ComboboxSelected>>", self._on_base_change)
        
        # Color sections
        for section_name, fields in self.COLOR_FIELDS:
            self._create_color_section(content, section_name, fields)
        
        # Preview section
        preview_frame = tk.LabelFrame(
            content, text="Preview", bg=theme.bg_primary,
            fg=theme.text_secondary, font=FONTS.body()
        )
        preview_frame.pack(fill=tk.X, padx=10, pady=15)
        
        self.preview_canvas = tk.Canvas(
            preview_frame, width=640, height=100,
            bg=theme.bg_secondary, highlightthickness=0
        )
        self.preview_canvas.pack(padx=10, pady=10)
        self._update_preview()
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        ModernButton(
            btn_frame, text="Reset to Base", command=self._reset_to_base
        ).pack(side=tk.LEFT)
        
        ModernButton(
            btn_frame, text="Cancel", command=self.destroy
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        ModernButton(
            btn_frame, text="Create Theme", command=self._create_theme,
            style="primary", icon="✨"
        ).pack(side=tk.RIGHT)
        
        # Initialize colors from base theme
        self._load_base_colors()
        
        self.bind("<Escape>", lambda e: self.destroy())
        self.center_window()
    
    def _create_color_section(self, parent, title: str, fields: List[Tuple[str, str]]):
        """Create a color section"""
        theme = get_theme()
        
        frame = tk.LabelFrame(
            parent, text=title, bg=theme.bg_primary,
            fg=theme.text_secondary, font=("Segoe UI", 10, "bold")
        )
        frame.pack(fill=tk.X, padx=10, pady=5)
        
        inner = tk.Frame(frame, bg=theme.bg_primary)
        inner.pack(fill=tk.X, padx=10, pady=10)
        
        row = 0
        col = 0
        
        for field_name, display_name in fields:
            # Create color variable
            var = tk.StringVar()
            self.color_vars[field_name] = var
            
            # Label
            tk.Label(
                inner, text=display_name, bg=theme.bg_primary,
                fg=theme.text_secondary, font=FONTS.small(),
                width=15, anchor="w"
            ).grid(row=row, column=col*3, sticky="w", pady=3)
            
            # Color button
            btn = tk.Button(
                inner, text="", width=3, height=1,
                command=lambda f=field_name: self._pick_color(f)
            )
            btn.grid(row=row, column=col*3+1, padx=5, pady=3)
            self.color_buttons[field_name] = btn
            
            # Hex entry
            entry = tk.Entry(
                inner, textvariable=var, width=8,
                bg=theme.bg_secondary, fg=theme.text_primary,
                insertbackground=theme.text_primary, bd=0,
                font=("Consolas", 9)
            )
            entry.grid(row=row, column=col*3+2, padx=(0, 20), pady=3)
            var.trace_add('write', lambda *args, f=field_name: self._on_color_change(f))
            
            col += 1
            if col >= 2:
                col = 0
                row += 1
    
    def _load_base_colors(self):
        """Load colors from base theme"""
        for field_name, var in self.color_vars.items():
            color = getattr(self.base_theme.colors, field_name, "#000000")
            var.set(color)
            self._update_button_color(field_name, color)
    
    def _on_base_change(self, e=None):
        """Handle base theme change"""
        base_name = self.base_display_to_name.get(self.base_var.get(), self.base_var.get())
        if base_name in self.theme_manager.built_in_themes:
            self.base_theme = self.theme_manager.built_in_themes[base_name]
            self._load_base_colors()
            self._update_preview()
    
    def _pick_color(self, field_name: str):
        """Open color picker for a field"""
        current = self.color_vars[field_name].get()
        color = colorchooser.askcolor(color=current, title=f"Choose {field_name}")
        if color[1]:
            self.color_vars[field_name].set(color[1])
    
    def _on_color_change(self, field_name: str):
        """Handle color value change"""
        color = self.color_vars[field_name].get()
        if re.match(r'^#[0-9A-Fa-f]{6}$', color):
            self._update_button_color(field_name, color)
            self._update_preview()
    
    def _update_button_color(self, field_name: str, color: str):
        """Update button background to show color"""
        if field_name in self.color_buttons:
            try:
                self.color_buttons[field_name].configure(bg=color)
            except Exception:
                pass
    
    def _update_preview(self):
        """Update the preview canvas"""
        self.preview_canvas.delete("all")
        
        # Get current colors
        bg_primary = self.color_vars.get("bg_primary", tk.StringVar()).get() or "#161b22"
        bg_secondary = self.color_vars.get("bg_secondary", tk.StringVar()).get() or "#21262d"
        text_primary = self.color_vars.get("text_primary", tk.StringVar()).get() or "#f0f6fc"
        accent = self.color_vars.get("accent_primary", tk.StringVar()).get() or "#58a6ff"
        
        # Draw preview
        self.preview_canvas.configure(bg=bg_primary)
        
        # Sidebar preview
        self.preview_canvas.create_rectangle(0, 0, 150, 100, fill=bg_secondary, outline="")
        self.preview_canvas.create_text(75, 20, text="Sidebar", fill=text_primary, font=FONTS.small())
        
        # Accent bar
        self.preview_canvas.create_rectangle(0, 40, 150, 45, fill=accent, outline="")
        
        # Main area text
        self.preview_canvas.create_text(350, 30, text="Main Content Area", fill=text_primary, font=FONTS.body())
        self.preview_canvas.create_text(350, 60, text="Preview of your theme colors", fill=text_primary, font=FONTS.small())
        
        # Accent button
        self.preview_canvas.create_rectangle(300, 75, 400, 95, fill=accent, outline="")
        self.preview_canvas.create_text(350, 85, text="Button", fill="#ffffff", font=FONTS.small())
    
    def _reset_to_base(self):
        """Reset all colors to base theme"""
        self._load_base_colors()
        self._update_preview()
    
    def _create_theme(self):
        """Create the custom theme"""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror(
                "Theme name required",
                "Enter a clear name for this custom theme.",
                parent=self
            )
            return
        
        # Generate safe name
        safe_name = re.sub(r'[^a-z0-9_]', '_', name.lower())
        
        # Collect color overrides
        overrides = {}
        invalid_fields = []
        for field_name, var in self.color_vars.items():
            color = var.get()
            if re.match(r'^#[0-9A-Fa-f]{6}$', color):
                overrides[field_name] = color
            else:
                invalid_fields.append(field_name)

        if invalid_fields:
            messagebox.showerror(
                "Invalid colors",
                "Use six-digit hex colors like #58a6ff before creating the theme.",
                parent=self
            )
            return
        
        # Create the theme
        try:
            new_theme = self.theme_manager.create_custom_theme(
                name=safe_name,
                display_name=name,
                base_theme=self.base_display_to_name.get(self.base_var.get(), self.base_var.get()),
                color_overrides=overrides
            )
            
            self.result = new_theme
            messagebox.showinfo(
                "Theme created",
                f"Created '{name}'. You can select it from Theme Settings.",
                parent=self
            )
            self.destroy()
        except Exception as e:
            messagebox.showerror(
                "Theme not created",
                f"Could not create this theme:\n\n{e}",
                parent=self
            )
    
    def center_window(self):
        """Center the dialog"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')


# =============================================================================
# Theme Selector Dialog
# =============================================================================
class ThemeSelectorDialog(tk.Toplevel, ThemedWidget):
    """
        Dialog for browsing and selecting themes.
        
        Displays all available themes with previews and allows
        switching or customizing themes.
        
        Features:
            - Theme list with previews
            - Dark/light mode indicator
            - Custom theme creation
            - Theme import/export
            - Live preview
        """
    
    def __init__(self, parent, theme_manager: ThemeManager):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.result = None
        theme = get_theme()
        
        self.title("Theme Settings")
        self.geometry("540x640")
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        self.grab_set()
        
        apply_window_chrome(self)
        
        # Header
        header = tk.Frame(self, bg=theme.bg_dark, padx=22, pady=18)
        header.pack(fill=tk.X)
        
        tk.Label(
            header, text="Theme settings", bg=theme.bg_dark,
            fg=theme.text_primary, font=FONTS.title(bold=True)
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Choose a built-in theme or create a custom look that fits your workspace.",
            bg=theme.bg_dark, fg=theme.text_secondary,
            font=FONTS.small(), wraplength=480, justify=tk.LEFT
        ).pack(anchor="w", pady=(5, 0))
        
        # Main content
        content = tk.Frame(self, bg=theme.bg_primary)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # Current theme label
        tk.Label(
            content, text="Theme library", bg=theme.bg_primary,
            fg=theme.text_primary, font=FONTS.body(bold=True)
        ).pack(anchor="w", pady=(0, 10))
        
        # Theme list with canvas for scrolling
        list_frame = tk.Frame(content, bg=theme.bg_secondary)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(list_frame, bg=theme.bg_secondary, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.themes_inner = tk.Frame(canvas, bg=theme.bg_secondary)
        
        self.themes_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.themes_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Populate themes
        self._populate_themes()
        
        # Buttons
        btn_frame = tk.Frame(self, bg=theme.bg_primary)
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        ModernButton(
            btn_frame, text="Import Theme", command=self._import_theme,
            icon="📥"
        ).pack(side=tk.LEFT, padx=(0, 10))

        ModernButton(
            btn_frame, text="Create Custom", command=self._create_custom_theme,
            icon="✨"
        ).pack(side=tk.LEFT)
        
        ModernButton(
            btn_frame, text="Close", command=self.destroy
        ).pack(side=tk.RIGHT)
        
        self.center_window()
    
    def _populate_themes(self):
        """Populate the theme list"""
        theme = get_theme()
        current_name = self.theme_manager.current_theme.name
        
        for widget in self.themes_inner.winfo_children():
            widget.destroy()
        
        all_themes = self.theme_manager.get_all_themes()
        
        for name, theme_info in all_themes.items():
            is_selected = name == current_name
            
            item_frame = tk.Frame(
                self.themes_inner,
                bg=theme.bg_tertiary if is_selected else theme.bg_secondary
            )
            item_frame.pack(fill=tk.X, padx=5, pady=3)
            
            # Color preview
            preview_frame = tk.Frame(item_frame, bg=theme.bg_secondary, width=60, height=40)
            preview_frame.pack(side=tk.LEFT, padx=10, pady=10)
            preview_frame.pack_propagate(False)
            
            # Show theme colors
            colors_preview = tk.Frame(preview_frame, bg=theme_info.colors.bg_primary)
            colors_preview.pack(fill=tk.BOTH, expand=True)
            
            accent_bar = tk.Frame(colors_preview, bg=theme_info.colors.accent_primary, height=8)
            accent_bar.pack(side=tk.BOTTOM, fill=tk.X)
            
            # Theme info
            info_frame = tk.Frame(item_frame, bg=item_frame.cget('bg'))
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=10)
            
            name_text = theme_info.display_name
            if is_selected:
                name_text += " ✓"
            
            tk.Label(
                info_frame, text=name_text,
                bg=info_frame.cget('bg'),
                fg=theme.text_primary if not is_selected else theme.accent_primary,
                font=("Segoe UI", 10, "bold" if is_selected else "normal")
            ).pack(anchor="w")
            
            mode_text = "🌙 Dark" if theme_info.is_dark else "☀️ Light"
            tk.Label(
                info_frame, text=f"{mode_text} • {theme_info.author}",
                bg=info_frame.cget('bg'),
                fg=theme.text_secondary,
                font=FONTS.small()
            ).pack(anchor="w")
            
            # Select button
            if not is_selected:
                select_btn = ModernButton(
                    item_frame, text="Select", command=lambda n=name: self._select_theme(n),
                    style="primary", padx=12, pady=5, font=FONTS.small()
                )
                select_btn.pack(side=tk.RIGHT, padx=10)
            
            # Hover effect
            def on_enter(e, f=item_frame):
                if f.cget('bg') != theme.bg_tertiary:
                    f.configure(bg=theme.bg_hover)
                    for child in f.winfo_children():
                        if isinstance(child, ModernButton):
                            continue
                        if isinstance(child, tk.Frame):
                            for subchild in child.winfo_children():
                                if isinstance(subchild, tk.Label):
                                    subchild.configure(bg=theme.bg_hover)
            
            def on_leave(e, f=item_frame, sel=is_selected):
                bg = theme.bg_tertiary if sel else theme.bg_secondary
                f.configure(bg=bg)
                for child in f.winfo_children():
                    if isinstance(child, ModernButton):
                        continue
                    if isinstance(child, tk.Frame):
                        for subchild in child.winfo_children():
                            if isinstance(subchild, tk.Label):
                                subchild.configure(bg=bg)
            
            item_frame.bind("<Enter>", on_enter)
            item_frame.bind("<Leave>", on_leave)
    
    def _select_theme(self, theme_name: str):
        """Select a theme"""
        if self.theme_manager.set_theme(theme_name):
            self.result = theme_name
            self.destroy()
    
    def _import_theme(self):
        """Import a theme from file"""
        filepath = filedialog.askopenfilename(
            title="Import Theme",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            theme = self.theme_manager.import_theme(filepath)
            if theme:
                messagebox.showinfo(
                    "Theme Imported",
                    f"Imported {theme.display_name}. You can select it from the theme library.",
                    parent=self
                )
                self._populate_themes()
            else:
                messagebox.showerror(
                    "Theme Import Failed",
                    "The selected file could not be imported as a theme. Check that it is a valid theme JSON file.",
                    parent=self
                )

    def _create_custom_theme(self):
        """Open the custom theme creator and refresh the theme list when it closes."""
        dialog = ThemeCreatorDialog(self, self.theme_manager)
        self.wait_window(dialog)
        self._populate_themes()
    
    def center_window(self):
        """Center the dialog"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')
