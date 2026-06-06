# Updater Bootstrap

Bookmark Organizer Pro uses a disabled-by-default tufup policy for update
readiness. The current implementation can configure repositories and check
trusted metadata, but it does not download or apply updates.

## Client Files

- Policy: `update_config.json` under the app data directory.
- Trusted root: `updates/metadata/root.json` under the app data directory.
- Target cache: `updates/targets/` under the app data directory.

The trusted root must be installed before `updates check` can construct the
tufup client. Treat `root.json` as a trust anchor: ship it with a signed
installer or place it through a documented manual bootstrap step.

## Optional Dependency

Install the updater extra only where update checks are required:

```powershell
py -3.12 -m pip install "bookmark-organizer-pro[updates]"
```

The project depends on tufup rather than pinning tuf directly because tufup
0.10.0 pins its compatible tuf runtime internally.

## Configure A Repository

```powershell
python main.py updates configure --enable --metadata-url https://updates.example.com/metadata --targets-url https://updates.example.com/targets
python main.py updates status
python main.py updates check
```

Repository URLs must use HTTPS. Checks remain opt-in and disabled until
`--enable` is set.

## Target Naming

tufup target filenames must not contain whitespace. Use the app target name and
PEP 440 version:

- Full archive: `BookmarkOrganizerPro-6.6.11.tar.gz`
- Patch: `BookmarkOrganizerPro-6.6.11.patch`

The client adapter uses `BookmarkOrganizerPro` as the tufup app name.

## Repository Owner Checklist

1. Build the PyInstaller or Nuitka bundle in a dedicated release directory.
2. Create tufup archives and patches with the tufup repository tooling.
3. Sign TUF metadata with the repository keys.
4. Publish metadata and targets to separate HTTPS paths.
5. Ship or document trusted-root placement for clients.
6. Verify `updates status` reports `Trusted root: present`.
7. Verify `updates check` reports either no update or a newer target.

## Safety Gates

- Updates are disabled by default.
- Repository URLs must use HTTPS.
- `updates check` requires local trusted root metadata.
- `updates check` does not download or apply target files.
- `updates download` and `updates apply` are explicit refusal gates in this
  release. They must stay gated until download, extraction, install directory
  isolation, rollback, and user confirmation are covered by tests.
