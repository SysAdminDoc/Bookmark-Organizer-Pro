"""Shared test contracts."""

SEARCH_CONFORMANCE_CASES = (
    ("unknown:value", "unknown_field"),
    ("after:not-a-date", "invalid_date"),
    ("visits:=>5", "invalid_visits_filter"),
    ("tag:", "empty_filter"),
    ('"unclosed phrase', "unclosed_quote"),
    ("python OR", "trailing_operator"),
    ("/python/", "legacy_regex_syntax"),
)


class SharedExtensionRegistryGuard:
    """Fail a case that writes the real approved-extension-origin registry.

    `BookmarkAPI` defaults `extension_origins_file` to the user's data
    directory, so a case that omits it pairs a fake extension id into their own
    registry and leaks that state into every later test. Both API test classes
    need this, and keeping one copy means the message and the check cannot
    drift apart.
    """

    def setUp(self):
        super().setUp()
        from bookmark_organizer_pro.services.api import _EXTENSION_ORIGINS_FILE

        self._shared_registry = _EXTENSION_ORIGINS_FILE
        self._registry_before = (
            _EXTENSION_ORIGINS_FILE.read_bytes()
            if _EXTENSION_ORIGINS_FILE.exists()
            else None
        )
        self.addCleanup(self._assert_shared_registry_untouched)

    def _assert_shared_registry_untouched(self):
        after = (
            self._shared_registry.read_bytes()
            if self._shared_registry.exists()
            else None
        )
        self.assertEqual(
            self._registry_before, after,
            "this test wrote the shared extension-origin registry; pass "
            "extension_origins_file=... when constructing BookmarkAPI",
        )
