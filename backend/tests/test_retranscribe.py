import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.domain import ScoreSettings


@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend import app as module, config, store
    monkeypatch.setattr(config, 'DATA', tmp_path)
    monkeypatch.setattr(store, 'DATA', tmp_path)
    monkeypatch.setattr(module, 'DATA', tmp_path)
    monkeypatch.setattr(module, 'get_adapter', lambda: SimpleNamespace(available=lambda: True, name='piano-crnn'))
    from fastapi.testclient import TestClient
    with TestClient(module.app) as client:
        yield client


@pytest.fixture
def saved_piece(client):
    from backend import store
    p = {'id': 'recording123', 'title': 'A saved recording', 'duration': 6,
         'clipStart': 10, 'source': {'kind': 'youtube', 'videoId': 'pMU3_1VbRn0', 'mediaClip': True},
         'raw': {'notes': [{'id': 'n0', 'pitch': 60, 'start': 0, 'end': 1}],
                 'duration': 5, 'provenance': {'kind': 'transcription'}},
         'edits': [{'id': 'n0', 'pitch': 61, 'start': 0, 'end': 6, 'hand': 'right'}],
         'settings': ScoreSettings().model_dump()}
    store.piece_save(p)
    directory = store.DATA/'pieces'/p['id']
    directory.mkdir()
    (directory/'source.wav').write_bytes(b'saved source audio')
    (directory/'raw.json').write_text(json.dumps(p['raw']))
    return p


def queued_count():
    from backend import store
    with store.db() as conn:
        return conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]


def test_retranscription_snapshots_original_audio_and_preserves_edits(client, saved_piece):
    from backend import store
    settings = ScoreSettings(tempo=88, numerator=3, cleanup='off', downbeat=.4).model_dump()
    untouched = copy.deepcopy(saved_piece)
    response = client.post(f"/api/pieces/{saved_piece['id']}/transcriptions", json={'settings': settings})
    assert response.status_code == 202, response.text
    job = response.json()
    assert job['status'] == 'queued'
    assert job['request'] == {'sourceId': job['source_id'], 'start': 0, 'end': 5, 'settings': settings}
    source = store.source_get(job['source_id'])
    assert source['kind'] == 'saved-audio'
    assert source['originalSource'] == saved_piece['source']
    assert source['clipStart'] == 10
    assert source['sourcePieceId'] == saved_piece['id']
    assert source['duration'] == 5  # Edited note length is not the audio duration.
    assert source['title'] == 'A saved recording (new transcription)'
    snapshot = Path(source['path'])
    assert snapshot.parent == store.DATA/'sources'
    assert snapshot.read_bytes() == b'saved source audio'
    assert store.piece_get(saved_piece['id']) == untouched
    assert json.loads((store.DATA/'pieces'/saved_piece['id']/'raw.json').read_text()) == untouched['raw']
    with store.db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM revisions').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM pieces').fetchone()[0] == 1
    # A queued transcription survives removal of its original library entry.
    assert client.delete(f"/api/pieces/{saved_piece['id']}").status_code == 200
    assert snapshot.read_bytes() == b'saved source audio'
    assert store.job_get(job['id'])['status'] == 'queued'


def test_retry_and_normal_jobs_preserve_optional_score_settings(client, saved_piece):
    from backend import store
    settings = ScoreSettings(tempo=75, cleanup='strong').model_dump()
    job = client.post(f"/api/pieces/{saved_piece['id']}/transcriptions", json={'settings': settings}).json()
    with store.db() as conn:
        conn.execute("UPDATE jobs SET status='failed' WHERE id=?", (job['id'],))
    retry = client.post('/api/jobs/'+job['id']+'/retry')
    assert retry.status_code == 202
    assert retry.json()['request'] == job['request']
    normal = client.post('/api/jobs', json={'sourceId': job['source_id'], 'settings': settings})
    assert normal.status_code == 202
    assert normal.json()['request']['settings'] == settings


def test_retranscription_rejects_demo_midi_missing_audio_and_model(client, saved_piece, monkeypatch):
    from backend import app as module, store
    body = {'settings': saved_piece['settings']}
    assert client.post('/api/pieces/demo/transcriptions', json=body).status_code == 409
    midi = {**saved_piece, 'id': 'midi123', 'source': {'kind': 'midi'}}
    store.piece_save(midi)
    assert client.post('/api/pieces/midi123/transcriptions', json=body).status_code == 409
    assert client.post('/api/pieces/missing123/transcriptions', json=body).status_code == 404
    monkeypatch.setattr(module, 'get_adapter', lambda: SimpleNamespace(available=lambda: False, name='piano-crnn'))
    response = client.post(f"/api/pieces/{saved_piece['id']}/transcriptions", json=body)
    assert response.status_code == 409
    assert 'not installed' in response.json()['detail']
    (store.DATA/'pieces'/saved_piece['id']/'source.wav').unlink()
    response = client.post(f"/api/pieces/{saved_piece['id']}/transcriptions", json=body)
    assert response.status_code == 404
    assert 'Import' in response.json()['detail']
    assert queued_count() == 0


def test_retranscription_bounds_title_and_strips_private_source_path(client, saved_piece):
    from backend import store
    saved_piece['title'] = 'Long ' * 40
    saved_piece['source']['path'] = 'private-acquisition-path'
    store.piece_save(saved_piece)
    job = client.post(f"/api/pieces/{saved_piece['id']}/transcriptions", json={'settings': saved_piece['settings']}).json()
    source = store.source_get(job['source_id'])
    assert len(source['title']) == 160
    assert source['title'].endswith(' (new transcription)')
    assert 'path' not in source['originalSource']


def test_failed_transaction_rolls_back_source_job_and_audio_snapshot(client, saved_piece):
    from backend import store
    with store.db() as conn:
        conn.execute("CREATE TRIGGER reject_job BEFORE INSERT ON jobs BEGIN SELECT RAISE(ABORT, 'simulated job failure'); END")
    response = client.post(f"/api/pieces/{saved_piece['id']}/transcriptions", json={'settings': saved_piece['settings']})
    assert response.status_code == 500
    assert 'unchanged' in response.json()['detail']
    assert queued_count() == 0
    with store.db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM sources').fetchone()[0] == 0
    assert list((store.DATA/'sources').iterdir()) == []
    assert store.piece_get(saved_piece['id']) == saved_piece


def test_partial_copy_failure_removes_only_snapshot(client, saved_piece, monkeypatch):
    from backend import app as module, store
    def partial(source, destination):
        Path(destination).write_bytes(b'partial')
        raise PermissionError('test locked file')
    monkeypatch.setattr(module.shutil, 'copyfile', partial)
    response = client.post(f"/api/pieces/{saved_piece['id']}/transcriptions", json={'settings': saved_piece['settings']})
    assert response.status_code == 409
    assert queued_count() == 0
    assert list((store.DATA/'sources').iterdir()) == []
    assert (store.DATA/'pieces'/saved_piece['id']/'source.wav').read_bytes() == b'saved source audio'


def test_deletion_during_snapshot_does_not_queue_stale_piece(client, saved_piece, monkeypatch):
    from backend import app as module, store
    real_copy = module.shutil.copyfile
    def deleting_copy(source, destination):
        real_copy(source, destination)
        with store.db() as conn:
            conn.execute('DELETE FROM pieces WHERE id=?', (saved_piece['id'],))
    monkeypatch.setattr(module.shutil, 'copyfile', deleting_copy)
    response = client.post(f"/api/pieces/{saved_piece['id']}/transcriptions", json={'settings': saved_piece['settings']})
    assert response.status_code == 404
    assert queued_count() == 0
    assert list((store.DATA/'sources').iterdir()) == []


def test_retranscription_rejects_invalid_ids_and_resolved_paths(client, saved_piece, monkeypatch):
    from backend import app as module, store
    body = {'settings': saved_piece['settings']}
    assert client.post('/api/pieces/bad-id/transcriptions', json=body).status_code == 400
    real_resolve = Path.resolve
    def outside(path, *args, **kwargs):
        resolved = real_resolve(path, *args, **kwargs)
        if path.name == 'source.wav':
            return store.DATA/'outside.wav'
        return resolved
    monkeypatch.setattr(Path, 'resolve', outside)
    response = client.post(f"/api/pieces/{saved_piece['id']}/transcriptions", json=body)
    assert response.status_code == 400
    assert queued_count() == 0


def test_health_reports_selected_engine_availability(client):
    result = client.get('/api/health').json()
    assert result['model'] is True
    assert result['engine'] == 'piano-crnn'
