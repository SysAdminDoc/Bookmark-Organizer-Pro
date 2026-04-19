# Architecture Notes

Bookmark Organizer Pro is currently a Tkinter desktop application with a modular
backend package and a legacy-large UI entry point.

## Current Boundaries

| Area | Location | Notes |
| --- | --- | --- |
| Desktop shell | `main.py` | Tkinter app composition, dialogs, view classes, and application startup. |
| Backend package | `bookmark_organizer_pro/` | Models, storage, import/export, search, AI providers, URL utilities, and shared helpers. |
| UI support modules | `bookmark_organizer_pro/ui/` | Design tokens, theme primitives, density settings, reusable view-model builders, report helpers, and first-run dependency UI. |
| Dependency helpers | `bookmark_organizer_pro/utils/dependencies.py` | Required/optional package discovery and guarded pip installation for first-run setup. |
| Runtime helpers | `bookmark_organizer_pro/utils/runtime.py` | Atomic JSON writes, CSV safety, URL opening guardrails, resource cleanup, environment validation, and timeout helpers. |
| Packaging | `packaging/` | PyInstaller spec and Windows version metadata. |
| Local scripts | `scripts/` | Build wrappers and workspace cleanup helpers. |

## Refactor Direction

The next maintainability win is to continue shrinking `main.py` without changing
behavior. Good extraction candidates are:

1. Generic Tk widgets such as tooltip, modern button/search, empty states, toast,
   and progress components.
2. Feature-specific dialogs such as bookmark editor, theme creator, analytics,
   selective export, and category management.
3. Long-running service classes such as backup scheduler, archiver, favicon
   manager, duplicate detector, and AI batch processors.

Each extraction should preserve the current public behavior, keep imports one
way from `main.py` into package modules, and add focused tests when logic moves
out of UI-only code.
