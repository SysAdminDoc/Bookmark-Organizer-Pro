"""Opt-in, bounded YouTube transcript capture and lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import html
import importlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Tuple
from urllib.parse import parse_qs, urlsplit

from bookmark_organizer_pro.constants import YOUTUBE_TRANSCRIPTS_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.job_ledger import JobLedger, redact_job_error


MAX_TRANSCRIPT_CHARS = 2_000_000
MAX_TRANSCRIPT_ERROR_CHARS = 500
MAX_LANGUAGE_CHARS = 32
DEFAULT_TRANSCRIPT_LANGUAGE = "en"
DEFAULT_TRANSCRIPT_TIMEOUT_SECONDS = 60
MAX_TRANSCRIPT_TIMEOUT_SECONDS = 300

YOUTUBE_PATTERNS = [
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+", re.IGNORECASE),
    re.compile(r"(?:https?://)?youtu\.be/[\w-]+", re.IGNORECASE),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+", re.IGNORECASE),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+", re.IGNORECASE),
    re.compile(r"(?:https?://)?music\.youtube\.com/watch\?v=[\w-]+", re.IGNORECASE),
]
LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?$")


def normalize_language(value: str | None) -> str:
    """Normalize a subtitle language tag without allowing shell-like input."""

    language = str(value or DEFAULT_TRANSCRIPT_LANGUAGE).strip().replace("_", "-")
    if len(language) > MAX_LANGUAGE_CHARS or not LANGUAGE_PATTERN.fullmatch(language):
        raise ValueError("language must be an ISO-style tag such as en or pt-BR")
    return language.lower()


def normalize_timeout(value: int | float | None) -> int:
    try:
        timeout = int(value if value is not None else DEFAULT_TRANSCRIPT_TIMEOUT_SECONDS)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout must be an integer number of seconds") from exc
    if timeout < 1 or timeout > MAX_TRANSCRIPT_TIMEOUT_SECONDS:
        raise ValueError(f"timeout must be between 1 and {MAX_TRANSCRIPT_TIMEOUT_SECONDS} seconds")
    return timeout


def is_youtube_url(url: str) -> bool:
    value = str(url or "").strip()
    if not value:
        return False
    candidate = value if "://" in value else f"https://{value}"
    try:
        parsed = urlsplit(candidate)
        host = (parsed.hostname or "").lower().removeprefix("www.")
    except ValueError:
        return False

    if host == "youtu.be":
        return bool(re.fullmatch(r"/[A-Za-z0-9_-]+/?", parsed.path or ""))
    if host not in {"youtube.com", "music.youtube.com", "m.youtube.com"}:
        return False
    if parsed.path == "/watch":
        return bool(parse_qs(parsed.query).get("v", [""])[0])
    return bool(re.fullmatch(r"/(?:shorts|embed)/[A-Za-z0-9_-]+/?", parsed.path or ""))


def _bound_transcript(text: str) -> tuple[str, bool]:
    value = " ".join(str(text or "").split()).strip()
    if len(value) <= MAX_TRANSCRIPT_CHARS:
        return value, False
    return value[:MAX_TRANSCRIPT_CHARS].rstrip(), True


def _parse_vtt(vtt_text: str) -> str:
    """Parse WebVTT into plain text, removing timestamps and duplicate cues."""

    lines = []
    seen = set()
    for line in str(vtt_text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if "-->" in line or line.isdigit():
            continue
        clean = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        if clean and clean not in seen:
            lines.append(clean)
            seen.add(clean)
    return " ".join(lines)


def _read_vtt_file(path: Path) -> str:
    """Read a subtitle file with a source-size guard."""

    try:
        # VTT is normally a small text sidecar. Four UTF-8 bytes per output
        # character is a conservative bound that prevents an oversized file
        # from becoming an unbounded in-memory input before truncation.
        max_source_bytes = MAX_TRANSCRIPT_CHARS * 4
        with path.open("rb") as handle:
            raw = handle.read(max_source_bytes + 1)
        return raw[:max_source_bytes].decode("utf-8", errors="replace")
    except OSError:
        return ""


def fetch_transcript(url: str, lang: str = DEFAULT_TRANSCRIPT_LANGUAGE,
                     timeout: int = DEFAULT_TRANSCRIPT_TIMEOUT_SECONDS) -> Tuple[bool, str]:
    """Fetch a bounded transcript using yt-dlp.

    The tuple is retained for compatibility with older callers. New workflow
    code classifies the second value with :func:`classify_transcript_error`.
    """

    try:
        language = normalize_language(lang)
        bounded_timeout = normalize_timeout(timeout)
    except ValueError as exc:
        return False, str(exc)
    if not is_youtube_url(url):
        return False, "Not a YouTube URL"

    if not shutil.which("yt-dlp"):
        try:
            yt_dlp = importlib.import_module("yt_dlp")
        except ImportError:
            return False, "yt-dlp not installed"
        return _fetch_via_library(yt_dlp, url, language, bounded_timeout)

    return _fetch_via_cli(url, language, bounded_timeout)


def _fetch_via_cli(url: str, lang: str, timeout: int) -> Tuple[bool, str]:
    """Fetch transcript using the yt-dlp CLI binary."""

    with tempfile.TemporaryDirectory(prefix="bop_transcript_") as tmpdir:
        try:
            completed = subprocess.run(
                [
                    "yt-dlp",
                    "--no-playlist",
                    "--skip-download",
                    "--write-auto-sub",
                    "--write-sub",
                    "--sub-lang", lang,
                    "--sub-format", "vtt",
                    "--quiet",
                    "--no-warnings",
                    "-o", f"{tmpdir}/%(id)s.%(ext)s",
                    url,
                ],
                check=False,
                timeout=timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return False, "yt-dlp timed out"
        except OSError as exc:
            return False, f"yt-dlp unavailable: {exc}"

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "yt-dlp failed").strip()
            return False, f"yt-dlp failed: {detail[:MAX_TRANSCRIPT_ERROR_CHARS]}"

        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            return False, "No subtitles found"

        transcript = _parse_vtt(_read_vtt_file(vtt_files[0]))
        bounded, _ = _bound_transcript(transcript)
        return (True, bounded) if bounded else (False, "Transcript is empty")


def _fetch_via_library(yt_dlp, url: str, lang: str, timeout: int) -> Tuple[bool, str]:
    """Fetch transcript using the optional yt-dlp Python library."""

    with tempfile.TemporaryDirectory(prefix="bop_transcript_") as tmpdir:
        opts = {
            "skip_download": True,
            "noplaylist": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": [lang],
            "subtitlesformat": "vtt",
            "socket_timeout": timeout,
            "outtmpl": f"{tmpdir}/%(id)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as exc:
            return False, f"yt-dlp library failed: {str(exc)[:MAX_TRANSCRIPT_ERROR_CHARS]}"

        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            return False, "No subtitles found"

        transcript = _parse_vtt(_read_vtt_file(vtt_files[0]))
        bounded, _ = _bound_transcript(transcript)
        return (True, bounded) if bounded else (False, "Transcript is empty")


def classify_transcript_error(error: object) -> tuple[str, bool]:
    """Classify provider failures and identify failures worth retrying."""

    text = " ".join(str(error or "").split())[:MAX_TRANSCRIPT_ERROR_CHARS]
    lowered = text.lower()
    if "not a youtube url" in lowered:
        return "ineligible", False
    if any(
        marker in lowered
        for marker in (
            "no subtitles",
            "does not have subtitles",
            "subtitles are not available",
            "no captions",
            "no automatic captions",
            "captions are not available",
            "transcript is empty",
            "captionless",
        )
    ):
        return "no_captions", False
    if any(marker in lowered for marker in ("429", "rate limit", "too many requests", "ratelimit")):
        return "rate_limited", True
    if any(
        marker in lowered
        for marker in (
            "private",
            "video unavailable",
            "video is unavailable",
            "unavailable",
            "sign in",
            "login required",
            "members-only",
            "not available",
            "age-restricted",
            "geo-restricted",
            "region blocked",
            "yt-dlp not installed",
            "yt-dlp unavailable",
        )
    ):
        return "unavailable", True
    return "failed", True


def _safe_transcript_path(path: str | Path, transcripts_dir: Path) -> Path | None:
    try:
        resolved = Path(path).expanduser().resolve()
        root = Path(transcripts_dir).resolve()
        return resolved if resolved.is_relative_to(root) else None
    except (OSError, RuntimeError, ValueError):
        return None


def _transcript_filename(bookmark_id: int, language: str) -> str:
    safe_language = re.sub(r"[^a-z0-9-]", "-", language.lower()).strip("-") or "en"
    return f"{int(bookmark_id)}.{safe_language}.txt"


def save_transcript(
    bookmark_id: int,
    transcript: str,
    *,
    language: str = DEFAULT_TRANSCRIPT_LANGUAGE,
    transcripts_dir: Path = YOUTUBE_TRANSCRIPTS_DIR,
) -> Path:
    """Atomically save one bounded, language-specific transcript artifact."""

    normalized_language = normalize_language(language)
    bounded, _ = _bound_transcript(transcript)
    if not bounded:
        raise ValueError("Transcript is empty")
    directory = Path(transcripts_dir)
    directory.mkdir(parents=True, exist_ok=True)
    out_path = directory / _transcript_filename(bookmark_id, normalized_language)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f".{out_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(bounded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, out_path)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
    log.info("YouTube transcript saved: %s (%s chars)", out_path, len(bounded))
    return out_path


@dataclass(frozen=True)
class TranscriptResult:
    """Non-sensitive outcome and provenance for one transcript operation."""

    status: str
    success: bool = False
    retryable: bool = False
    error: str = ""
    language: str = ""
    path: str = ""
    sha256: str = ""
    chars: int = 0
    truncated: bool = False
    backend: str = "yt-dlp"
    fetched_at: str = ""
    job_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class YouTubeTranscriptService:
    """Opt-in transcript capture/removal with durable retry metadata."""

    job_type = "youtube_transcript"

    def __init__(
        self,
        *,
        job_ledger: JobLedger | None = None,
        fetcher: Callable[[str, str, int], Tuple[bool, str]] = fetch_transcript,
        transcripts_dir: Path = YOUTUBE_TRANSCRIPTS_DIR,
    ):
        self.job_ledger = job_ledger or JobLedger()
        self.fetcher = fetcher
        self.transcripts_dir = Path(transcripts_dir)

    def capture(
        self,
        bookmark: Bookmark,
        *,
        language: str = DEFAULT_TRANSCRIPT_LANGUAGE,
        timeout: int = DEFAULT_TRANSCRIPT_TIMEOUT_SECONDS,
    ) -> TranscriptResult:
        try:
            normalized_language = normalize_language(language)
            bounded_timeout = normalize_timeout(timeout)
        except ValueError as exc:
            return TranscriptResult(status="failed", error=str(exc))

        job = self.job_ledger.start(
            self.job_type,
            bookmark_id=bookmark.id,
            url_or_domain=bookmark.url,
            backend="yt-dlp",
            language=normalized_language,
        )
        if not is_youtube_url(bookmark.url):
            error = "Not a YouTube URL"
            record = job.fail(error, retryable=False, backend="yt-dlp")
            return TranscriptResult(
                status="ineligible",
                error=error,
                language=normalized_language,
                job_id=record.job_id,
            )

        try:
            ok, payload = self.fetcher(bookmark.url, normalized_language, bounded_timeout)
        except Exception as exc:
            ok, payload = False, f"Transcript provider failed: {exc}"
        if not ok:
            status, retryable = classify_transcript_error(payload)
            record = job.fail(payload, retryable=retryable, backend="yt-dlp")
            return TranscriptResult(
                status=status,
                retryable=retryable,
                error=redact_job_error(payload),
                language=normalized_language,
                job_id=record.job_id,
            )

        raw_text = str(payload or "")
        bounded_text, truncated = _bound_transcript(raw_text)
        if len(raw_text) >= MAX_TRANSCRIPT_CHARS:
            truncated = True
        if not bounded_text:
            error = "Transcript is empty"
            record = job.fail(error, retryable=False, backend="yt-dlp")
            return TranscriptResult(
                status="no_captions",
                error=error,
                language=normalized_language,
                job_id=record.job_id,
            )

        try:
            path = save_transcript(
                bookmark.id,
                bounded_text,
                language=normalized_language,
                transcripts_dir=self.transcripts_dir,
            )
        except Exception as exc:
            record = job.fail(f"Could not store transcript: {exc}", retryable=False, backend="yt-dlp")
            return TranscriptResult(
                status="failed",
                error=record.error,
                language=normalized_language,
                job_id=record.job_id,
            )

        digest = hashlib.sha256(bounded_text.encode("utf-8")).hexdigest()
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = job.succeed(
            bytes_processed=len(bounded_text.encode("utf-8")),
            backend="yt-dlp",
        )
        old_path = _safe_transcript_path(bookmark.youtube_transcript_path, self.transcripts_dir)
        if old_path is not None and old_path != path:
            try:
                old_path.unlink(missing_ok=True)
            except OSError:
                log.warning("Could not remove superseded transcript artifact %s", old_path)
        return TranscriptResult(
            status="success",
            success=True,
            language=normalized_language,
            path=str(path),
            sha256=digest,
            chars=len(bounded_text),
            truncated=truncated,
            fetched_at=fetched_at,
            job_id=record.job_id,
        )

    def apply(self, bookmark: Bookmark, result: TranscriptResult) -> bool:
        """Apply only a successful result to bookmark metadata."""

        if not result.success or not result.path:
            return False
        changed = any(
            getattr(bookmark, field) != value
            for field, value in (
                ("youtube_transcript_path", result.path),
                ("youtube_transcript_language", result.language),
                ("youtube_transcript_sha256", result.sha256),
                ("youtube_transcript_fetched_at", result.fetched_at),
                ("youtube_transcript_backend", result.backend),
                ("youtube_transcript_chars", result.chars),
                ("youtube_transcript_truncated", result.truncated),
            )
        )
        bookmark.youtube_transcript_path = result.path
        bookmark.youtube_transcript_language = result.language
        bookmark.youtube_transcript_sha256 = result.sha256
        bookmark.youtube_transcript_fetched_at = result.fetched_at
        bookmark.youtube_transcript_backend = result.backend
        bookmark.youtube_transcript_chars = result.chars
        bookmark.youtube_transcript_truncated = result.truncated
        return changed

    def remove(self, bookmark: Bookmark) -> TranscriptResult:
        """Remove only this workflow's artifact and clear its metadata."""

        language = bookmark.youtube_transcript_language or DEFAULT_TRANSCRIPT_LANGUAGE
        job = self.job_ledger.start(
            "youtube_transcript_remove",
            bookmark_id=bookmark.id,
            url_or_domain=bookmark.url,
            backend="local",
            language=language,
        )
        path = _safe_transcript_path(bookmark.youtube_transcript_path, self.transcripts_dir)
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                record = job.fail(f"Could not remove transcript: {exc}", retryable=True, backend="local")
                return TranscriptResult(
                    status="failed",
                    retryable=True,
                    error=record.error,
                    language=language,
                    job_id=record.job_id,
                )
        record = job.succeed(backend="local")
        bookmark.youtube_transcript_path = ""
        bookmark.youtube_transcript_language = ""
        bookmark.youtube_transcript_sha256 = ""
        bookmark.youtube_transcript_fetched_at = ""
        bookmark.youtube_transcript_backend = ""
        bookmark.youtube_transcript_chars = 0
        bookmark.youtube_transcript_truncated = False
        return TranscriptResult(
            status="removed",
            success=True,
            language=language,
            backend="local",
            job_id=record.job_id,
        )
