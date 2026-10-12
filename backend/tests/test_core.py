import copy
import xml.etree.ElementTree as ET
import mido
import pytest
from backend.domain import ScoreSettings, NoteEdit, seconds_to_beats, beats_to_seconds, apply_revision
from backend.ingestion import parse_youtube
from backend.midi_io import read_midi, write_midi
from backend.demo import make_demo

def test_time_mapping_with_tempo_changes():
    anchors=[{'time':0,'beat':0,'bpm':120},{'time':2,'beat':4,'bpm':60},{'time':5,'beat':7,'bpm':180}]
    for t in [-.5,0,.25,1.9,2,4.5,5,8.2]:
        assert beats_to_seconds(seconds_to_beats(t,anchors),anchors)==pytest.approx(t)

@pytest.mark.parametrize('url,stamp',[('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1m2s',62),('https://youtu.be/dQw4w9WgXcQ?t=15',15),('https://m.youtube.com/watch?v=dQw4w9WgXcQ&start=42',42)])
def test_youtube_normalization(url,stamp):
    result=parse_youtube(url)
    assert result['suggestedStart']==stamp
    assert result['url']=='https://www.youtube.com/watch?v=dQw4w9WgXcQ'

@pytest.mark.parametrize('url',['file:///x','https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ','https://youtube.com@127.0.0.1/watch?v=dQw4w9WgXcQ','https://youtu.be/no','https://youtube.com:443/watch?v=dQw4w9WgXcQ','https://127.0.0.1/media'])
def test_unsupported_sources_rejected(url):
    with pytest.raises(ValueError):parse_youtube(url)

def test_midi_simultaneous_repeated_notes_and_pedal(tmp_path):
    mid=mido.MidiFile(ticks_per_beat=480)
    track=mido.MidiTrack();mid.tracks.append(track)
    track.extend([mido.MetaMessage('set_tempo',tempo=500000),mido.Message('note_on',note=60,velocity=80),mido.Message('note_on',note=64,velocity=70),mido.Message('control_change',control=64,value=127),mido.Message('note_off',note=60,time=240),mido.Message('note_on',note=60,velocity=90),mido.Message('note_off',note=60,time=240),mido.Message('note_off',note=64),mido.Message('control_change',control=64,value=0)])
    path=tmp_path/'test.mid';mid.save(path)
    raw=read_midi(path)
    assert len(raw['notes'])==3
    assert [(n['start'],n['end']) for n in raw['notes'] if n['pitch']==60]==[(0,.25),(.25,.5)]
    assert [p['value'] for p in raw['pedals']]==[127,0]
    path.write_bytes(write_midi({'notes':raw['notes'],'raw':raw}))
    reread=read_midi(path)
    assert len(reread['notes'])==3
    assert reread['pedals']==raw['pedals']

def test_score_pickup_ties_and_raw_immutability():
    raw={'notes':[{'id':'test','pitch':60,'start':.03,'end':3.1,'velocity':80,'hand':'right'},{'id':'other','pitch':48,'start':.51,'end':1.1,'velocity':60,'hand':'left'}],'duration':4,'pedals':[],'tempos':[]}
    untouched=copy.deepcopy(raw)
    result=apply_revision({'raw':raw,'duration':4},ScoreSettings(tempo=120,downbeat=1).model_dump(),[])
    xml=ET.fromstring(result['score']['musicxml'])
    assert xml.tag=='score-partwise'
    assert len(xml.findall('.//tie'))>=2
    assert result['score']['measures'][0]['endBeat']==2
    assert raw==untouched
    assert result['notes'][0]['start']==.03
    assert len([f for f in result['score']['fragments'] if f['noteId']=='test'])>=2

def test_demo_and_export_validity(tmp_path):
    piece=make_demo()
    assert len(piece['score']['measures'])==16
    assert piece['raw']['provenance']['kind']=='demo'
    from music21 import converter
    parsed=converter.parseData(piece['score']['musicxml'],format='musicxml')
    assert len(parsed.parts)==2
    path=tmp_path/'demo.mid';path.write_bytes(write_midi(piece))
    imported=read_midi(path)
    assert len(imported['notes'])==len(piece['notes'])
    for a,b in zip(imported['notes'],sorted(piece['notes'],key=lambda n:(n['start'],n['pitch']))):
        assert a['pitch']==b['pitch']
        assert abs(a['start']-b['start'])<.001

def test_invalid_corrections():
    with pytest.raises(ValueError):NoteEdit(id='a',pitch=60,start=2,end=1,hand='right')
    with pytest.raises(ValueError):ScoreSettings(denominator=3)

@pytest.fixture
def client(tmp_path,monkeypatch):
    from backend import store,config,app as module
    monkeypatch.setattr(config,'DATA',tmp_path);monkeypatch.setattr(store,'DATA',tmp_path);monkeypatch.setattr(module,'DATA',tmp_path)
    monkeypatch.setattr(module,'fetch_youtube_title',lambda url: None)
    from fastapi.testclient import TestClient
    with TestClient(module.app) as client:yield client

def test_job_failure_retry_cancel(client):
    source=client.post('/api/sources/youtube',json={'url':'https://youtu.be/dQw4w9WgXcQ'}).json()
    assert client.post('/api/jobs',json={'sourceId':source['id'],'start':3,'end':1}).status_code==422
    result=client.post('/api/jobs',json={'sourceId':source['id'],'start':0,'end':10});assert result.status_code==202
    job=result.json()
    assert client.post('/api/jobs/'+job['id']+'/retry').status_code==409
    assert client.post('/api/jobs/'+job['id']+'/cancel').json()['cancel']==1
    from backend import store
    with store.db() as conn:conn.execute("UPDATE jobs SET status='failed',error='A real failure' WHERE id=?",(job['id'],))
    retry=client.post('/api/jobs/'+job['id']+'/retry');assert retry.status_code==202
    assert retry.json()['id']!=job['id']
    assert retry.json()['request']==job['request']

def test_upload_and_piece_roundtrip(client):
    result=client.post('/api/sources/upload',files={'file':('study.mid',write_midi(make_demo()),'audio/midi')})
    assert result.status_code==200,result.text
    piece=result.json()['piece'];original=copy.deepcopy(piece['raw']);n=piece['notes'][0]
    result=client.post(f"/api/pieces/{piece['id']}/revisions",json={'settings':piece['settings'],'edits':[{**n,'pitch':n['pitch']+1}]})
    assert result.status_code==200,result.text
    assert result.json()['raw']==original
    assert client.get(f"/api/pieces/{piece['id']}/export/midi").content.startswith(b'MThd')
    assert client.get(f"/api/pieces/{piece['id']}/export/musicxml").status_code==200
    assert client.get('/api/pieces').json()[0]['id']==piece['id']
    assert client.post('/api/sources/upload',files={'file':('bad.mid',b'not-midi','audio/midi')}).status_code==422

def test_invalid_audio_and_size(client,monkeypatch):
    assert client.post('/api/sources/upload',files={'file':('bad.wav',b'not-a-wave','audio/wav')}).status_code==422
    from backend import app as module
    monkeypatch.setattr(module,'MAX_BYTES',4)
    assert client.post('/api/sources/upload',files={'file':('big.wav',b'12345','audio/wav')}).status_code==413

def test_musicxml_against_official_schema():
    assert_valid_musicxml(make_demo()['score']['musicxml'])


def assert_valid_musicxml(musicxml):
    from pathlib import Path
    from lxml import etree
    directory=Path(__file__).parent/'schemas'
    class LocalSchema(etree.Resolver):
        def resolve(self,url,pubid,context):
            target=directory/url.rsplit('/',1)[-1]
            return self.resolve_filename(str(target),context) if target.exists() else None
    parser=etree.XMLParser(no_network=True,resolve_entities=False)
    parser.resolvers.add(LocalSchema())
    schema=etree.XMLSchema(etree.parse(str(directory/'musicxml.xsd'),parser))
    score=etree.fromstring(musicxml.encode(),parser)
    assert schema.validate(score),str(schema.error_log)

def test_subprocess_model_failure_is_persisted(client,tmp_path):
    import os,subprocess,sys,wave
    path=tmp_path/'valid.wav'
    with wave.open(str(path),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(22050);wav.writeframes(b'\x00\x00'*22050)
    result=client.post('/api/sources/upload',files={'file':('valid.wav',path.read_bytes(),'audio/wav')})
    assert result.status_code==200,result.text
    job=client.post('/api/jobs',json={'sourceId':result.json()['id'],'start':0,'end':.5}).json()
    env={**os.environ,'PIANO_DATA_DIR':str(tmp_path),
         'PIANO_MODEL_PYTHON':str(tmp_path/'missing-python.exe'),
         'PIANO_CRNN_PYTHON':str(tmp_path/'missing-piano-python.exe')}
    process=subprocess.run([sys.executable,'-m','backend.pipeline',job['id']],env=env,capture_output=True,timeout=30)
    assert process.returncode!=0
    failed=client.get('/api/jobs/'+job['id']).json()
    assert failed['status']=='failed'
    assert 'not installed' in failed['error']

def test_manual_downbeat_maps_to_grid_without_changing_note_time():
    from backend.domain import tempo_map
    settings=ScoreSettings(tempo=120,downbeat=1.333).model_dump()
    anchors=tempo_map(settings,{})
    assert seconds_to_beats(1.333,anchors)==pytest.approx(2.75)
    assert beats_to_seconds(2.75,anchors)==pytest.approx(1.333)


def test_tied_and_fresh_notes_with_identical_offset_and_duration():
    # At beat 4, C has a tie stop, E a tie continue, and G a new attack.
    # All three have the same offset and length in this measure.
    notes = [{'id': ident, 'pitch': pitch, 'start': start, 'end': end, 'hand': 'right'}
             for ident, pitch, start, end in [('stop', 60, 3, 8), ('continue', 64, 3, 9), ('fresh', 67, 4, 8)]]
    raw = {'notes': notes, 'duration': 9}
    piece = apply_revision({'raw': raw}, ScoreSettings(tempo=60).model_dump(), [])
    xml = ET.fromstring(piece['score']['musicxml'])
    assert {t.attrib['type'] for t in xml.findall('.//tie')} == {'start', 'stop'}
    fragments = [f for f in piece['score']['fragments'] if f['measure'] == 1]
    assert {f['noteId'] for f in fragments} == {'stop', 'continue', 'fresh'}
    assert all(f['beat'] == 4 and f['endBeat'] == 8 for f in fragments)
    from music21 import converter
    parsed = converter.parseData(piece['score']['musicxml'], format='musicxml')
    assert len(parsed.parts) == 2


def test_complex_durations_have_unique_xml_ids_and_preserve_fragment_links():
    notes = [{'id': 'long', 'pitch': 60, 'start': 0, 'end': 1.25, 'hand': 'right'},
             {'id': 'chord-a', 'pitch': 64, 'start': 2, 'end': 4.5, 'hand': 'right'},
             {'id': 'chord-b', 'pitch': 67, 'start': 2, 'end': 4.5, 'hand': 'right'}]
    piece = apply_revision({'raw': {'notes': notes, 'duration': 5}}, ScoreSettings(tempo=60).model_dump(), [])
    xml = ET.fromstring(piece['score']['musicxml'])
    ids = [n.get('id') for n in xml.findall('.//note[@id]')]
    assert len(ids) == len(set(ids))
    assert any(len(f['xmlIds']) > 1 for f in piece['score']['fragments'])
    assert all(set(f['xmlIds']).issubset(ids) for f in piece['score']['fragments'])
    assert_valid_musicxml(piece['score']['musicxml'])


def transcription_fixture():
    notes = [{'id': ident, 'pitch': pitch, 'start': start, 'end': end, 'velocity': velocity, 'hand': 'right'}
             for ident, pitch, start, end, velocity in [
                 ('clear', 60, 0, .5, 80), ('weak-attack', 72, .1, .4, 60),
                 ('quiet-clear', 64, .6, 1.1, 40), ('short-weak', 67, 1.2, 1.35, 40),
                 ('fast-clear', 69, 1.5, 1.65, 80), ('borderline', 65, 2, 2.5, 65)]]
    return {'id': 'cleanup-test', 'title': 'Cleanup test', 'raw': {'notes': notes, 'duration': 3,
            'provenance': {'kind': 'transcription'}, 'pedals': []},
            'noteEvidence': {n['id']: {'onset': .9 if n['id'] not in ('weak-attack','borderline') else
                                     .4 if n['id'] == 'weak-attack' else .65} for n in notes}}


def test_cleanup_is_reversible_preserves_quiet_attacks_and_manual_corrections():
    original = transcription_fixture()
    untouched = copy.deepcopy(original)
    settings = ScoreSettings().model_dump()
    balanced = apply_revision(original, settings, [])
    assert set(balanced['cleanup']['hiddenNoteIds']) == {'weak-attack', 'short-weak'}
    assert {n['id'] for n in balanced['notes']} >= {'quiet-clear', 'fast-clear'}
    strong = apply_revision(balanced, {**settings, 'cleanup': 'strong'}, [])
    assert set(strong['cleanup']['hiddenNoteIds']) == {'weak-attack', 'short-weak', 'borderline'}
    restored = apply_revision(strong, {**settings, 'cleanup': 'off'}, [])
    assert restored['notes'] == original['raw']['notes']
    correction = {**original['raw']['notes'][1], 'pitch': 71}
    corrected = apply_revision(balanced, settings, [correction])
    assert next(n for n in corrected['notes'] if n['id'] == correction['id'])['pitch'] == 71
    deleted = apply_revision(corrected, settings, [{**correction, 'deleted': True}])
    assert correction['id'] not in {n['id'] for n in deleted['notes']}
    assert original == untouched
    assert all(p['raw'] == untouched['raw'] for p in (balanced, strong, restored, corrected, deleted))


def test_cleanup_does_not_filter_midi_and_handles_older_transcriptions():
    from backend.cleanup import clean_notes
    p = transcription_fixture()
    # Older saved pieces without attack evidence still get gentle short/weak filtering.
    _, summary = clean_notes(p['raw'], p['raw']['notes'], [], 'balanced')
    assert summary['hiddenNoteIds'] == ['short-weak']
    p['raw']['provenance']['kind'] = 'midi'
    kept, summary = clean_notes(p['raw'], p['raw']['notes'], [], 'strong', p['noteEvidence'])
    assert kept == p['raw']['notes']
    assert summary['profile'] == 'off'
    with pytest.raises(ValueError):
        ScoreSettings(cleanup='unknown')


def test_cleanup_revision_and_exports_use_same_notes(client, tmp_path):
    from backend import store
    p = transcription_fixture()
    store.piece_save(p)
    response = client.post('/api/pieces/cleanup-test/revisions', json={'settings': ScoreSettings().model_dump(), 'edits': []})
    assert response.status_code == 200, response.text
    piece = response.json()
    assert len(piece['notes']) == 4
    assert piece['raw'] == p['raw']
    assert {f['noteId'] for f in piece['score']['fragments']} == {n['id'] for n in piece['notes']}
    path = tmp_path/'cleaned.mid'
    path.write_bytes(client.get('/api/pieces/cleanup-test/export/midi').content)
    assert len(read_midi(path)['notes']) == 4
    restored = client.post('/api/pieces/cleanup-test/revisions', json={'settings': {**piece['settings'], 'cleanup': 'off'}, 'edits': []})
    assert len(restored.json()['notes']) == 6


def test_score_failure_has_actionable_error_and_keeps_saved_piece(client, monkeypatch):
    from backend import store, app as module
    piece = make_demo()
    store.piece_save(piece)
    def fail(*args):
        raise TypeError('deliberate score failure')
    monkeypatch.setattr(module, 'apply_revision', fail)
    response = client.post('/api/pieces/demo/revisions', json={'settings': piece['settings'], 'edits': []})
    assert response.status_code == 500
    assert 'Could not generate the score' in response.json()['detail']
    assert client.get('/api/pieces/demo').json() == piece
    with store.db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM revisions').fetchone()[0] == 0
    assert client.post('/api/pieces/missing/revisions', json={'settings': piece['settings']}).status_code == 404


def test_delete_piece_removes_only_its_own_data(client):
    import json,time
    from backend import store
    first = {**make_demo(), 'id': 'delete-me', 'title': 'Delete me'}
    other = {**first, 'id': 'keep-me', 'title': 'Keep me'}
    for piece in (first, other):
        store.piece_save(piece)
        folder = store.DATA/'pieces'/piece['id']
        folder.mkdir()
        (folder/'raw.json').write_text(json.dumps(piece['raw']))
        (folder/'source.wav').write_bytes(b'practice audio')
    shared = {'id': 'shared-source', 'kind': 'upload', 'title': 'Shared recording'}
    store.source_save(shared)
    source_file = store.DATA/'sources'/'shared.wav'
    source_file.write_bytes(b'original shared recording')
    job = client.post('/api/jobs', json={'sourceId': shared['id']}).json()
    with store.db() as conn:
        conn.execute('INSERT INTO revisions VALUES (?,?,?,?)', ('revision1', first['id'], '{}', time.time()))
        conn.execute('INSERT INTO revisions VALUES (?,?,?,?)', ('revision2', other['id'], '{}', time.time()))
        conn.execute("UPDATE jobs SET status='completed',piece_id=? WHERE id=?", (first['id'], job['id']))
    response = client.delete('/api/pieces/delete-me')
    assert response.status_code == 200, response.text
    assert response.json() == {'id': 'delete-me', 'deleted': True, 'filesPending': False}
    assert client.get('/api/pieces/delete-me').status_code == 404
    assert client.get('/api/pieces/delete-me/media').status_code == 404
    assert client.get('/api/pieces/delete-me/export/midi').status_code == 404
    assert not (store.DATA/'pieces'/'delete-me').exists()
    assert (store.DATA/'pieces'/'keep-me'/'source.wav').read_bytes() == b'practice audio'
    assert store.piece_get('keep-me') == other
    assert store.source_get('shared-source') == shared
    assert source_file.exists()
    assert store.job_get(job['id'])['piece_id'] is None
    assert {p['id'] for p in client.get('/api/pieces').json()} == {'keep-me'}
    with store.db() as conn:
        assert conn.execute('SELECT piece_id FROM revisions').fetchall()[0]['piece_id'] == 'keep-me'
        assert conn.execute('SELECT COUNT(*) FROM pending_piece_deletions').fetchone()[0] == 0
    assert client.delete('/api/pieces/delete-me').status_code == 404
    assert client.delete('/api/pieces/demo').status_code == 403
    assert client.get('/api/pieces/demo').status_code == 200


def test_delete_locked_files_are_retried_without_restoring_piece(client, monkeypatch):
    from backend import store,library
    p = {**make_demo(), 'id': 'locked-piece'}
    store.piece_save(p)
    folder = store.DATA/'pieces'/p['id']
    folder.mkdir()
    (folder/'source.wav').write_bytes(b'locked audio')
    with monkeypatch.context() as m:
        def locked(*args):
            raise PermissionError('File is in use')
        m.setattr(library.shutil, 'rmtree', locked)
        response = client.delete('/api/pieces/locked-piece')
    assert response.status_code == 200
    assert response.json()['filesPending']
    assert store.piece_get(p['id']) is None
    assert folder.exists()
    library.retry_file_deletions()
    assert not folder.exists()
    with store.db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pending_piece_deletions').fetchone()[0] == 0


def test_deletion_rolls_back_database_if_transaction_fails(client):
    import sqlite3
    from backend import store,library
    p = {**make_demo(), 'id': 'transaction-piece'}
    store.piece_save(p)
    folder = store.DATA/'pieces'/p['id']
    folder.mkdir()
    (folder/'raw.json').write_text('original')
    with store.db() as conn:
        conn.execute("CREATE TRIGGER block_deletion BEFORE DELETE ON pieces BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        library.delete_piece(p['id'])
    assert store.piece_get(p['id']) == p
    assert (folder/'raw.json').read_text() == 'original'


def test_late_revision_cannot_resurrect_deleted_piece(client, monkeypatch):
    from backend import store,app as module,library
    p = {**make_demo(), 'id': 'racing-piece'}
    store.piece_save(p)
    real_apply = module.apply_revision
    def overlapping_revision(*args):
        result = real_apply(*args)
        library.delete_piece(p['id'])
        return result
    monkeypatch.setattr(module, 'apply_revision', overlapping_revision)
    response = client.post('/api/pieces/racing-piece/revisions', json={'settings': p['settings'], 'edits': []})
    assert response.status_code == 404
    assert store.piece_get(p['id']) is None
    with store.db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM revisions').fetchone()[0] == 0


def test_delete_rejects_paths_outside_piece_storage(client):
    from backend.library import piece_directory
    for ident in ('..', '../sources', 'C:\\outside', '/outside', 'demo'):
        with pytest.raises(ValueError):
            piece_directory(ident)
