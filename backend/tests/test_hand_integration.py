import copy
import json
import xml.etree.ElementTree as ET

import pytest

from backend.domain import ScoreSettings, apply_revision
from backend.midi_io import read_midi
from backend.score import COLORS


def passage(kind='transcription'):
    # Small transcription excerpt around the user's reported C4 at 18.9 s.
    # The E3-A3-C4 arpeggio precedes a distinct high-register melody.
    rows = [('f3', 53, 16.500025, 17.941736, 52),
            ('a3-first', 57, 16.906963, 17.960226, 68),
            ('c4-first', 60, 17.364765, 17.954210, 54),
            ('e3', 52, 17.824207, 20.560249, 45),
            ('a3', 57, 18.285027, 20.558163, 57),
            ('reported-c4', 60, 18.898668, 20.560629, 47),
            ('d3', 50, 20.521292, 21.858212, 40),
            ('d5', 74, 20.548836, 21.370001, 64),
            ('f5', 77, 20.744377, 20.96, 73),
            ('d6', 86, 20.964012, 21.855710, 72)]
    notes = [{'id': ident, 'pitch': pitch, 'start': start, 'end': end,
              'velocity': velocity, 'hand': 'left' if pitch < 60 else 'right', 'channel': 0}
             for ident, pitch, start, end, velocity in rows]
    return {'id': 'handpassage', 'title': 'Hand assignment passage',
            'source': {'kind': 'youtube' if kind == 'transcription' else kind},
            'raw': {'notes': notes, 'duration': 22,
                    'pedals': [{'time': 18.8, 'value': 127, 'channel': 0},
                               {'time': 20.6, 'value': 0, 'channel': 0}],
                    'provenance': {'kind': kind, 'engine': 'piano-crnn'}},
            'noteEvidence': {n['id']: {'onset': .9} for n in notes}}


def assert_score_staff(piece, ident, hand):
    fragments = [f for f in piece['score']['fragments'] if f['noteId'] == ident]
    assert fragments
    assert {f['hand'] for f in fragments} == {hand}
    exported_ids = {ident for fragment in fragments for ident in fragment['xmlIds']}
    document = ET.fromstring(piece['score']['musicxml'])
    elements = [n for n in document.findall('.//note') if n.get('id') in exported_ids]
    assert elements
    assert {n.findtext('staff') for n in elements} == {'2' if hand == 'left' else '1'}
    assert {n.get('color', '').lower() for n in elements} == {COLORS[hand]}
    assert {n.find('notehead').get('color', '').lower() for n in elements} == {COLORS[hand]}


def test_contextual_hands_reach_score_without_changing_performance_or_raw():
    original = passage()
    untouched = copy.deepcopy(original)
    settings = ScoreSettings(tempo=152, cleanup='balanced').model_dump()
    updated = apply_revision(original, settings, [])
    by_id = {n['id']: n for n in updated['notes']}
    assert by_id['reported-c4']['hand'] == 'left'
    assert by_id['d5']['hand'] == 'right'
    assert_score_staff(updated, 'reported-c4', 'left')
    assert_score_staff(updated, 'd5', 'right')
    assert updated['handAssignment']['estimated'] is True
    # Hand labels are shared by the score, piano roll, and playback; no second
    # pitch split or timing quantization belongs in their performance notes.
    for before, after in zip(original['raw']['notes'], updated['notes']):
        assert {k: v for k, v in before.items() if k != 'hand'} == {k: v for k, v in after.items() if k != 'hand'}
    assert updated['raw'] == untouched['raw']
    assert original == untouched
    regenerated = apply_revision(updated, {**settings, 'tempo': 108, 'quantization': '1/32'}, [])
    assert regenerated['notes'] == updated['notes']
    assert regenerated['raw'] == untouched['raw']
    assert regenerated['edits'] == []
    assert_score_staff(regenerated, 'reported-c4', 'left')


def test_explicit_right_hand_correction_wins_and_survives_regeneration():
    original = passage()
    target = next(n for n in original['raw']['notes'] if n['id'] == 'reported-c4')
    correction = {'id': target['id'], 'pitch': target['pitch'], 'start': target['start'],
                  'end': target['end'], 'hand': 'right', 'deleted': False}
    edits = [correction]
    untouched = copy.deepcopy((original, edits))
    settings = ScoreSettings(tempo=152).model_dump()
    updated = apply_revision(original, settings, edits)
    assert next(n for n in updated['notes'] if n['id'] == target['id'])['hand'] == 'right'
    assert_score_staff(updated, target['id'], 'right')
    regenerated = apply_revision(updated, {**settings, 'cleanup': 'off'}, edits)
    assert regenerated['notes'] == updated['notes']
    assert regenerated['edits'] == edits
    assert regenerated['raw'] == original['raw']
    assert (original, edits) == untouched
    assert_score_staff(regenerated, target['id'], 'right')


@pytest.mark.parametrize('kind', ['midi', 'demo'])
def test_demo_and_imported_midi_keep_their_assigned_hands(kind):
    original = passage(kind)
    # Explicit assignments are allowed to disagree with register conventions.
    original['raw']['notes'][0]['hand'] = 'right'
    original['raw']['notes'][-1]['hand'] = 'left'
    updated = apply_revision(original, ScoreSettings(tempo=152).model_dump(), [])
    assert updated['notes'] == original['raw']['notes']
    assert updated['raw'] == original['raw']
    assert_score_staff(updated, 'reported-c4', 'right')
    assert_score_staff(updated, 'd6', 'left')


@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend import app as module, config, store
    monkeypatch.setattr(config, 'DATA', tmp_path)
    monkeypatch.setattr(store, 'DATA', tmp_path)
    monkeypatch.setattr(module, 'DATA', tmp_path)
    from fastapi.testclient import TestClient
    with TestClient(module.app) as client:
        yield client


def test_regeneration_api_saves_one_hand_assignment_for_display_and_exports(client, tmp_path):
    from backend import store
    original = passage()
    store.piece_save(original)
    body = {'settings': ScoreSettings(tempo=152).model_dump(), 'edits': []}
    response = client.post('/api/pieces/handpassage/revisions', json=body)
    assert response.status_code == 200, response.text
    piece = response.json()
    assert next(n for n in piece['notes'] if n['id'] == 'reported-c4')['hand'] == 'left'
    assert_score_staff(piece, 'reported-c4', 'left')
    assert client.get('/api/pieces/handpassage').json() == piece
    exported_score = client.get('/api/pieces/handpassage/export/musicxml')
    assert exported_score.status_code == 200
    assert exported_score.text == piece['score']['musicxml']
    midi = client.get('/api/pieces/handpassage/export/midi')
    assert midi.status_code == 200
    path = tmp_path/'context-hands.mid'
    path.write_bytes(midi.content)
    reread = read_midi(path)
    assert len(reread['notes']) == len(piece['notes'])
    for before, after in zip(piece['notes'], reread['notes']):
        assert before['pitch'] == after['pitch']
        assert before['velocity'] == after['velocity']
        assert before['start'] == pytest.approx(after['start'], abs=.001)
        assert before['end'] == pytest.approx(after['end'], abs=.001)
        # MIDI keeps both hands on channel 0 so the inferred shared pedal works.
        assert before['channel'] == after['channel'] == 0
    assert [p['channel'] for p in reread['pedals']] == [0, 0]
    assert [p['value'] for p in reread['pedals']] == [127, 0]
    assert piece['raw'] == original['raw']
    assert piece['edits'] == []
    with store.db() as conn:
        revision = json.loads(conn.execute('SELECT payload FROM revisions').fetchone()[0])
    assert revision == body
