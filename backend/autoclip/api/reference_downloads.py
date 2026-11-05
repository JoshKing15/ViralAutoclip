"""Background reference imports with observable transfer progress."""
import asyncio
import json
import math
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..db import store
from ..db.models import new_id
from ..pipeline import ingest, long_video, reference_style

router = APIRouter(prefix='/api/reference-downloads', tags=['reference downloads'])
active: set[str] = set()


class DownloadIn(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


def path_for(key: str) -> Path:
    # Reuse the style ID validator but keep download snapshots in their own folder.
    reference_style.profile_path(key)
    folder = reference_style.directory() / 'downloads'
    folder.mkdir(exist_ok=True)
    return folder / f'{key}.json'


def save(state):
    path = path_for(state['id'])
    temp = path.with_suffix('.tmp')
    state['updated_at_s'] = time.time()
    temp.write_text(json.dumps(state), encoding='utf-8')
    temp.replace(path)


def positive(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 else None


def transfer_snapshot(event):
    """Numbers refer to the current yt-dlp stream, not the combined download."""
    total = positive(event.get('total_bytes') or event.get('total_bytes_estimate'))
    done = positive(event.get('downloaded_bytes')) or 0
    speed = positive(event.get('speed'))
    eta = positive(event.get('eta'))
    return dict(downloaded_bytes=done, total_bytes=total, speed_bps=speed, eta_s=eta,
        progress=min(1, done/total) if total else None,
        stream=Path(event.get('filename') or '').name)


async def run(state, settings):
    last_write = 0.0
    def activity(event):
        nonlocal last_write
        now = time.monotonic()
        if now-last_write < .5 and event.get('status') != 'finished':
            return
        last_write = now
        state.update(transfer_snapshot(event))
        state['message'] = ('Downloading current audio/video stream' if event.get('status') == 'downloading'
                            else 'Processing downloaded streams; more streams may follow')
        save(state)
    try:
        metadata = await asyncio.to_thread(long_video.register, state['url'], settings)
        if not 0 < metadata.duration_s <= 1200:
            raise ValueError('Reference must be at most 20 minutes.')
        state.update(message='Starting media download', title=metadata.title)
        save(state)
        source = await asyncio.to_thread(ingest.ingest_youtube, state['url'], settings, on_activity=activity)
        await asyncio.to_thread(store.create_source, source)
        state.update(status='done', message='Reference downloaded. Ready to analyse.', eta_s=None,
            finished_at_s=time.time(), source={'id':source.id,'title':source.title})
    except Exception as exc:
        state.update(status='failed', message=str(exc), eta_s=None, finished_at_s=time.time())
    finally:
        save(state)
        active.discard(state['id'])


@router.post('', status_code=202)
async def create(payload: DownloadIn, tasks: BackgroundTasks):
    if not ingest.is_youtube_url(payload.url):
        raise HTTPException(400, 'Use a YouTube video link.')
    if active:
        raise HTTPException(409, 'A reference download is already running. Wait for it to finish.')
    state = dict(id=new_id(), url=payload.url, status='running', message='Checking YouTube metadata',
        started_at_s=time.time(), progress=None, eta_s=None, downloaded_bytes=0,
        total_bytes=None, speed_bps=None, stream='')
    save(state)
    active.add(state['id'])
    tasks.add_task(run, state, config.load().ingest)
    return state


@router.get('/{download_id}')
async def get(download_id: str):
    try:
        state = json.loads(path_for(download_id).read_text(encoding='utf-8'))
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, 'Download not found.')
    if state['status'] == 'running' and download_id not in active:
        state.update(status='failed', message='Download interrupted by a server restart. Add the link again.',
                     finished_at_s=time.time(), eta_s=None)
        save(state)
    return state
