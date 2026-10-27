"""Deferred YouTube ingestion and per-clip media with explicit timeline offsets.

Remote sources use a small marker rather than pretending a full video exists.
Database words/clips retain episode timestamps; only rendering and playback
translate to a downloaded section's local clock.
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from .. import paths
from ..config import IngestSettings
from ..db.models import Clip, Source, new_id
from . import ffmpeg, ingest
from .transcript import Transcript, Word

log = logging.getLogger(__name__)
MARKER = "remote-youtube.json"


def is_remote(source: Source) -> bool:
    return source.type == "youtube" and Path(source.path).name == MARKER


def _options(settings: IngestSettings, cancelled: Callable[[], bool] | None = None,
             progress: Callable[[float], None] | None = None) -> dict:
    def hook(status: dict) -> None:
        if cancelled and cancelled():
            raise ingest.IngestError("Download cancelled.")
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        if progress and total:
            progress(min(1.0, status.get("downloaded_bytes", 0) / total))

    options = {"quiet": True, "no_warnings": True, "noplaylist": True,
               "retries": 2, "fragment_retries": 2, "socket_timeout": 30,
               "progress_hooks": [hook]}
    if settings.cookies_from_browser:
        options["cookiesfrombrowser"] = (settings.cookies_from_browser,)
    return options


def register(url: str, settings: IngestSettings) -> Source:
    """Save metadata only. No media is downloaded in the HTTP request."""
    import yt_dlp

    try:
        with yt_dlp.YoutubeDL(_options(settings)) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise ingest._translate_ytdlp_error(exc, settings) from exc
    if not info or info.get("_type") in ("playlist", "multi_video"):
        raise ingest.IngestError("Please use a single YouTube video link.")
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
        raise ingest.IngestError("Use a completed video rather than a live or upcoming stream.")
    if not info.get("duration"):
        raise ingest.IngestError("YouTube did not provide a finite duration for this video.")
    source_id = new_id()
    marker = paths.source_media_dir(source_id) / MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"cookies_from_browser": settings.cookies_from_browser}),
                      encoding="utf-8")
    return Source(id=source_id, type="youtube", path=str(marker), url=url,
                  title=info.get("title") or "YouTube video", channel=info.get("uploader"),
                  duration_s=float(info["duration"]), width=info.get("width"),
                  height=info.get("height"), fps=info.get("fps"), has_video=True, has_audio=True)


def source_settings(source: Source, settings: IngestSettings) -> IngestSettings:
    """Retain this source's browser choice without storing cookies or signed URLs."""
    browser = json.loads(Path(source.path).read_text(encoding="utf-8"))["cookies_from_browser"]
    return settings.model_copy(update={"cookies_from_browser": browser})


def parse_json3(data: dict, language: str) -> Transcript:
    """Use real segment offsets only; never invent timings for sentence subtitles."""
    words: list[Word] = []
    for event in data.get("events", []):
        segments = event.get("segs") or []
        if not segments:
            continue
        base = float(event.get("tStartMs", 0)) / 1000
        event_end = base + float(event.get("dDurationMs", 0)) / 1000
        timed = [s for s in segments if s.get("utf8", "").strip()]
        # Human captions commonly contain whole sentences without word offsets.
        if not timed or any((i > 0 and "tOffsetMs" not in s) or len(s["utf8"].split()) != 1 for i, s in enumerate(timed)):
            return Transcript(source="youtube", language=language)
        for i, segment in enumerate(timed):
            start = base + float(segment.get("tOffsetMs", 0)) / 1000
            end = (base + float(timed[i + 1]["tOffsetMs"]) / 1000
                   if i + 1 < len(timed) else min(event_end, start + 1.0))
            if end > start:
                words.append(Word(segment["utf8"].strip(), start, end))
    # Rolling tracks may repeat words. Keep one monotonic sequence.
    unique: dict[tuple[float, str], Word] = {}
    for word in words:
        unique.setdefault((word.start, word.text), word)
    return Transcript(words=sorted(unique.values(), key=lambda w: w.start),
                      source="youtube", language=language, model="youtube-json3")


def fetch_captions(source: Source, directory: Path, settings: IngestSettings,
                   language: str = "", cancelled: Callable[[], bool] | None = None) -> Transcript | None:
    """Prefer original-language auto captions with measured word offsets."""
    import yt_dlp

    options = _options(settings, cancelled)
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(source.url, download=False)
            tracks = (info or {}).get("automatic_captions") or {}
            available = [key for key in tracks if any(t.get("ext") == "json3" for t in tracks[key])]
            if language:
                choices = [key for key in available if key == language or key.startswith(language + "-")]
            else:
                # '-orig' marks the spoken track; don't silently pick a translation.
                choices = [key for key in available if key.endswith("-orig")]
                if not choices and (info or {}).get("language"):
                    choices = [key for key in available if key == info["language"]]
            if not choices:
                return None
            key = choices[0]
            directory.mkdir(parents=True, exist_ok=True)
            options.update({"skip_download": True, "writeautomaticsub": True,
                            "writesubtitles": False, "subtitleslangs": [key],
                            "subtitlesformat": "json3", "outtmpl": str(directory / "captions.%(ext)s")})
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([source.url])
        caption_file = directory / f"captions.{key}.json3"
        transcript = parse_json3(json.loads(caption_file.read_text(encoding="utf-8")), key.split("-")[0])
        return transcript if transcript.words else None
    except Exception as exc:
        if cancelled and cancelled():
            raise ingest.IngestError("Download cancelled.") from exc
        log.warning("YouTube captions unavailable; using audio transcription: %s", exc)
        return None


def download_audio(source: Source, directory: Path, settings: IngestSettings,
                   cancelled=None, progress=None) -> Path:
    import yt_dlp

    directory.mkdir(parents=True, exist_ok=True)
    cached = ingest._find_downloaded_file(directory)
    if cached and cached.stat().st_size:
        return cached
    options = _options(settings, cancelled, progress)
    options.update({"format": "bestaudio[ext=m4a]/bestaudio", "outtmpl": str(directory / "audio.%(ext)s")})
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([source.url])
    except yt_dlp.utils.DownloadError as exc:
        raise ingest._translate_ytdlp_error(exc, settings) from exc
    result = ingest._find_downloaded_file(directory)
    if not result:
        raise ingest.IngestError("Audio download produced no media file.")
    return result


@dataclass
class ClipMedia:
    path: Path
    offset: float = 0.0
    end: float = 0.0


def section_manifest(job_id: str, clip_id: str) -> Path:
    return paths.job_work_dir(job_id) / "sections" / clip_id / "section.json"


def clip_media(source: Source, clip: Clip) -> ClipMedia:
    if not is_remote(source):
        return ClipMedia(Path(source.path), 0.0, source.duration_s)
    manifest = section_manifest(clip.job_id, clip.id)
    if not manifest.exists():
        raise ingest.IngestError("This clip's video section has not been downloaded yet. Retry the job.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    media = ClipMedia(manifest.parent / data["filename"], data["start"], data["end"])
    if not media.path.is_file():
        raise ingest.IngestError("This clip's cached video is missing. Retry the job.")
    if clip.start_s < media.offset - 0.01 or clip.end_s > media.end + 0.01:
        raise ingest.IngestError("Trim must stay inside the downloaded section. Retry with a new selection to extend it.")
    return media


def download_section(source: Source, clip: Clip, settings: IngestSettings,
                     cancelled=None, progress=None) -> ClipMedia:
    import yt_dlp
    from yt_dlp.utils import download_range_func

    try:
        return clip_media(source, clip)
    except ingest.IngestError:
        pass
    start, end = max(0.0, clip.start_s - 2), min(source.duration_s, clip.end_s + 2)
    directory = section_manifest(clip.job_id, clip.id).parent
    # Without a validated manifest, files may be leftovers from an interrupted cut.
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True, exist_ok=True)
    options = _options(settings, cancelled, progress)
    options.update({"format": settings.ytdlp_format, "outtmpl": str(directory / "video.%(ext)s"),
                    "download_ranges": download_range_func(None, [(start, end)]),
                    "force_keyframes_at_cuts": True, "merge_output_format": "mp4"})
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([source.url])
        result = ingest._find_downloaded_file(directory)
        if not result:
            raise ingest.IngestError("Section download produced no video.")
        info = ffmpeg.probe(result)
        if not info.has_video or not info.has_audio or abs(info.duration_s - (end - start)) > 1.0:
            raise ingest.IngestError("Downloaded section has unexpected timing or missing audio/video.")
    except Exception as exc:
        raise ingest.IngestError(
            f"Could not fetch the selected video section: {exc}",
            hint="No full-video fallback was started. Retry, update yt-dlp, or use full-video mode/upload.") from exc
    section_manifest(clip.job_id, clip.id).write_text(
        json.dumps({"filename": result.name, "start": start, "end": start + info.duration_s}), encoding="utf-8")
    return clip_media(source, clip)


def local_transcript(transcript: Transcript, offset: float) -> Transcript:
    """Keep word indices stable while moving the rendering clock to the section."""
    return replace(transcript,
                   words=[replace(w, start=w.start - offset, end=w.end - offset) for w in transcript.words],
                   segments=[replace(s, start=s.start - offset, end=s.end - offset) for s in transcript.segments])
