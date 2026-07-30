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
