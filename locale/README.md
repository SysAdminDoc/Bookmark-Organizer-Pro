# Translations

Bookmark Organizer Pro uses Python's `gettext` for internationalization.

## For translators

1. Copy `bop.pot` to `<lang>/LC_MESSAGES/bop.po` (e.g. `de/LC_MESSAGES/bop.po`)
2. Fill in `msgstr` entries
3. Compile with `msgfmt bop.po -o bop.mo`

## Regenerating the template

```bash
python -m bookmark_organizer_pro.i18n
```

This scans all `.py` files for `_("...")` calls and overwrites `locale/bop.pot`.

## Directory structure

```
locale/
├── bop.pot              # Template (auto-generated)
├── README.md            # This file
└── <lang>/
    └── LC_MESSAGES/
        ├── bop.po       # Translation source
        └── bop.mo       # Compiled binary (from msgfmt)
```
