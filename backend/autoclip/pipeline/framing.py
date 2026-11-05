"""Explicit framing choices shared by first renders and review re-exports."""
from pathlib import Path
from typing import Literal
import json

from . import ffmpeg
from .reframe import ReframeConfig, build_crop_path
from .reframe.croppath import CropPath, centre_crop
from .transcript import Transcript

Mode = Literal["auto", "centre", "fit", "split"]


def create(video: Path, start: float, end: float, transcript: Transcript,
           ratio: str, mode: Mode = "auto") -> CropPath:
    aspect_w, aspect_h = {"9:16": (9, 16), "1:1": (1, 1), "16:9": (16, 9)}[ratio]
    if mode == "auto":
        return build_crop_path(video, start_s=start, end_s=end, transcript=transcript,
                               config=ReframeConfig(aspect_w=aspect_w, aspect_h=aspect_h))
    info = ffmpeg.probe(video)
    if not info.width or not info.height:
        raise ValueError("This source has no video picture to frame.")
    path = centre_crop(info.width, info.height, end - start, aspect_w=aspect_w, aspect_h=aspect_h)
    for segment in path.segments:
        segment.fit = mode == "fit"
        segment.split = mode == "split"
    return path


def metadata_path(crop_path: Path) -> Path:
    return crop_path.with_suffix(".framing.json")


def choice(crop_path: Path, default_mode: str = "auto", default_ratio: str = "9:16") -> dict:
    try:
        return json.loads(metadata_path(crop_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"mode": default_mode, "ratio": default_ratio}


def save(path: CropPath, crop_path: Path, mode: str, ratio: str) -> None:
    path.save(crop_path)
    metadata_path(crop_path).write_text(json.dumps({"mode": mode, "ratio": ratio}), encoding="utf-8")
