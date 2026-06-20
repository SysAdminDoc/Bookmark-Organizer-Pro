# Blocked Roadmap Items

Items moved here from ROADMAP.md because they have hard blockers preventing implementation.

## R-41 — tufup auto-update (apply stage)

**Blocker:** Applying downloaded updates requires design decisions about install isolation, rollback safety, user confirmation UI, and binary replacement of a running process. The non-mutating infrastructure (policy, check, download, staging, preflight, cleanup, planning) is complete through v6.6.27. The `apply_preflight()` method deliberately returns "update application is disabled in this release" as a blocker. Unblocking requires:

1. Safe binary extraction and replacement strategy (especially for running executables on Windows)
2. Rollback mechanism that can restore the previous version if the new one fails to start
3. User confirmation UI in the desktop app
4. End-to-end testing with real tufup repositories

**Source:** [S-28][S-88]

## R-02 — Web client (FastAPI + HTMX + PWA)

**Blocker:** XL effort (1-2 weeks). Requires designing a full FastAPI application with HTMX templates, authentication, PWA manifest, and service worker. While SQLite (R-31) is complete, the web client needs its own architecture, routing, template system, and security model. No partial implementation exists.

**Source:** [S-3][S-5][S-6][S-8][S-12]

## R-03 — Mobile PWA share-intent

**Blocker:** Depends on R-02 (web client). Android share-intent requires a served PWA with a Web Share Target API manifest entry. Cannot be implemented without the web client.

**Source:** [S-8][S-12]

## Publish browser extension to Chrome Web Store and Firefox AMO

**Blocker:** Requires $5 Chrome Web Store developer account, Mozilla AMO developer account, store listing screenshots, and a privacy policy URL. These are operator-gated actions that cannot be automated without credentials and human review.

**Source:** [S-5][S-3][S-8] (Karakeep CWS+AMO+Safari; Linkwarden CWS+AMO; Wallabag CWS+AMO)

## Extension native messaging for server-free save

**Blocker:** Depends on the browser extension being published to stores (or at minimum, stable enough for native messaging registration). Native messaging also requires platform-specific manifest registration (Windows registry keys, macOS/Linux JSON manifests) that varies by browser. Implementation is feasible but should follow store publication.

**Source:** S-67 (MDN native messaging), S-97 (Universal Bookmark Manager), S-110 (Zotero connectors)

## MSIX packaging + SignPath Foundation code signing

**Blocker:** Requires operator to apply to SignPath Foundation for free OV code signing (signpath.org), create a Microsoft Partner Center developer account ($19 one-time fee), generate AppxManifest.xml with app identity, and set up MSIX build pipeline. These are account-gated actions.

**Source:** S-121 (research pass), signpath.org, 82phil.github.io MSIX guide
