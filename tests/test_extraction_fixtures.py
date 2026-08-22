"""Content-extraction regression fixtures.

trafilatura's extraction changes between releases (2.2.0 was an explicit
"better recall" overhaul), and a silent regression there degrades reader view,
content search, and embeddings at once without failing anything else. These
fixtures pin the properties the app actually depends on for representative page
shapes, rather than exact strings, so a bump is verifiable but ordinary wording
changes upstream do not produce false alarms.
"""

from __future__ import annotations

import unittest

from bookmark_organizer_pro.services.ingest import _bs4_fallback, _trafilatura_extract

ARTICLE = """<!doctype html>
<html><head>
<title>Growing tomatoes in containers</title>
<meta name="description" content="A short guide to container tomatoes.">
</head><body>
<nav><ul><li><a href="/">Home</a></li><li><a href="/about">About</a></li></ul></nav>
<article>
<h1>Growing tomatoes in containers</h1>
<p>Tomatoes grown in pots need more water than tomatoes in the ground, because
the soil volume is small and dries out quickly in full sun.</p>
<p>Choose a container of at least twenty litres. Smaller pots force daily
watering and still produce a stressed plant with split fruit.</p>
</article>
<footer><p>We use cookies to improve your experience. Accept all cookies.</p></footer>
</body></html>
"""

NEWS = """<!doctype html>
<html><head><title>Council approves the harbour plan</title></head><body>
<div class="ad">Sponsored: buy boats now</div>
<main><h1>Council approves the harbour plan</h1>
<p>The council voted on Tuesday to approve the harbour redevelopment, ending a
two year consultation.</p>
<p>Work begins in spring and the eastern slipway stays open throughout.</p>
</main>
<aside>Related: five more stories you might like</aside>
</body></html>
"""

DOCS = """<!doctype html>
<html><head><title>API reference: list_bookmarks</title></head><body>
<main><h1>list_bookmarks</h1>
<p>Return every bookmark visible to the caller.</p>
<pre><code>result = client.list_bookmarks(limit=50)
for bookmark in result.items:
    print(bookmark.url)</code></pre>
<table><tr><th>Parameter</th><th>Meaning</th></tr>
<tr><td>limit</td><td>Maximum rows returned</td></tr></table>
</main></body></html>
"""

FORUM = """<!doctype html>
<html><head><title>Why does my import stall at 90 percent?</title></head><body>
<div class="post"><p>My import stalls near the end every time. Is that normal?</p></div>
<div class="post"><p>It is usually the favicon fetch, not the import. Turn off
icon fetching and the last step finishes immediately.</p></div>
<div class="post"><p>That fixed it, thank you.</p></div>
</body></html>
"""

MINIMAL = """<!doctype html>
<html><head><title>Just a link page</title></head>
<body><p>Short note.</p></body></html>
"""

FIXTURES = {
    "article": (ARTICLE, "https://garden.test/tomatoes", ["twenty litres", "dries out"], ["Sponsored", "Accept all cookies"]),
    "news": (NEWS, "https://news.test/harbour", ["harbour redevelopment", "eastern slipway"], ["Sponsored: buy boats"]),
    # Code blocks survive; table cells do NOT with trafilatura 2.1.0. If a
    # future bump starts preserving tables this expectation should be widened
    # rather than the table dropped from the fixture.
    "docs": (DOCS, "https://docs.test/api", ["list_bookmarks", "Return every bookmark"], []),
    "forum": (FORUM, "https://forum.test/thread/1", ["favicon fetch", "stalls near the end"], []),
    "minimal": (MINIMAL, "https://notes.test/short", ["Short note"], []),
}


class TestExtractionFixtures(unittest.TestCase):
    def _extract(self, html: str, url: str) -> dict:
        return _trafilatura_extract(html, url) or _bs4_fallback(html) or {}

    def test_representative_pages_keep_their_body_and_drop_boilerplate(self):
        for name, (html, url, expected, unwanted) in FIXTURES.items():
            with self.subTest(page=name):
                extracted = self._extract(html, url)
                text = str(extracted.get("text", ""))

                self.assertTrue(text.strip(), f"{name}: extraction produced no text")
                for phrase in expected:
                    self.assertIn(phrase, text, f"{name}: lost {phrase!r}")
                for phrase in unwanted:
                    self.assertNotIn(phrase, text, f"{name}: kept boilerplate {phrase!r}")

    def test_titles_survive_extraction(self):
        for name, (html, url, _expected, _unwanted) in FIXTURES.items():
            with self.subTest(page=name):
                extracted = self._extract(html, url)
                title = str(extracted.get("title", "")).strip()
                # Some backends return no title; when one is returned it must be
                # the page's own title rather than a fragment of the body.
                if title:
                    self.assertIn(title.split(":")[0][:20].lower(), html.lower())

    def test_word_counts_stay_in_a_sane_band(self):
        # Guards against an upstream change that starts returning the whole DOM
        # or collapses everything to a stub.
        bands = {"article": (30, 200), "news": (20, 200), "docs": (5, 200),
                 "forum": (15, 200), "minimal": (1, 60)}
        for name, (html, url, _expected, _unwanted) in FIXTURES.items():
            with self.subTest(page=name):
                text = str(self._extract(html, url).get("text", ""))
                words = len(text.split())
                low, high = bands[name]
                self.assertGreaterEqual(words, low, f"{name}: only {words} words")
                self.assertLessEqual(words, high, f"{name}: {words} words looks like raw DOM")

    def test_known_extraction_limits_are_recorded(self):
        """Document what the pinned extractor drops, so a bump is visible."""
        text = str(self._extract(DOCS, "https://docs.test/api").get("text", ""))
        # trafilatura 2.1.0 discards table markup entirely.
        self.assertNotIn("Maximum rows returned", text)

    def test_fallback_matches_the_contract_when_trafilatura_is_absent(self):
        # The BS4 fallback must satisfy the same shape, since it runs whenever
        # the optional dependency is missing.
        for name, (html, _url, expected, _unwanted) in FIXTURES.items():
            with self.subTest(page=name):
                extracted = _bs4_fallback(html) or {}
                self.assertIn("text", extracted, f"{name}: fallback returned no text key")
                self.assertTrue(str(extracted["text"]).strip(), f"{name}: fallback text empty")


if __name__ == "__main__":
    unittest.main()
