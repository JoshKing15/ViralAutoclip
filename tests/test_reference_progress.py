import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
from autoclip.app import create_app
from autoclip.api import reference_downloads as downloads
from autoclip.db.models import Source
from autoclip.pipeline import ingest


def test_transfer_progress_handles_unknown_and_separate_streams():
    unknown = downloads.transfer_snapshot({'downloaded_bytes':123})
    assert unknown['progress'] is None and unknown['eta_s'] is None
    known = downloads.transfer_snapshot({'downloaded_bytes':50,'total_bytes':100,'speed':10,'eta':5})
    assert known['progress'] == .5 and known['eta_s'] == 5
    next_stream = downloads.transfer_snapshot({'downloaded_bytes':5,'total_bytes':50})
    assert next_stream['progress'] == .1
    invalid = downloads.transfer_snapshot({'speed':float('nan'),'eta':-1})
    assert invalid['speed_bps'] is None and invalid['eta_s'] is None


def test_background_import_has_progress_and_persists_completion(monkeypatch,tmp_path):
    monkeypatch.setenv('AUTOCLIP_NO_WORKER','1')
    monkeypatch.setattr(downloads.long_video,'register',lambda *a: SimpleNamespace(duration_s=90,title='Test reference'))
    def fetch(url,settings,on_activity):
        on_activity({'status':'downloading','downloaded_bytes':50,'total_bytes':100,'speed':10,'eta':5})
        on_activity({'status':'finished','downloaded_bytes':100,'total_bytes':100})
        return Source(id='downloaded',type='youtube',path=str(tmp_path/'clip.mp4'),title='Test reference',duration_s=90)
    monkeypatch.setattr(downloads.ingest,'ingest_youtube',fetch)
    with TestClient(create_app()) as client:
        response = client.post('/api/reference-downloads',json={'url':'https://www.youtube.com/watch?v=abcdefghijk'})
        assert response.status_code == 202
        state = client.get('/api/reference-downloads/'+response.json()['id']).json()
        assert state['status'] == 'done' and state['source']['id'] == 'downloaded'
        assert state['progress'] == 1 and state['eta_s'] is None
        assert state['finished_at_s'] >= state['started_at_s']
    assert not downloads.active


def test_failed_import_and_interrupted_download_are_visible(monkeypatch):
    monkeypatch.setenv('AUTOCLIP_NO_WORKER','1')
    def fail(*a): raise ingest.IngestError('YouTube blocked the download')
    monkeypatch.setattr(downloads.long_video,'register',fail)
    with TestClient(create_app()) as client:
        response = client.post('/api/reference-downloads',json={'url':'https://www.youtube.com/watch?v=abcdefghijk'})
        state = client.get('/api/reference-downloads/'+response.json()['id']).json()
        assert state['status'] == 'failed' and 'blocked' in state['message']
        downloads.save(dict(id='f'*16,status='running',started_at_s=time.time()))
        state = client.get('/api/reference-downloads/'+'f'*16).json()
        assert state['status'] == 'failed' and 'restart' in state['message']
        assert client.get('/api/reference-downloads/invalid').status_code == 404
