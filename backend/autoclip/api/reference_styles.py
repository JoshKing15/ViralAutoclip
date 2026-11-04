"""Reference style analysis, persistence and review."""
import asyncio
import time
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from .. import config
from ..db import store
from ..db.models import new_id
from ..pipeline import reference_style as styles, ingest, long_video

router = APIRouter(prefix='/api/reference-styles', tags=['reference styles'])
active: set[str] = set()


class CreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    source_ids: list[str] = Field(min_length=1, max_length=5)
    use_vision: bool = False


class EditIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    guidance: str = Field(min_length=1, max_length=1500)
    recommendations: styles.Recommendations


class URLIn(BaseModel):
    url: str = Field(max_length=2048)


def get_profile(style_id: str) -> dict:
    try:
        profile = styles.load(style_id)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, 'Style not found.')
    if profile['status'] == 'analysing' and style_id not in active:
        profile.update(status='failed', finished_at_s=time.time(), message='Analysis was interrupted. Retry to reuse completed work.')
        styles.save(profile)
    return profile


@router.get('')
async def list_styles():
    return [get_profile(path.stem) for path in styles.directory().glob('*.json')]


@router.post('/youtube')
async def import_youtube(payload: URLIn):
    if not ingest.is_youtube_url(payload.url):
        raise HTTPException(400, 'Use a YouTube video link.')
    settings = config.load().ingest
    try:
        metadata = await asyncio.to_thread(long_video.register, payload.url, settings)
        if not 0 < metadata.duration_s <= 1200:
            raise ValueError('Use a finished clip up to 20 minutes, not a full podcast episode.')
        source = await asyncio.to_thread(ingest.ingest_youtube, payload.url, settings)
        await asyncio.to_thread(store.create_source, source)
        return {'id': source.id, 'title': source.title, 'duration_s': source.duration_s}
    except (ingest.IngestError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


async def run(profile, settings):
    try:
        await styles.analyse(profile, settings)
    finally:
        active.discard(profile['id'])


def start(profile, tasks):
    if active:
        raise HTTPException(409, 'Another reference analysis is running. Wait for it to finish.')
    profile.update(status='analysing', reviewed=False, message='Starting reference analysis',
                   started_at_s=time.time(), finished_at_s=None, updated_at_s=time.time())
    active.add(profile['id'])
    styles.save(profile)
    tasks.add_task(run, profile, config.load())
    return profile


@router.post('', status_code=202)
async def create_style(payload: CreateIn, tasks: BackgroundTasks):
    ids = list(dict.fromkeys(payload.source_ids))
    for source_id in ids:
        source = await asyncio.to_thread(store.get_source, source_id)
        if source is None:
            raise HTTPException(404, 'Reference source not found.')
        if not 0 < source.duration_s <= 1200 or not source.has_video:
            raise HTTPException(422, 'References must be finished video clips up to 20 minutes.')
    profile = dict(id=new_id(), name=payload.name.strip(), source_ids=ids,
                   use_vision=payload.use_vision, evidence=[], guidance='', summary='', recommendations={})
    return start(profile, tasks)


@router.get('/{style_id}')
async def get_style(style_id: str):
    return get_profile(style_id)


@router.post('/{style_id}/retry', status_code=202)
async def retry_style(style_id: str, tasks: BackgroundTasks):
    profile = get_profile(style_id)
    if profile['status'] != 'failed':
        raise HTTPException(409, 'Only failed analyses can be retried.')
    return start(profile, tasks)


@router.put('/{style_id}')
async def edit_style(style_id: str, payload: EditIn):
    profile = get_profile(style_id)
    if profile['status'] != 'ready':
        raise HTTPException(409, 'Wait for a successful analysis before editing.')
    if payload.recommendations.min_duration_s >= payload.recommendations.max_duration_s:
        raise HTTPException(422, 'Minimum length must be below maximum.')
    profile.update(**payload.model_dump(), reviewed=True)
    styles.save(profile)
    return profile
