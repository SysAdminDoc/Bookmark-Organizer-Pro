"""Web archive, screenshot, summarization, and PDF services."""

from __future__ import annotations

import html as html_module
import mimetypes
import re
import time
import urllib.parse
import uuid
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from bookmark_organizer_pro.ai import AIConfigManager, create_ai_client
from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.egress import public_egress as requests
from bookmark_organizer_pro.url_utils import URLUtilities
from bookmark_organizer_pro.utils import sanitize_filename, truncate_string

_SCRIPT_RE = re.compile(r"<script[\s>].*?</script\s*>", re.DOTALL | re.IGNORECASE)
_EVENT_HANDLER_QUOTED_RE = re.compile(r"\s+on[a-z]+\s*=\s*[\"'][^\"']*[\"']", re.IGNORECASE)
_EVENT_HANDLER_UNQUOTED_RE = re.compile(r"\s+on[a-z]+\s*=\s*[^\s>]+", re.IGNORECASE)
_JS_URI_RE = re.compile(r"""(?:href|src|action)\s*=\s*["']?\s*javascript\s*:""", re.IGNORECASE)


def _strip_dangerous_html(html_text: str) -> str:
    """Remove <script> tags, inline event handlers, and javascript: URIs from HTML."""
    html_text = _SCRIPT_RE.sub("", html_text)
    html_text = _EVENT_HANDLER_QUOTED_RE.sub("", html_text)
    html_text = _EVENT_HANDLER_UNQUOTED_RE.sub("", html_text)
    html_text = _JS_URI_RE.sub('href="about:blank"', html_text)
    return html_text


class WaybackMachine:
    """Integration with Internet Archive's Wayback Machine"""
    
    SAVE_URL = "https://web.archive.org/save/"
    AVAILABILITY_URL = "https://archive.org/wayback/available"
    CDX_URL = "https://web.archive.org/cdx/search/cdx"
    
    @staticmethod
    def save_page(url: str) -> Tuple[bool, str]:
        """
        Save a page to the Wayback Machine.
        Returns (success, archived_url or error_message)
        """
        if not URLUtilities._is_safe_url(url):
            return False, "Private or unsupported URLs are not sent to the Wayback Machine"

        response = None
        try:
            response = requests.get(
                WaybackMachine.SAVE_URL + url,
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=30
            )
            
            if response.status_code == 200:
                # Check for the archived URL in headers
                archived_url = response.headers.get('Content-Location', '')
                if archived_url:
                    return True, f"https://web.archive.org{archived_url}"
                
                # Try to extract from response
                if 'web.archive.org' in response.url:
                    return True, response.url
                
                return True, f"https://web.archive.org/web/{url}"
            else:
                return False, f"Failed with status {response.status_code}"
        except requests.exceptions.Timeout:
            return False, "Request timed out"
        except Exception as e:
            return False, str(e)
        finally:
            if response is not None:
                response.close()
    
    @staticmethod
    def check_availability(url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if a URL is available in the Wayback Machine.
        Returns (is_available, archived_url, timestamp)
        """
        if not URLUtilities._is_safe_url(url):
            return False, None, None

        response = None
        try:
            response = requests.get(
                WaybackMachine.AVAILABILITY_URL,
                params={'url': url},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                snapshots = data.get('archived_snapshots', {})
                closest = snapshots.get('closest', {})
                
                if closest.get('available'):
                    return True, closest.get('url'), closest.get('timestamp')
            
            return False, None, None
        except Exception:
            return False, None, None
        finally:
            if response is not None:
                response.close()
    
    @staticmethod
    def get_snapshots(url: str, limit: int = 10) -> List[Dict[str, str]]:
        """Get list of available snapshots for a URL"""
        if not URLUtilities._is_safe_url(url):
            return []

        try:
            limit = max(1, min(100, int(limit)))
        except (TypeError, ValueError):
            limit = 10

        response = None
        try:
            response = requests.get(
                WaybackMachine.CDX_URL,
                params={
                    'url': url,
                    'output': 'json',
                    'limit': limit,
                    'fl': 'timestamp,original,statuscode'
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if len(data) > 1:  # First row is headers
                    snapshots = []
                    for row in data[1:]:
                        timestamp, original, status = row
                        snapshots.append({
                            'timestamp': timestamp,
                            'url': f"https://web.archive.org/web/{timestamp}/{original}",
                            'status': status,
                            'date': datetime.strptime(timestamp[:8], '%Y%m%d').strftime('%Y-%m-%d')
                        })
                    return snapshots
            return []
        except Exception:
            return []
        finally:
            if response is not None:
                response.close()


class LocalArchiver:
    """Archive pages locally as HTML or MHTML"""
    
    ARCHIVE_DIR = DATA_DIR / "archives"
    MAX_ARCHIVE_BYTES = 5_000_000
    MAX_RESOURCE_BYTES = 1_000_000
    MAX_MHTML_RESOURCES = 32
    
    def __init__(self):
        self.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    def _read_text_response(self, response) -> Tuple[bool, str]:
        """Read a bounded text/html response body."""
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type and not (
            content_type.startswith("text/")
            or content_type == "application/xhtml+xml"
        ):
            return False, "Only text or HTML pages can be archived"

        try:
            content_length = int(response.headers.get("content-length", 0) or 0)
        except (TypeError, ValueError):
            content_length = 0
        if content_length > self.MAX_ARCHIVE_BYTES:
            return False, "Page is too large to archive safely"

        chunks = bytearray()
        for chunk in response.iter_content(chunk_size=16384):
            if not chunk:
                continue
            chunks.extend(chunk)
            if len(chunks) > self.MAX_ARCHIVE_BYTES:
                return False, "Page is too large to archive safely"

        encoding = response.encoding or "utf-8"
        return True, bytes(chunks).decode(encoding, errors="replace")

    def _read_resource_response(self, response, remaining: int) -> Tuple[bool, bytes | str]:
        """Read one bounded MHTML resource without exceeding the archive budget."""
        limit = min(self.MAX_RESOURCE_BYTES, max(0, remaining))
        try:
            declared = int(response.headers.get("content-length", 0) or 0)
        except (TypeError, ValueError):
            declared = 0
        if declared > limit:
            return False, "Referenced resource exceeds the archive limit"
        chunks = bytearray()
        for chunk in response.iter_content(chunk_size=16384):
            if not chunk:
                continue
            chunks.extend(chunk)
            if len(chunks) > limit:
                return False, "Referenced resource exceeds the archive limit"
        return True, bytes(chunks)

    def _build_mhtml(self, page_text: str, source_url: str) -> bytes:
        """Build an RFC 2557 multipart/related archive with bounded public resources."""
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise RuntimeError("BeautifulSoup is required for MHTML archives") from exc

        soup = BeautifulSoup(_strip_dangerous_html(page_text), "html.parser")
        for element in soup.find_all(("script", "iframe", "object", "embed", "form")):
            element.decompose()
        for element in soup.find_all("base"):
            element.decompose()
        for element in soup.find_all("meta"):
            if str(element.get("http-equiv") or "").strip().lower() == "refresh":
                element.decompose()

        resources: list[tuple[str, str, bytes, str]] = []
        fetched: dict[str, str] = {}
        total = len(str(soup).encode("utf-8"))

        def fetch_resource(raw_url: str) -> str | None:
            nonlocal total
            absolute = urllib.parse.urljoin(source_url, raw_url)
            if absolute in fetched:
                return fetched[absolute]
            if len(resources) >= self.MAX_MHTML_RESOURCES or not URLUtilities._is_safe_url(absolute):
                return None
            response = requests.get(
                absolute,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
                allow_redirects=False,
                stream=True,
            )
            try:
                if response.status_code != 200:
                    return None
                ok, payload = self._read_resource_response(response, self.MAX_ARCHIVE_BYTES - total)
                if not ok or not isinstance(payload, bytes):
                    return None
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if not content_type:
                    content_type = mimetypes.guess_type(urllib.parse.urlsplit(absolute).path)[0] or "application/octet-stream"
                if not content_type.startswith(("text/css", "image/", "font/", "application/font", "application/vnd.ms-font")):
                    return None
                cid = f"resource-{uuid.uuid4().hex}@bookmark-organizer"
                resources.append((absolute, cid, payload, content_type))
                fetched[absolute] = cid
                total += len(payload)
                return cid
            finally:
                response.close()

        for element, attribute in [
            *((node, "href") for node in soup.find_all("link", rel=lambda value: value and "stylesheet" in value)),
            *((node, "src") for node in soup.find_all(("img", "source"))),
            *((node, "poster") for node in soup.find_all("video")),
        ]:
            raw_url = element.get(attribute)
            if not raw_url or str(raw_url).lower().startswith("data:"):
                continue
            cid = fetch_resource(str(raw_url))
            if cid:
                element[attribute] = f"cid:{cid}"
            else:
                element.attrs.pop(attribute, None)

        for element in soup.find_all(srcset=True):
            rewritten_candidates = []
            for candidate in str(element.get("srcset") or "").split(","):
                parts = candidate.strip().split()
                if not parts:
                    continue
                cid = fetch_resource(parts[0])
                if cid:
                    descriptor = f" {' '.join(parts[1:])}" if len(parts) > 1 else ""
                    rewritten_candidates.append(f"cid:{cid}{descriptor}")
            if rewritten_candidates:
                element["srcset"] = ", ".join(rewritten_candidates)
            else:
                element.attrs.pop("srcset", None)

        css_url_re = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
        css_import_re = re.compile(
            r"@import\s+(?:url\(\s*)?(['\"]?)(?!data:|cid:)(.*?)\1\s*\)?\s*;",
            re.IGNORECASE,
        )

        def rewrite_css(css: str, base_url: str) -> str:
            def replace_css_url(match):
                raw_target = match.group(2).strip()
                if raw_target.lower().startswith(("data:", "cid:")):
                    return match.group(0)
                target = urllib.parse.urljoin(base_url, raw_target)
                cid = fetch_resource(target)
                return f"url('cid:{cid}')" if cid else "url('')"

            def replace_css_import(match):
                target = urllib.parse.urljoin(base_url, match.group(2))
                cid = fetch_resource(target)
                return f"@import url('cid:{cid}');" if cid else ""

            return css_url_re.sub(replace_css_url, css_import_re.sub(replace_css_import, css))

        for style in soup.find_all("style"):
            css = style.string or style.get_text()
            style.string = rewrite_css(css, source_url)
        for element in soup.find_all(style=True):
            element["style"] = rewrite_css(str(element.get("style") or ""), source_url)

        # Rewrite fonts/images referenced by downloaded stylesheets before MIME assembly.
        index = 0
        while index < len(resources):
            location, cid, payload, content_type = resources[index]
            if content_type != "text/css":
                index += 1
                continue
            css_text = payload.decode("utf-8", errors="replace")
            rewritten = rewrite_css(css_text, location).encode("utf-8")
            resources[index] = (location, cid, rewritten, content_type)
            index += 1

        root = EmailMessage()
        root["Subject"] = "Bookmark Organizer offline archive"
        root["MIME-Version"] = "1.0"
        root["Snapshot-Content-Location"] = source_url
        root.make_related()
        html_part = EmailMessage()
        html_part.set_content(str(soup), subtype="html", charset="utf-8")
        html_part["Content-Location"] = source_url
        root.attach(html_part)
        for location, cid, payload, content_type in resources:
            maintype, subtype = content_type.split("/", 1)
            part = EmailMessage()
            part.set_content(payload, maintype=maintype, subtype=subtype, cte="base64")
            part["Content-ID"] = f"<{cid}>"
            part["Content-Location"] = location
            root.attach(part)
        rendered = root.as_bytes()
        if len(rendered) > self.MAX_ARCHIVE_BYTES:
            raise ValueError("MHTML archive exceeds the 5 MB limit")
        return rendered
    
    def archive_page(self, bookmark: Bookmark, 
                     format: str = "html") -> Tuple[bool, str]:
        """
        Archive a page locally.
        format: 'html' or 'mhtml'
        Returns (success, filepath or error)
        """
        try:
            format = str(format or "html").strip().lower()
            if format not in {"html", "mhtml"}:
                return False, "Unsupported archive format"
            if not URLUtilities._is_safe_url(bookmark.url):
                return False, "Private or unsupported URLs cannot be archived"

            response = requests.get(
                bookmark.url,
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=30,
                allow_redirects=False,
                stream=True
            )
            try:
                if response.status_code != 200:
                    return False, f"Failed to fetch: {response.status_code}"
                ok, page_text = self._read_text_response(response)
                if not ok:
                    return False, page_text
            finally:
                response.close()

            # Create safe filename
            safe_title = sanitize_filename(bookmark.title or "bookmark")[:50] or "bookmark"
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{safe_title}_{timestamp}.{format}"
            filepath = self.ARCHIVE_DIR / filename
            
            if format == "html":
                safe_url = html_module.escape(bookmark.url, quote=True)
                safe_title_html = html_module.escape(bookmark.title, quote=True)
                sanitized_body = _strip_dangerous_html(page_text)
                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy" content="script-src 'none'; object-src 'none';">
    <meta name="archived-from" content="{safe_url}">
    <meta name="archived-date" content="{datetime.now().isoformat()}">
    <meta name="original-title" content="{safe_title_html}">
    <title>{safe_title_html} (Archived)</title>
    <style>
        .archive-banner {{
            background: #1a1a2e;
            color: #eee;
            padding: 10px 20px;
            font-family: Arial, sans-serif;
            font-size: 12px;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 99999;
        }}
        .archive-banner a {{ color: #58a6ff; }}
        body {{ margin-top: 40px !important; }}
    </style>
</head>
<body>
    <div class="archive-banner">
        📦 Archived from <a href="{safe_url}">{safe_url}</a>
        on {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>
    {sanitized_body}
</body>
</html>"""
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(html_content)
            
            else:
                filepath.write_bytes(self._build_mhtml(page_text, bookmark.url))
            
            # Update bookmark with archive path
            bookmark.custom_data["local_archive_path"] = str(filepath)
            bookmark.modified_at = datetime.now().isoformat()
            setattr(bookmark, "local_archive_path", str(filepath))
            
            return True, str(filepath)
        
        except Exception as e:
            return False, str(e)
    
    def get_archived_pages(self) -> List[Dict[str, str]]:
        """Get list of all archived pages"""
        archives = []

        for pattern in ("*.html", "*.mhtml"):
            for file in self.ARCHIVE_DIR.glob(pattern):
                try:
                    stat = file.stat()
                except OSError:
                    continue
                archives.append({
                    'filename': file.name,
                    'path': str(file),
                    'size': stat.st_size,
                    'date': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        
        return sorted(archives, key=lambda x: x['date'], reverse=True)
    
    def get_archive_size(self) -> Tuple[int, int]:
        """Get total archive size (file_count, bytes)"""
        total_size = 0
        file_count = 0
        for file in self.ARCHIVE_DIR.glob("*"):
            if not file.is_file():
                continue
            try:
                total_size += file.stat().st_size
                file_count += 1
            except OSError:
                continue
        return file_count, total_size
    
    def delete_archive(self, filepath: str) -> bool:
        """Delete an archived page"""
        try:
            archive_root = self.ARCHIVE_DIR.resolve()
            target = Path(filepath).resolve()
            target.relative_to(archive_root)
            if target.suffix.lower() not in {".html", ".mhtml"}:
                return False
            target.unlink()
            return True
        except (OSError, ValueError):
            return False


class AISummarizer:
    """Generate AI summaries for bookmark pages"""
    MAX_FETCH_BYTES = 2_000_000
    MAX_PARSE_BYTES = 100_000
    _MAX_CACHE = 1024

    def __init__(self, ai_config: AIConfigManager):
        self.ai_config = ai_config
        self._cache: Dict[str, str] = {}

    def _read_summary_html(self, response) -> Optional[str]:
        """Read a bounded HTML-ish response for summarization."""
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type and content_type not in {"text/html", "application/xhtml+xml"}:
            return None
        try:
            content_length = int(response.headers.get("content-length", 0) or 0)
        except (TypeError, ValueError):
            content_length = 0
        if content_length > self.MAX_FETCH_BYTES:
            return None

        chunks = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            chunks.extend(chunk)
            if len(chunks) >= self.MAX_PARSE_BYTES:
                break
        return bytes(chunks[:self.MAX_PARSE_BYTES]).decode(
            response.encoding or "utf-8",
            errors="replace",
        )
    
    def summarize_page(self, bookmark: Bookmark, 
                       max_length: int = 150) -> Optional[str]:
        """
        Fetch page content and generate a summary.
        Returns summary text or None on failure.
        """
        cache_key = bookmark.url
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            try:
                max_length = max(50, min(1000, int(max_length)))
            except (TypeError, ValueError):
                max_length = 150
            if not URLUtilities._is_safe_url(bookmark.url):
                return None

            # Fetch page content
            response = requests.get(
                bookmark.url,
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=15,
                allow_redirects=False,
                stream=True
            )
            try:
                if response.status_code != 200:
                    return None
                html_text = self._read_summary_html(response)
                if not html_text:
                    return None
            finally:
                response.close()

            # Extract text content
            text = self._extract_text(html_text)
            if len(text) < 100:
                return None
            
            # Truncate for API
            text = text[:4000]
            
            # Generate summary with AI
            client = create_ai_client(self.ai_config)
            
            prompt = f"""Summarize this webpage in 1-2 sentences (max {max_length} characters).
Be concise and capture the main topic/purpose.

Title: {bookmark.title}
URL: {bookmark.url}

Content:
{text}

Summary:"""
            
            # Generate the summary via the provider's text-completion API.
            # (This previously called a non-existent ``categorize_bookmark``
            # method, so every call raised and silently fell through to the
            # naive paragraph extract below — AI summaries never used the model.)
            try:
                summary = client.complete(
                    prompt,
                    system="You write concise, accurate 1-2 sentence summaries of web pages.",
                    max_tokens=160,
                    temperature=0.3,
                )
            except Exception as exc:
                log.warning(f"AI summary failed; using paragraph extract: {exc}")
                summary = None

            if not summary or not str(summary).strip():
                # Fallback: extract first meaningful paragraph
                summary = self._extract_first_paragraph(text)
            
            if summary:
                summary = str(summary).strip()
                if len(summary) > max_length:
                    summary = truncate_string(summary, max_length)
                if len(self._cache) >= self._MAX_CACHE:
                    try:
                        self._cache.pop(next(iter(self._cache)))
                    except StopIteration:
                        pass
                self._cache[cache_key] = summary
                return summary
            
        except Exception:
            pass
        
        return None
    
    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML"""
        # Remove scripts and styles
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Decode HTML entities
        import html as _html_mod
        text = _html_mod.unescape(text)
        
        return text
    
    def _extract_first_paragraph(self, text: str) -> str:
        """Extract first meaningful paragraph as fallback summary"""
        sentences = re.split(r'[.!?]+', text)
        
        meaningful = []
        for sent in sentences:
            sent = sent.strip()
            if len(sent) > 30 and len(sent) < 200:
                meaningful.append(sent)
                if len(' '.join(meaningful)) > 100:
                    break
        
        if meaningful:
            return '. '.join(meaningful[:2]) + '.'
        
        return text[:150] + '...' if len(text) > 150 else text
    
    def batch_summarize(self, bookmarks: List[Bookmark],
                        progress_callback: Callable = None) -> Dict[int, str]:
        """Generate summaries for multiple bookmarks"""
        results = {}
        total = len(bookmarks)
        
        for i, bm in enumerate(bookmarks):
            summary = self.summarize_page(bm)
            if summary:
                results[bm.id] = summary
                bm.ai_summary = summary
            
            if progress_callback:
                progress_callback(i + 1, total, bm)
            
            # Rate limiting
            time.sleep(0.5)
        
        return results


class ScreenshotCapture:
    """Capture screenshots of web pages"""
    
    SCREENSHOT_DIR = DATA_DIR / "screenshots"
    
    def __init__(self):
        self.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    def _screenshot_path(self, bookmark_id: int) -> Optional[Path]:
        """Return a confined screenshot path for a bookmark id."""
        try:
            normalized_id = int(bookmark_id)
        except (TypeError, ValueError):
            return None
        if normalized_id < 0:
            return None
        root = self.SCREENSHOT_DIR.resolve()
        target = (root / f"screenshot_{normalized_id}.png").resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return None
        return target
    
    def capture(self, url: str, bookmark_id: int) -> Optional[str]:
        """
        Capture screenshot of a URL.
        Returns filepath or None on failure.
        
        Note: This uses a simple approach. For production, 
        consider using playwright, selenium, or a screenshot API.
        """
        try:
            if not URLUtilities._is_safe_url(url):
                return None
            # thum.io sends the bookmark URL to a third-party service.
            # Only proceed if the user has explicitly opted in via settings.
            from bookmark_organizer_pro.constants import SETTINGS_FILE
            import json as _json
            _opt_in = False
            try:
                if SETTINGS_FILE.exists():
                    _settings = _json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                    _opt_in = bool(_settings.get("screenshot_api_enabled", False))
            except Exception:
                pass
            if not _opt_in:
                log.info("Screenshot API disabled (set screenshot_api_enabled=true in settings to enable)")
                return None
            api_url = (
                "https://image.thum.io/get/width/1280/crop/800/"
                f"{urllib.parse.quote(url, safe='')}"
            )
            
            response = requests.get(api_url, timeout=30, allow_redirects=False, stream=True)
            try:
                if response.status_code != 200:
                    return None

                content = bytearray()
                for chunk in response.iter_content(chunk_size=16384):
                    if not chunk:
                        continue
                    content.extend(chunk)
                    if len(content) > 5_000_000:
                        return None

                filepath = self._screenshot_path(bookmark_id)
                if filepath is None:
                    return None
                
                with open(filepath, 'wb') as f:
                    f.write(content)
                
                return str(filepath)
            finally:
                response.close()
        except Exception:
            pass
        
        return None
    
    def get_screenshot_path(self, bookmark_id: int) -> Optional[str]:
        """Get path to existing screenshot"""
        filepath = self._screenshot_path(bookmark_id)
        if filepath and filepath.exists():
            return str(filepath)
        return None
    
    def delete_screenshot(self, bookmark_id: int) -> bool:
        """Delete a screenshot"""
        filepath = self._screenshot_path(bookmark_id)
        if not filepath or not filepath.exists():
            return False
        try:
            filepath.unlink()
            return True
        except OSError as e:
            log.warning(f"Could not delete screenshot {filepath}: {e}")
            return False
    
    def get_cache_size(self) -> Tuple[int, int]:
        """Get screenshot cache size (count, bytes)"""
        files = list(self.SCREENSHOT_DIR.glob("*.png"))
        total_size = 0
        count = 0
        for file in files:
            try:
                total_size += file.stat().st_size
                count += 1
            except OSError:
                continue
        return count, total_size
    
    def clear_cache(self):
        """Clear all screenshots"""
        for f in self.SCREENSHOT_DIR.glob("*.png"):
            try:
                f.unlink()
            except OSError as e:
                log.warning(f"Could not delete screenshot cache file {f}: {e}")


class PDFExporter:
    """Export pages or bookmarks as PDF"""
    
    PDF_DIR = DATA_DIR / "pdfs"
    MAX_HTML_BYTES = 5_000_000
    
    def __init__(self):
        self.PDF_DIR.mkdir(parents=True, exist_ok=True)

    def _read_html_response(self, response) -> Optional[str]:
        """Read a bounded HTML response body for PDF rendering."""
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type and content_type not in {"text/html", "application/xhtml+xml"}:
            return None

        try:
            length = int(response.headers.get("Content-Length", "0") or 0)
        except (TypeError, ValueError):
            length = 0
        if length > self.MAX_HTML_BYTES:
            return None

        content = bytearray()
        for chunk in response.iter_content(chunk_size=16384, decode_unicode=False):
            if not chunk:
                continue
            content.extend(chunk)
            if len(content) > self.MAX_HTML_BYTES:
                return None

        encoding = response.encoding or "utf-8"
        return content.decode(encoding, errors="replace")
    
    def save_page_as_pdf(self, url: str, title: str) -> Optional[str]:
        """
        Save a web page as PDF.
        Note: Full implementation would require a headless browser.
        This is a simplified version using weasyprint if available.
        """
        try:
            if not URLUtilities._is_safe_url(url):
                return None
            # Try to use weasyprint if available
            from weasyprint import HTML
            
            response = requests.get(url, timeout=30, allow_redirects=False, stream=True)
            try:
                if response.status_code != 200:
                    return None
                html_text = self._read_html_response(response)
                if not html_text:
                    return None
            finally:
                response.close()

            safe_title = sanitize_filename(title or "bookmark")[:50] or "bookmark"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_title}_{timestamp}.pdf"
            filepath = self.PDF_DIR / filename
            
            HTML(string=html_text, base_url=url).write_pdf(str(filepath))
            
            return str(filepath)
        except ImportError:
            # weasyprint not available
            return None
        except Exception:
            log.warning("PDF page export failed", exc_info=True)
            return None
    
    def export_bookmarks_pdf(self, bookmarks: List[Bookmark], filepath: str):
        """Export bookmark list as PDF document"""
        try:
            from weasyprint import HTML
            
            # Generate HTML for the bookmarks
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; border-bottom: 2px solid #58a6ff; padding-bottom: 10px; }}
        .category {{ margin-top: 30px; }}
        .category h2 {{ color: #555; font-size: 16px; }}
        .bookmark {{ margin: 10px 0; padding: 10px; background: #f5f5f5; border-radius: 4px; }}
        .bookmark a {{ color: #0366d6; text-decoration: none; }}
        .bookmark .domain {{ color: #888; font-size: 12px; }}
        .bookmark .tags {{ color: #6e40c9; font-size: 11px; }}
    </style>
</head>
<body>
    <h1>📚 Bookmark Collection</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    <p>Total: {len(bookmarks)} bookmarks</p>
"""
            
            # Group by category
            by_category: Dict[str, List[Bookmark]] = {}
            for bm in bookmarks:
                cat = bm.category or "Uncategorized"
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(bm)
            
            for category, cat_bookmarks in sorted(by_category.items()):
                safe_category = html_module.escape(str(category), quote=True)
                html_content += f'<div class="category"><h2>{safe_category} ({len(cat_bookmarks)})</h2>'
                
                for bm in cat_bookmarks:
                    safe_url = html_module.escape(str(bm.url or ""), quote=True)
                    safe_title = html_module.escape(str(bm.title or bm.url or "Untitled"), quote=True)
                    safe_domain = html_module.escape(str(bm.domain or ""), quote=True)
                    tags_html = ""
                    if bm.tags:
                        safe_tags = " ".join(
                            f"#{html_module.escape(str(tag), quote=True)}"
                            for tag in bm.tags
                        )
                        tags_html = f'<div class="tags">{safe_tags}</div>'
                    html_content += f'''
                    <div class="bookmark">
                        <a href="{safe_url}">{safe_title}</a>
                        <div class="domain">{safe_domain}</div>
                        {tags_html}
                    </div>'''
                
                html_content += '</div>'
            
            html_content += '</body></html>'
            
            target = Path(filepath)
            target.parent.mkdir(parents=True, exist_ok=True)
            HTML(string=html_content).write_pdf(str(target))
            return True
        
        except ImportError:
            return False
        except Exception:
            log.warning("PDF bookmark export failed", exc_info=True)
            return False
