"""Long episode routing, measured caption timing, and local media clock tests."""
from dataclasses import replace
from pathlib import Path
import json
from types import SimpleNamespace

import pytest

from autoclip.config import IngestSettings, Settings
from autoclip.db import store
from autoclip.db.models import Source, Job, Clip
from autoclip.pipeline import long_video, ingest, highlights, runner
from autoclip.pipeline.transcript import Transcript, Word
from autoclip.providers import ClipCandidate, ClipCandidates, DetectionConfig


def remote_source(tmp_path):
    marker = tmp_path / long_video.MARKER
    marker.write_text('{"cookies_from_browser": ""}')
    return Source(id="source", type="youtube", path=str(marker),
                  url="https://www.youtube.com/watch?v=example", duration_s=10800)


def test_measured_captions_and_sentence_fallback():
    data = {"events": [{"tStartMs": 3600000, "dDurationMs": 2000, "segs": [
        {"utf8": "Hello", "tOffsetMs": 0}, {"utf8": "world.", "tOffsetMs": 600}]}]}
    result = long_video.parse_json3(data, "en")
    assert [(w.text, w.start, w.end) for w in result.words] == [
        ("Hello", 3600, 3600.6), ("world.", 3600.6, 3601.6)]
    data["events"][0]["segs"] = [{"utf8": "A whole sentence without word timestamps"}]
    assert not long_video.parse_json3(data, "en").words


def test_clip_clock_preserves_episode_indices(tmp_path):
    source = remote_source(tmp_path)
    clip = Clip(id="clip", job_id="job", start_s=3602, end_s=3630)
    manifest = long_video.section_manifest("job", "clip")
    manifest.parent.mkdir(parents=True)
    (manifest.parent / "video.mp4").write_bytes(b"media")
    manifest.write_text(json.dumps({"filename": "video.mp4", "start": 3600, "end": 3632}))
    media = long_video.clip_media(source, clip)
    assert clip.start_s - media.offset == 2
    transcript = Transcript(words=[Word("Earlier", 10, 11), Word("Selected", 3602, 3603)])
    local = long_video.local_transcript(transcript, media.offset)
    assert local.words[1].start == 2
    assert transcript.words[1].start == 3602
    with pytest.raises(ingest.IngestError, match="Trim"):
        long_video.clip_media(source, replace(clip, end_s=3640))


def test_registration_never_downloads_media(monkeypatch, tmp_path):
    calls = []
    class YDL:
        def __init__(self, options):
            assert options["noplaylist"]
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            calls.append(download)
            return {"title": "Long podcast", "duration": 10800, "width": 1920, "height": 1080}
    monkeypatch.setattr("yt_dlp.YoutubeDL", YDL)
    source = long_video.register("https://youtube.com/watch?v=test&list=list", IngestSettings())
    assert calls == [False]
    assert long_video.is_remote(source)
    assert source.duration_s == 10800
    assert Path(source.path).is_file()


def test_partial_download_requests_range_and_reuses_cache(monkeypatch, tmp_path):
    source = remote_source(tmp_path)
    clip = Clip(id="c", job_id="j", start_s=7200, end_s=7230)
    seen = []
    class YDL:
        def __init__(self, options): self.options = options
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def download(self, urls):
            seen.append(list(self.options["download_ranges"]({}, self)))
            assert self.options["force_keyframes_at_cuts"] is True
            Path(self.options["outtmpl"].replace("%(ext)s", "mp4")).write_bytes(b"media")
    monkeypatch.setattr("yt_dlp.YoutubeDL", YDL)
    monkeypatch.setattr(long_video.ffmpeg, "probe", lambda p: SimpleNamespace(
        has_video=True, has_audio=True, duration_s=34))
    media = long_video.download_section(source, clip, IngestSettings())
    assert media.offset == 7198
    assert seen[0][0]["start_time"] == 7198
    assert seen[0][0]["end_time"] == 7232
    long_video.download_section(source, clip, IngestSettings())
    assert len(seen) == 1


def test_caption_path_skips_audio_and_full_source(monkeypatch, tmp_path, initialised_db):
    source = remote_source(tmp_path)
    store.create_source(source)
    job = Job(id="job", source_id=source.id)
    store.create_job(job)
    transcript = Transcript(words=[Word("Hi", 3600, 3601)], source="youtube")
    monkeypatch.setattr(long_video, "fetch_captions", lambda *a: transcript)
    monkeypatch.setattr(long_video, "download_audio", lambda *a: pytest.fail("Must not download audio"))
    run = runner.PipelineRunner(job, source, settings=Settings())
    assert run._remote_transcript().words[0].start == 3600
    assert run.workspace.transcript.exists()
    monkeypatch.setattr(long_video, "fetch_captions", lambda *a: pytest.fail("Must reuse transcript"))
    assert run._remote_transcript().words[0].start == 3600


def test_no_caption_path_downloads_audio_only(monkeypatch, tmp_path, initialised_db):
    source = remote_source(tmp_path)
    store.create_source(source)
    job = Job(id="job", source_id=source.id)
    store.create_job(job)
    run = runner.PipelineRunner(job, source, settings=Settings())
    monkeypatch.setattr(long_video, "fetch_captions", lambda *a: None)
    monkeypatch.setattr(long_video, "download_audio", lambda *a: tmp_path / "audio.m4a")
    calls = []
    monkeypatch.setattr(runner.prepare, "extract_audio", lambda *a, **kw: calls.append(a))
    monkeypatch.setattr(run, "_stage_transcribe", lambda p: Transcript(words=[Word("Hi", 0, 1)]))
    assert run._remote_transcript().words
    assert calls[0][0].suffix == ".m4a"


@pytest.mark.asyncio
async def test_window_checkpoint_avoids_repeated_llm_requests(tmp_path):
    class Provider:
        name, model, base_url = "ollama", "local", "http://localhost"
        calls = 0
        async def detect_highlights(self, window, config):
            self.calls += 1
            return ClipCandidates(clips=[ClipCandidate(start_word_index=0, end_word_index=29)])
    transcript = Transcript(words=[Word("word.", i, i + .9) for i in range(60)])
    provider = Provider()
    config = DetectionConfig(min_duration_s=20, max_duration_s=40)
    await highlights.detect(transcript, provider, config, job_id="a", cache_dir=tmp_path)
    await highlights.detect(transcript, provider, config, job_id="a", cache_dir=tmp_path)
    assert provider.calls == 1
    provider.model = "changed"
    await highlights.detect(transcript, provider, config, job_id="a", cache_dir=tmp_path)
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_timeouts_are_not_reported_as_no_highlights():
    class Provider:
        name, model, base_url = "ollama", "local", "http://localhost"
        async def detect_highlights(self, window, config): raise TimeoutError("Ollama timed out")
    with pytest.raises(highlights.HighlightError, match="analysis failed"):
        await highlights.detect(Transcript(words=[Word("word", 0, 1)]), Provider(),
                                DetectionConfig(), job_id="a")


def test_section_reframe_and_export_use_local_clock(monkeypatch, tmp_path, initialised_db):
    source = remote_source(tmp_path)
    store.create_source(source)
    job = Job(id="job", source_id=source.id)
    store.create_job(job)
    clip = Clip(id="clip", job_id=job.id, start_s=3602, end_s=3625, start_word=0, end_word=1)
    store.replace_clips(job.id, [clip])
    media_path = tmp_path / "section.mp4"
    monkeypatch.setattr(long_video, "clip_media", lambda *a: long_video.ClipMedia(media_path, 3600, 3627))
    transcript = Transcript(words=[Word("Hello", 3602, 3603), Word("world", 3624, 3625)])
    from autoclip.pipeline.reframe.croppath import centre_crop
    crop = centre_crop(1920, 1080, 23)
    def reframe(path, **kwargs):
        assert path == media_path
        assert (kwargs["start_s"], kwargs["end_s"]) == (2, 25)
        assert kwargs["transcript"].words[0].start == 2
        return crop
    requests = []
    def export(request, **kwargs):
        requests.append(request)
        request.destination.write_bytes(b"rendered")
    monkeypatch.setattr(runner, "build_crop_path", reframe)
    monkeypatch.setattr(runner.export, "export_clip", export)
    run = runner.PipelineRunner(job, source, settings=Settings())
    crops = run._stage_reframe([clip], transcript)
    run._stage_export([clip], transcript, crops)
    assert requests[0].source == media_path
    assert (requests[0].start_s, requests[0].end_s) == (2, 25)
    assert requests[0].words[0].start == 2
    assert store.list_exports(clip.id)
    assert store.get_clip(clip.id).start_s == 3602


def test_long_mode_api_preview_trim_and_reexport(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from autoclip.app import create_app
    from autoclip.api import clips as clip_api
    from autoclip.pipeline.reframe.croppath import centre_crop
    monkeypatch.setenv("AUTOCLIP_NO_WORKER", "1")
    with TestClient(create_app()) as client:
        source = remote_source(tmp_path)
        monkeypatch.setattr(long_video, "register", lambda *a: source)
        monkeypatch.setattr(ingest, "ingest_youtube", lambda *a: pytest.fail("Full download forbidden"))
        response = client.post("/api/sources/youtube", json={
            "url": source.url, "transcript_first": True})
        assert response.status_code == 201
        job = Job(id="job", source_id=source.id)
        store.create_job(job)
        clip = Clip(id="clip", job_id=job.id, start_s=3602, end_s=3625, start_word=0, end_word=1)
        store.replace_clips(job.id, [clip])
        manifest = long_video.section_manifest(job.id, clip.id)
        manifest.parent.mkdir(parents=True)
        (manifest.parent / "video.mp4").write_bytes(b"video")
        manifest.write_text(json.dumps({"filename": "video.mp4", "start": 3600, "end": 3627}))
        workspace = runner.JobWorkspace(job.id)
        Transcript(words=[Word("Hello", 3602, 3603), Word("world", 3624, 3625)]).save(workspace.transcript)
        assert client.get("/api/clips/clip").json()["media_offset_s"] == 3600
        assert client.get("/api/clips/clip/media").content == b"video"
        assert client.get("/api/jobs/job/media").status_code == 409
        assert client.patch("/api/clips/clip", json={"end_s": 3700}).status_code == 400
        requests = []
        monkeypatch.setattr(clip_api, "_crop_path_for", lambda *a: centre_crop(1920, 1080, 23))
        def export(request, **kwargs):
            requests.append(request)
            request.destination.parent.mkdir(parents=True, exist_ok=True)
            request.destination.write_bytes(b"rendered")
        monkeypatch.setattr(clip_api.export_module, "export_clip", export)
        result = client.post("/api/clips/clip/export", json={})
        assert result.status_code == 201, result.text
        assert requests[0].start_s == 2
        assert requests[0].words[0].start == 2


def test_live_registration_is_rejected_without_media(monkeypatch):
    class YDL:
        def __init__(self, options): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            assert download is False
            return {"is_live": True, "duration": 100}
    monkeypatch.setattr("yt_dlp.YoutubeDL", YDL)
    with pytest.raises(ingest.IngestError, match="completed video"):
        long_video.register("https://youtube.com/watch?v=test", IngestSettings())


def test_real_render_with_episode_offset(tmp_path):
    """A section from hour one must render at local seconds, with synced captions."""
    import subprocess
    from autoclip.pipeline import captions, export, ffmpeg
    from autoclip.config import ExportSettings
    from autoclip.pipeline.reframe.croppath import centre_crop
    media = tmp_path / "section.mp4"
    subprocess.run([ffmpeg.ffmpeg_path(), "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=320x180:rate=10:duration=4", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=4", "-c:v", "libx264", "-c:a", "aac",
                    "-shortest", str(media)], check=True, capture_output=True)
    transcript = Transcript(words=[Word("Hello", 3601, 3601.5), Word("world", 3601.5, 3602)])
    local = long_video.local_transcript(transcript, 3600)
    output = tmp_path / "render.mp4"
    export.export_clip(export.ExportRequest(
        source=media, destination=output, start_s=1, end_s=2,
        crop_path=centre_crop(320, 180, 1), words=local.words,
        style=captions.get_style("bold_pop")), work_dir=tmp_path / "work",
        settings=ExportSettings(prefer_hardware_encoder=False))
    info = ffmpeg.probe(output)
    assert info.has_audio and info.has_video
    assert (info.width, info.height) == (1080, 1920)
    assert info.duration_s == pytest.approx(1, abs=.2)
    ass = (tmp_path / "work" / "render" / "captions.ass").read_text()
    assert "HELLO" in ass
    assert "1:00:01" not in ass
