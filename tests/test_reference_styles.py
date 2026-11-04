import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from autoclip import config
from autoclip.app import create_app
from autoclip.db import store
from autoclip.db.models import Source
from autoclip.pipeline import reference_style as styles
from autoclip.pipeline.transcript import Transcript, Word
from autoclip.providers import detection_config
from autoclip.providers.base import render_window_prompt, TranscriptWindow


def test_measured_scene_cuts_from_real_video(tmp_path):
    path = tmp_path/'reference.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=red:s=160x90:r=10:d=1',
        '-f','lavfi','-i','color=blue:s=160x90:r=10:d=1','-filter_complex',
        '[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-c:v','libx264',str(path)], check=True)
    measured = styles.measure(path)
    assert measured['cut_count'] == 1
    assert measured['cut_times_s'][0] == pytest.approx(1,abs=.1)
    assert measured['median_shot_s'] == pytest.approx(1,abs=.1)


@pytest.mark.asyncio
async def test_analysis_cache_guidance_and_no_visual_claims(tmp_path, monkeypatch):
    media = tmp_path/'reference.mp4'; media.touch()
    monkeypatch.setattr(store,'get_source',lambda _: SimpleNamespace(path=str(media),title='Reference',url='https://youtube.com/example'))
    calls = []
    def measure(_):
        calls.append('measure')
        return dict(duration_s=60,width=1920,height=1080,cut_count=2,median_shot_s=20)
    monkeypatch.setattr(styles,'measure',measure)
    monkeypatch.setattr(styles.prepare,'extract_audio',lambda *a,**kw: None)
    def transcribe(*a,**kw):
        calls.append('transcribe')
        return Transcript(words=[Word('Why?',0,1),Word('Because.',59,60)])
    monkeypatch.setattr(styles.transcribe,'transcribe',transcribe)
    class Provider:
        async def _complete(self, system, payload, cfg):
            assert json.loads(payload)[0]['visual'] is None
            assert 'do not infer' in system
            return json.dumps(dict(guidance='Keep the question and its complete answer.',summary='Question and answer.',framing='split'))
    monkeypatch.setattr(styles,'build_provider',lambda **kw: Provider())
    profile = dict(id='a'*16,name='Example',source_ids=['s'],use_vision=False,reviewed=False)
    for _ in range(2):
        await styles.analyse(profile,config.Settings())
        assert profile['status'] == 'ready'
    assert calls == ['measure','transcribe']
    assert profile['recommendations']['ratio'] == '16:9'
    assert profile['recommendations']['framing'] == 'fit'
    assert not profile['reviewed']


def test_api_review_apply_snapshot_and_interrupt(monkeypatch,tmp_path):
    monkeypatch.setenv('AUTOCLIP_NO_WORKER','1')
    from autoclip.api import reference_styles as routes
    with TestClient(create_app()) as client:
        store.create_source(Source(id='s',type='upload',path=str(tmp_path/'media.mp4'),duration_s=60,has_video=True))
        profile = dict(id='b'*16,name='Style',status='ready',reviewed=False,guidance='Keep complete answers.',
            source_ids=['s'],use_vision=False,evidence=[],recommendations=styles.Recommendations().model_dump())
        styles.save(profile)
        assert client.post('/api/jobs',json={'source_id':'s','settings':{'reference_style_id':profile['id']}}).status_code == 422
        response = client.put('/api/reference-styles/'+profile['id'],json={k:profile[k] for k in ('name','guidance','recommendations')})
        assert response.status_code == 200 and response.json()['reviewed']
        response = client.post('/api/jobs',json={'source_id':'s','settings':{'reference_style_id':profile['id']}})
        assert response.status_code == 201
        saved = store.get_job(response.json()['id']).settings
        assert saved['clips']['reference_guidance'] == profile['guidance']
        cfg = detection_config(config.Settings.model_validate(saved))
        assert profile['guidance'] in render_window_prompt(TranscriptWindow('test',0,0),cfg)
        profile.update(status='analysing');styles.save(profile)
        assert client.get('/api/reference-styles/'+profile['id']).json()['status'] == 'failed'
        assert client.get('/api/reference-styles/not-an-id').status_code == 404
        assert client.post('/api/reference-styles',json={'name':'Style','source_ids':[]}).status_code == 422


def test_long_youtube_reference_rejected_before_download(monkeypatch):
    monkeypatch.setenv('AUTOCLIP_NO_WORKER','1')
    from autoclip.api import reference_styles as routes
    monkeypatch.setattr(routes.long_video,'register',lambda *a: SimpleNamespace(duration_s=10800))
    def download(*a): raise AssertionError('Full video must not download')
    monkeypatch.setattr(routes.ingest,'ingest_youtube',download)
    with TestClient(create_app()) as client:
        response = client.post('/api/reference-styles/youtube',json={'url':'https://www.youtube.com/watch?v=abcdefghijk'})
        assert response.status_code == 422 and '5 minutes' in response.text


@pytest.mark.asyncio
async def test_vision_sends_sampled_images_to_local_model(tmp_path,monkeypatch):
    calls = []
    def frame(args,**kwargs):
        Path(args[-1]).write_bytes(b'jpeg-sample')
    monkeypatch.setattr(styles.subprocess,'run',frame)
    class Client:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,json):
            calls.append((url,json))
            class Response:
                def raise_for_status(self): pass
                def json(self): return {'response':'{"captions":"lower white text","framing":"two speakers"}'}
            return Response()
    monkeypatch.setattr(styles.httpx,'AsyncClient',Client)
    result = await styles.visual_notes(tmp_path/'video.mp4',60,tmp_path,config.Settings())
    assert [v['time_s'] for v in result['sampled_frames']] == [6,30,54]
    assert len(calls) == 3
    assert all(payload['model'] == 'qwen2.5vl:3b' and payload['images'] and payload['keep_alive'] == 0 for _,payload in calls)


@pytest.mark.asyncio
async def test_failed_analysis_is_persisted_and_not_usable(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'get_source',lambda _: None)
    profile = dict(id='c'*16,name='Missing reference',source_ids=['missing'],use_vision=False,reviewed=False)
    await styles.analyse(profile,config.Settings())
    assert styles.load(profile['id'])['status'] == 'failed'
    assert 'missing' in profile['message'].lower()
