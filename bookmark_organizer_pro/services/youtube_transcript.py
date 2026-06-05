"""YouTube transcript capture via yt-dlp.

Detects YouTube URLs at save time, fetches auto-generated or manual subtitles,
and stores the transcript as extracted text for semantic search + RAG.

Requires yt-dlp to be installed (pip install yt-dlp or standalone binary).
Degrades gracefully if yt-dlp is not available.
"""

from __future__ import annotations

import importlib
import re
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from bookmark_organizer_pro.constants import EXTRACTED_DIR
from bookmark_organizer_pro.logging_config import log


YOUTUBE_PATTERNS = [
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+"),
    re.compile(r"(?:https?://)?youtu\.be/[\w-]+"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+"),
    re.compile(r"(?:https?://)?music\.youtube\.com/watch\?v=[\w-]+"),
]


def is_youtube_url(url: str) -> bool:
    return any(p.match(url) for p in YOUTUBE_PATTERNS)


def _parse_vtt(vtt_text: str) -> str:
    """Parse WebVTT subtitle file into plain text, removing timestamps and deduplicating lines."""
    lines = []
    seen = set()
    for line in vtt_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if "-->" in line:
            continue
        if line.isdigit():
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean not in seen:
            lines.append(clean)
            seen.add(clean)
    return " ".join(lines)


def fetch_transcript(url: str, lang: str = "en",
                     timeout: int = 60) -> Tuple[bool, str]:
    """Fetch YouTube transcript using yt-dlp.

    Returns (success, transcript_text_or_error).
    """
    if not is_youtube_url(url):
        return False, "Not a YouTube URL"

    if not shutil.which("yt-dlp"):
        try:
            yt_dlp = importlib.import_module("yt_dlp")
        except ImportError:
            return False, "yt-dlp not installed"
        return _fetch_via_library(yt_dlp, url, lang)

    return _fetch_via_cli(url, lang, timeout)


def _fetch_via_cli(url: str, lang: str, timeout: int) -> Tuple[bool, str]:
    """Fetch transcript using yt-dlp CLI binary."""
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            subprocess.run(
                [
                    "yt-dlp",
                    "--skip-download",
                    "--write-auto-sub",
                    "--write-sub",
                    "--sub-lang", lang,
                    "--sub-format", "vtt",
                    "-o", f"{tmpdir}/%(id)s.%(ext)s",
                    url,
                ],
                check=True,
                timeout=timeout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return False, f"yt-dlp failed: {exc}"

        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            return False, "No subtitles found"

        vtt_text = vtt_files[0].read_text(encoding="utf-8", errors="replace")
        transcript = _parse_vtt(vtt_text)
        if not transcript.strip():
            return False, "Transcript is empty"

        return True, transcript


def _fetch_via_library(yt_dlp, url: str, lang: str) -> Tuple[bool, str]:
    """Fetch transcript using yt-dlp Python library."""
    with tempfile.TemporaryDirectory() as tmpdir:
        opts = {
            "skip_download": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": [lang],
            "subtitlesformat": "vtt",
            "outtmpl": f"{tmpdir}/%(id)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as exc:
            return False, f"yt-dlp library failed: {exc}"

        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            return False, "No subtitles found"

        vtt_text = vtt_files[0].read_text(encoding="utf-8", errors="replace")
        transcript = _parse_vtt(vtt_text)
        return (True, transcript) if transcript.strip() else (False, "Transcript is empty")


def save_transcript(bookmark_id: int, transcript: str) -> Path:
    """Save transcript to the extracted text directory."""
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EXTRACTED_DIR / f"{bookmark_id}.txt"
    out_path.write_text(transcript, encoding="utf-8")
    log.info(f"YouTube transcript saved: {out_path} ({len(transcript)} chars)")
    return out_path
