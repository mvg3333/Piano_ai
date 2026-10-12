import copy
import json
import time

import mido
import pytest

from backend.arrangement import ArrangementSettings, Guidance, analyze, arrange, fingerprint
from backend.domain import ScoreSettings, apply_revision
from backend.midi_io import read_midi, write_midi


def note(ident, pitch, start, end, hand='right', velocity=85):
    return dict(id=ident, pitch=pitch, start=start, end=end, hand=hand, velocity=velocity, channel=0)


def fixture():
    notes = []
    for i, pitch in enumerate([60, 62, 64, 65, 67, 65, 64, 60]):
        t = i*.6
        notes.append(note(f'm{i}', pitch, t, t+.54))
        for j, bass in enumerate(([36, 43, 48] if i < 4 else [41, 48, 53])):
            notes.append(note(f'a{i}-{j}', bass, t+j*.18, t+j*.18+.16, 'left', 60))
        if i >= 2:
            notes.append(note(f'upper{i}', pitch+24, t, t+.10, velocity=58))
        if i in (0, 4):
            notes.append(note(f'octave{i}', pitch+12, t, t+.54, velocity=70))
    raw = {'notes': sorted(notes, key=lambda n: (n['start'], n['pitch'], n['id'])), 'duration': 6,
           'pedals': [{'time': .1, 'value': 127, 'channel': 0}, {'time': 5, 'value': 0, 'channel': 0}],
           'tempos': [{'time': 0, 'bpm': 100}], 'provenance': {'kind': 'midi'}}
    return apply_revision({'id': 'arrangementfixture', 'title': 'Arrangement fixture', 'source': {'kind': 'midi'}, 'clipStart': 12,
                           'raw': raw, 'guidance': Guidance().model_dump()}, ScoreSettings(tempo=100).model_dump(), [])


def settings(level='beginner'):
    return {h: {'level': level, 'maxNotes': (2 if h == 'left' else 3) if level == 'easy' else 1,
                'maxSpan': 7, 'activity': 'light' if level == 'easy' else 'none' if level == 'melody' else 'changes'} for h in ('left', 'right')}


@pytest.mark.parametrize('level', ['melody', 'beginner', 'easy', 'full'])
def test_presets_preserve_source_melody_timeline_and_provenance(level):
    piece = fixture()
    before = copy.deepcopy(piece)
    result = arrange(piece, settings(level))
    view = result['performance']
    assert piece == before
    assert view['duration'] == 6 and view['clipStart'] == 12
    assert view['score']['anchors'] == piece['score']['anchors']
    assert view['score']['measures'] == piece['score']['measures']
    assert view['pedals'] == piece['raw']['pedals']
    by_id = {n['id']: n for n in view['notes']}
    for original in piece['notes']:
        if original['id'].startswith('m'):
            assert by_id[original['id']] == original
    assert set(result['sourceNoteMap']) == set(by_id)
    assert all(ids and set(ids) <= {n['id'] for n in piece['notes']} for ids in result['sourceNoteMap'].values())
    if level == 'full':
        assert view['notes'] == piece['notes']
        assert view['score'] == piece['score']
        assert result['operations'] == []
    else:
        assert len(view['notes']) < len(piece['notes'])
        assert 'upper2' not in by_id
        assert 'octave0' not in by_id
        if level == 'melody':
            assert set(by_id) == {f'm{i}' for i in range(8)}
        for hand in ('left', 'right'):
            assert result['metrics']['after'][hand]['maxSimultaneous'] <= settings(level)[hand]['maxNotes']
            assert result['metrics']['after'][hand]['maxSpan'] <= 7
    from backend.tests.test_core import assert_valid_musicxml
    assert_valid_musicxml(view['score']['musicxml'])


def test_protection_manual_roles_crossed_hands_and_limits():
    piece = fixture()
    piece['guidance'] = {'roles': {'m1': 'accompaniment', 'upper2': 'melody'}, 'protectedNoteIds': ['m0', 'octave0', 'm1']}
    piece['notes'][0]['hand'] = 'right'
    result = arrange(piece, settings('melody'))
    by_id = {n['id']: n for n in result['performance']['notes']}
    for ident in ('m0', 'octave0', 'm1', 'upper2'):
        assert by_id[ident] == next(n for n in piece['notes'] if n['id'] == ident)
    assert any(f['code'] == 'melodyExceedsLimits' for f in result['reviewFlags'])


def test_mixed_hands_and_deleted_protection():
    piece = fixture()
    piece['guidance']['protectedNoteIds'] = ['deleted-note']
    cfg = settings('melody')
    cfg['left']['level'] = 'full'
    result = arrange(piece, cfg)
    assert [n for n in result['performance']['notes'] if n['hand'] == 'left'] == [n for n in piece['notes'] if n['hand'] == 'left']
    assert any(f['code'] == 'protectedUnavailable' for f in result['reviewFlags'])


def test_ornaments_repeated_accents_and_melody_changing_hands():
    piece = fixture()
    rows = [note('theme1', 60, .1, .6), note('run1', 62, .61, .67, velocity=55),
            note('run2', 64, .69, .75, velocity=55), note('theme2', 65, .8, 1.3),
            note('repeat', 65, 1.45, 1.95), note('lower1', 57, 3, 3.5, 'left'),
            note('lower2', 59, 3.6, 4.1, 'left')]
    piece['raw']['notes'] = rows
    piece = apply_revision(piece, piece['settings'], [])
    result = arrange(piece, settings('melody'))
    assert {n['id'] for n in result['performance']['notes']} == {'theme1', 'theme2', 'repeat', 'lower1', 'lower2'}
    assert {o['sourceNoteIds'][0] for o in result['operations'] if o['reason'] == 'ornament'} == {'run1', 'run2'}
    for n in result['performance']['notes']:
        assert n == next(x for x in rows if x['id'] == n['id'])


def test_dense_chords_reduce_inner_tones_and_score_voice_lengths():
    from music21 import converter
    piece = fixture()
    piece['raw']['notes'] = [note('theme', 72, 0, 1.1), *[note(f'chord{p}', p, 0, 1.1, 'left', 60) for p in (36, 48, 52, 55, 60)]]
    piece = apply_revision(piece, piece['settings'], [])
    result = arrange(piece, settings('easy'))
    assert result['metrics']['after']['left']['maxSimultaneous'] <= 2
    assert result['metrics']['after']['left']['maxSpan'] <= 7
    score = converter.parseData(result['performance']['score']['musicxml'], format='musicxml')
    for part in score.parts:
        for measure in part.getElementsByClass('Measure'):
            assert float(measure.duration.quarterLength) == pytest.approx(4)


def test_multiple_harmonic_changes_inside_measure_and_overlapping_releases():
    piece = fixture()
    piece['raw']['notes'] = [note('m', 72, 0, 2), note('c', 36, 0, 2, 'left'),
                             note('f', 41, .6, 2, 'left'), note('g', 43, 1.2, 2, 'left')]
    piece = apply_revision(piece, piece['settings'], [])
    piece['guidance']['roles'] = {'m': 'melody'}
    result = arrange(piece, settings())
    bass = [n for n in result['performance']['notes'] if n['hand'] == 'left']
    assert [n['start'] for n in bass] == [0, .6, 1.2]
    assert bass[0]['end'] == .6 and bass[1]['end'] == 1.2
    assert any(o['type'] == 'duration' for o in result['operations'])
    assert result['performance']['notes'][-1]['end'] <= 2


def test_pickup_tempo_changes_syncopation_trailing_silence_and_midi(tmp_path):
    piece = fixture()
    piece['raw']['tempos'].append({'time': 2.4, 'bpm': 75})
    piece['raw']['notes'][0]['start'] = .07
    piece = apply_revision(piece, {**piece['settings'], 'useMidiTempo': True, 'downbeat': .6}, [])
    result = arrange(piece, settings('easy'))
    view = result['performance']
    assert view['score']['measures'] == piece['score']['measures']
    path = tmp_path/'arranged.mid'
    path.write_bytes(write_midi(view))
    reread = read_midi(path)
    assert mido.MidiFile(path).length == pytest.approx(piece['duration'], abs=.001)
    for a, b in zip(sorted(view['notes'], key=lambda n: (n['start'], n['pitch'])), reread['notes']):
        assert a['pitch'] == b['pitch']
        assert a['start'] == pytest.approx(b['start'], abs=.001)
        assert a['end'] == pytest.approx(b['end'], abs=.001)


def test_fingerprint_excludes_title_and_analysis_is_deterministic():
    piece = fixture()
    original = fingerprint(piece)
    piece['title'] = 'Renamed'
    assert fingerprint(piece) == original
    assert arrange(piece, settings()) == arrange(piece, settings())
    piece['guidance']['roles']['m0'] = 'melody'
    assert fingerprint(piece) != original


def test_demo_preserves_accented_phrase_register_change_and_reduces_accompaniment():
    from backend.demo import make_demo
    piece = make_demo()
    melody = {n['id'] for n in piece['notes'] if n['hand'] == 'right'}
    for level in ('melody', 'beginner', 'easy'):
        result = arrange(piece, settings(level))
        assert melody <= set(result['melodyNoteIds'])
        assert result['metrics']['after']['left']['noteCount'] < result['metrics']['before']['left']['noteCount']


def test_long_analysis_bounded():
    notes = [note(str(i), 60+i%7, i*.1, i*.1+.09) for i in range(10000)]
    start = time.monotonic()
    melody, _, _, _ = analyze(notes, ScoreSettings().model_dump(), Guidance().model_dump())
    assert melody
    assert time.monotonic()-start < 25


@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend import app as module, config, store
    for mod in (module, config, store):
        monkeypatch.setattr(mod, 'DATA', tmp_path)
    from fastapi.testclient import TestClient
    with TestClient(module.app) as client:
        store.piece_save(fixture())
        yield client


def create(client, **overrides):
    listing = client.get('/api/pieces/arrangementfixture/arrangements').json()
    return client.post('/api/pieces/arrangementfixture/arrangements', json={
        'name': 'Beginner', 'settings': settings(), 'expectedSourceFingerprint': listing['sourceFingerprint'], **overrides})


def test_saved_versions_staleness_guidance_exports_and_delete(client):
    from backend import store
    original = store.piece_get('arrangementfixture')
    response = create(client)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert store.piece_get('arrangementfixture') == original
    root = '/api/pieces/arrangementfixture'
    assert client.get(root+'/export/midi', params={'arrangementId': saved['id']}).content == write_midi(saved['performance'])
    assert client.get(root+'/export/musicxml', params={'arrangementId': saved['id']}).text == saved['performance']['score']['musicxml']
    guidance = {'roles': {'m0': 'melody'}, 'protectedNoteIds': ['m0']}
    response = client.put(root+'/guidance', json={'guidance': guidance, 'expectedSourceFingerprint': saved['sourceFingerprint']})
    assert response.status_code == 200
    old = client.get(root+'/arrangements/'+saved['id']).json()
    assert old['outdated'] is True
    assert old['performance'] == saved['performance']
    assert old['sourcePerformance'] == saved['sourcePerformance']
    assert create(client, expectedSourceFingerprint=saved['sourceFingerprint']).status_code == 409
    assert client.put(root+'/guidance', json={'guidance': guidance, 'expectedSourceFingerprint': saved['sourceFingerprint']}).status_code == 409
    refreshed = create(client, predecessorId=saved['id']).json()
    assert refreshed['id'] != saved['id'] and refreshed['predecessorId'] == saved['id']
    assert len(client.get(root+'/arrangements').json()['arrangements']) == 2
    assert store.piece_get('arrangementfixture')['raw'] == original['raw']
    assert client.delete(root).status_code == 200
    with store.db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM arrangements').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM arrangement_sources').fetchone()[0] == 0


def test_generation_failure_and_deleted_source_never_commit(client, monkeypatch):
    from backend import arrangement_api, store
    original = store.piece_get('arrangementfixture')
    def fail(*args):
        raise RuntimeError('score failure')
    monkeypatch.setattr(arrangement_api, 'arrange', fail)
    assert create(client).status_code == 500
    assert store.piece_get('arrangementfixture') == original
    assert client.get('/api/pieces/arrangementfixture/arrangements').json()['arrangements'] == []
    def deleted(piece, config):
        result = arrange(piece, config)
        with store.db() as conn:
            conn.execute('DELETE FROM pieces WHERE id=?', (piece['id'],))
        return result
    monkeypatch.setattr(arrangement_api, 'arrange', deleted)
    assert create(client).status_code == 404
    assert store.piece_get('arrangementfixture') is None


def test_source_race_invalid_ids_settings_and_arrangement_delete(client, monkeypatch):
    from backend import arrangement_api, store
    saved = create(client).json()
    root = '/api/pieces/arrangementfixture'
    assert client.get(root+'/export/midi?arrangementId=missing').status_code == 404
    assert create(client, settings={'left': {'level': 'random'}}).status_code == 422
    def changed(piece, config):
        result = arrange(piece, config)
        updated = copy.deepcopy(piece)
        updated['notes'][0]['pitch'] += 1
        store.piece_save(updated)
        return result
    monkeypatch.setattr(arrangement_api, 'arrange', changed)
    assert create(client).status_code == 409
    assert client.delete(root+'/arrangements/'+saved['id']).status_code == 200
    assert client.get(root+'/arrangements').json()['arrangements'] == []


def test_additive_schema_upgrade(client):
    from backend import store
    with store.db() as conn:
        conn.execute('PRAGMA user_version=2')
    original = store.piece_get('arrangementfixture')
    store.setup()
    assert store.piece_get('arrangementfixture') == original
    with store.db() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 3
