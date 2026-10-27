import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from autoclip import config
from autoclip.app import create_app
from autoclip.db import store
from autoclip.db.models import Source, Job, Clip
from autoclip.pipeline import framing, long_video, highlights, posting, runner, export, ffmpeg, captions
from autoclip.pipeline.reframe.croppath import centre_crop, CropPath
from autoclip.pipeline.transcript import Transcript, Word
from autoclip.providers import DetectionConfig, TranscriptWindow, ClipCandidates
from autoclip.providers.base import render_window_prompt


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTOCLIP_NO_WORKER", "1")
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def sample(client, tmp_path):
    source = store.create_source(Source(id="s", type="upload", path=str(tmp_path / "source.mp4"),
                                       title="Real episode", url="https://example.com/episode", duration_s=60,
                                       width=1920, height=1080))
    settings = config.Settings(active_provider="ollama")
    settings.clips.topic = "Money and relationships"
    job = store.create_job(Job(id="j", source_id=source.id, provider="ollama", settings=settings.model_dump()))
    clip = Clip(id="c", job_id=job.id, start_s=0, end_s=30, start_word=0, end_word=1)
    store.replace_clips(job.id, [clip])
    Transcript(words=[Word("Save", 0, 1), Word("money.", 29, 30)]).save(runner.JobWorkspace(job.id).transcript)
    return source, job, clip


def test_topic_and_framing_reach_saved_job_and_prompt(client, sample):
    response = client.post("/api/jobs", json={"source_id": "s", "settings": {
        "topic": "Dating and money", "framing": "split", "diarization": False}})
    assert response.status_code == 201
    job = store.get_job(response.json()["id"])
    run = runner.PipelineRunner(job, store.get_source("s"))
    assert run.settings.clips.topic == "Dating and money"
    assert run.settings.export.framing == "split"
    prompt = render_window_prompt(TranscriptWindow("[0]Hello", 0, 0), DetectionConfig(topic="Dating and money"))
    assert "Dating and money" in prompt and "empty clips list" in prompt
    assert client.post("/api/jobs", json={"source_id": "s", "settings": {"topic": "x" * 501}}).status_code == 422
    assert client.post("/api/jobs", json={"source_id": "s", "settings": {"framing": "invalid"}}).status_code == 422


def test_progress_message_survives_snapshot(client, sample):
    source, job, _ = sample
    run = runner.PipelineRunner(job, source)
    run._emit(runner.Stage.HIGHLIGHTS, .5, "Analysed section 3/6")
    assert client.get("/api/jobs/j").json()["progress_message"] == "Analysed section 3/6"


def test_download_activity_includes_bytes():
    messages = []
    hook = long_video._options(config.IngestSettings(), activity=messages.append)["progress_hooks"][0]
    hook({"status": "finished", "downloaded_bytes": 2 * 1024**2, "total_bytes": 4 * 1024**2})
    assert messages == ["Downloaded 2.0 / 4.0 MB"]


@pytest.mark.asyncio
async def test_checkpoint_invalidation_on_topic_change(tmp_path):
    class Provider:
        name, model, base_url = "ollama", "qwen3:4b", "http://localhost"
        calls = 0
        async def detect_highlights(self, window, settings):
            self.calls += 1
            return ClipCandidates(clips=[])
    provider = Provider()
    transcript = Transcript(words=[Word("Hello.", 0, 1)])
    events = []
    for topic in ("money", "money", "dating"):
        with pytest.raises(highlights.HighlightError, match="No clips"):
            await highlights.detect(transcript, provider, DetectionConfig(topic=topic), job_id="j",
                                    cache_dir=tmp_path, on_window=lambda *args: events.append(args))
    assert provider.calls == 2
    assert events == [(1, 1, False), (1, 1, True), (1, 1, False)]


def test_editable_posting_draft_is_grounded_and_saved(client, sample, monkeypatch):
    calls = []
    class Provider:
        async def _complete(self, system, payload, config):
            calls.append(json.loads(payload))
            return json.dumps({"youtube_title": "A money conversation", "description": "A discussion.",
                               "facebook_caption": "What would you do?", "hashtags": ["#Money"],
                               "commentary_points": ["Explain your view", "Discuss tradeoffs", "Ask a question"],
                               "source_credit": "An invented source"})
    monkeypatch.setattr("autoclip.providers.build_provider", lambda *a: Provider())
    assert client.get("/api/clips/c/posting").status_code == 404
    response = client.post("/api/clips/c/posting")
    assert response.status_code == 200, response.text
    draft = response.json()
    assert calls[0]["transcript"] == "Save money."
    assert calls[0]["topic"] == "Money and relationships"
    assert draft["source_credit"] == "Source: Real episode\nhttps://example.com/episode"
    draft["youtube_title"] = "My edited title"
    assert client.put("/api/clips/c/posting", json=draft).status_code == 200
    assert client.get("/api/clips/c/posting").json()["youtube_title"] == "My edited title"
    draft["youtube_title"] = "x" * 101
    assert client.put("/api/clips/c/posting", json=draft).status_code == 422
    assert client.patch("/api/clips/c/captions", json={"words": [{"text": "Changed", "start": 0, "end": 1}]}).status_code == 200
    assert client.get("/api/clips/c/posting").status_code == 404


def test_posting_failure_is_actionable(client, sample, monkeypatch):
    class Provider:
        async def _complete(self, *args): raise RuntimeError("Ollama offline")
    monkeypatch.setattr("autoclip.providers.build_provider", lambda *a: Provider())
    response = client.post("/api/clips/c/posting")
    assert response.status_code == 422 and "Ollama offline" in response.text


def test_framing_choice_is_saved_for_preview_and_export(client, sample, monkeypatch):
    calls = []
    def create(*args):
        calls.append(args)
        path = centre_crop(1920, 1080, 30)
        path.segments[0].split = True
        return path
    monkeypatch.setattr(framing, "create", create)
    response = client.patch("/api/clips/c/framing", json={"mode": "split", "ratio": "9:16"})
    assert response.status_code == 200, response.text
    assert response.json()["framing"] == "split"
    assert client.get("/api/clips/c/crop-path").json()["segments"][0]["split"] is True
    assert calls[0][-1] == "split"
    from autoclip.api.clips import _crop_path_for
    path = _crop_path_for(runner.JobWorkspace("j"), sample[2], sample[0], "9:16")
    assert path.segments[0].split and len(calls) == 1
    assert client.patch("/api/clips/c/framing", json={"mode": "unknown"}).status_code == 422


@pytest.mark.parametrize("mode", ["fit", "split", "centre"])
def test_explicit_layout_real_render(tmp_path, mode):
    source = tmp_path / "source.mp4"
    subprocess.run([ffmpeg.ffmpeg_path(), "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=red:size=160x180:rate=10:duration=1",
        "-f", "lavfi", "-i", "color=blue:size=160x180:rate=10:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-filter_complex", "[0:v][1:v]hstack[v]", "-map", "[v]", "-map", "2:a",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", str(source)], check=True, capture_output=True)
    path = framing.create(source, 0, 1, Transcript(), "9:16", mode)
    assert CropPath.from_dict(path.to_dict()).segments[0].split == (mode == "split")
    output = tmp_path / "out.mp4"
    export.export_clip(export.ExportRequest(source=source, destination=output, start_s=0, end_s=1,
        crop_path=path, words=[], style=captions.get_style("bold_pop")), work_dir=tmp_path / "work",
        settings=config.ExportSettings(prefer_hardware_encoder=False))
    info = ffmpeg.probe(output)
    assert info.has_audio and (info.width, info.height) == (1080, 1920)
    if mode == "split":
        def pixel(y):
            result = subprocess.run([ffmpeg.ffmpeg_path(), "-v", "error", "-i", str(output),
                "-vf", f"format=rgb24,crop=1:1:540:{y}", "-frames:v", "1", "-f", "rawvideo", "-"],
                check=True, capture_output=True)
            return result.stdout[:3]
        top, bottom = pixel(200), pixel(1400)
        assert top[0] > top[2] + 100
        assert bottom[2] > bottom[0] + 100
