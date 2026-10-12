import copy
import json
import math
import time
from pathlib import Path

import pytest

from backend.domain import ScoreSettings
from backend.midi_io import read_midi, write_midi
from backend.piano_events import normalize_events


def event(start, end, pitch=60, velocity=80):
    return {'onset_time': start, 'offset_time': end, 'midi_note': pitch, 'velocity': velocity}


def test_piano_events_clamp_clip_boundaries_and_drop_invalid_intervals():
    events = [event(-.2, .5, 48), event(.8, 2, 72), event(-2, -.1),
              event(1, 1.5), event(.3, .3), event(.7, .2), event(math.nan, .5),
              event(.2, math.inf), event(.2, .5, 20), event(.2, .5, 109)]
    untouched = copy.deepcopy(events)
    notes, pedals = normalize_events(events, [], 1)
    assert [(n['pitch'], n['start'], n['end']) for n in notes] == [(48, 0, .5), (72, .8, 1)]
    assert [n['hand'] for n in notes] == ['left', 'right']
    assert pedals == []
    assert events == untouched


@pytest.mark.parametrize('field,value', [
    ('onset_time', None), ('offset_time', 'invalid'), ('midi_note', math.nan),
    ('midi_note', math.inf), ('velocity', math.nan), ('velocity', math.inf),
    ('velocity', None),
])
def test_piano_events_skip_invalid_numeric_fields(field, value):
    malformed = {**event(.1, .5), field: value}
    notes, _ = normalize_events([malformed, event(.6, .9, 64)], [], 1)
    assert [n['pitch'] for n in notes] == [64]


def test_piano_event_ids_are_stable_and_repeated_pitches_are_distinct():
    events = [event(1, 1.25, 60, 999), event(.1, .5, 72, 0),
              event(.1, .6, 48, -8), event(.1, .4, 60, 65), event(.4, .8, 60, 70)]
    notes, _ = normalize_events(events, [], 2)
    shuffled, _ = normalize_events(list(reversed(events)), [], 2)
    assert notes == shuffled
    assert [n['id'] for n in notes] == ['n0', 'n1', 'n2', 'n3', 'n4']
    assert [n['pitch'] for n in notes] == [48, 60, 72, 60, 60]
    assert [n['velocity'] for n in notes] == [1, 65, 1, 70, 127]
    assert [(n['start'], n['end']) for n in notes if n['pitch'] == 60] == [(.1, .4), (.4, .8), (1, 1.25)]
    assert {n['channel'] for n in notes} == {0}


def test_pedal_spans_union_overlap_and_touching_boundaries():
    spans = [event(.4, .8), event(-.1, .5), event(.8, 1), event(1.2, 3),
             event(-1, -.1), event(2, 3), event(.4, .4), event(.9, .7),
             event(math.nan, 1), event(.2, math.inf)]
    _, pedals = normalize_events([], spans, 2)
    assert pedals == [{'time': 0, 'value': 127, 'channel': 0},
                      {'time': 1, 'value': 0, 'channel': 0},
                      {'time': 1.2, 'value': 127, 'channel': 0},
                      {'time': 2, 'value': 0, 'channel': 0}]


def test_shared_pedal_channel_survives_midi_export_for_both_hands(tmp_path):
    notes, pedals = normalize_events([event(.1, .5, 48, 55), event(.2, .7, 72, 90)],
                                    [event(.3, 1)], 1.1)
    output = tmp_path/'piano-pedal.mid'
    output.write_bytes(write_midi({'notes': notes, 'raw': {'pedals': pedals}}))
    reread = read_midi(output)
    assert {n['hand'] for n in reread['notes']} == {'left', 'right'}
    assert {n['channel'] for n in reread['notes']} == {p['channel'] for p in reread['pedals']} == {0}
    assert [p['value'] for p in reread['pedals']] == [127, 0]
    assert [p['time'] for p in reread['pedals']] == pytest.approx([.3, 1], abs=.001)
    for old, new in zip(notes, reread['notes']):
        assert old['pitch'] == new['pitch']
        assert old['velocity'] == new['velocity']
        assert old['start'] == pytest.approx(new['start'], abs=.001)
        assert old['end'] == pytest.approx(new['end'], abs=.001)


@pytest.mark.parametrize('duration', [.01, 1, 1.005])
def test_crop_predictions_removes_padded_audio_and_adds_silent_decoder_tail(duration):
    import numpy as np
    from backend.piano_runner import crop_predictions
    shapes = {'reg_onset_output': 88, 'reg_offset_output': 88,
              'frame_output': 88, 'velocity_output': 88,
              'reg_pedal_onset_output': 1, 'reg_pedal_offset_output': 1,
              'pedal_frame_output': 1}
    frames_per_second = 100
    real_frames = int(np.ceil(duration * frames_per_second)) + 1
    outputs = {key: np.zeros((220, width), dtype=np.float32) for key, width in shapes.items()}
    # The final real frames can still contain held keys and a depressed pedal.
    outputs['frame_output'][:real_frames, 39] = .9
    outputs['velocity_output'][:real_frames, 39] = .7
    outputs['pedal_frame_output'][:real_frames, 0] = .9
    outputs['reg_onset_output'][0, 39] = .8
    # A high-confidence onset in padded audio must not reach the decoder.
    outputs['reg_onset_output'][real_frames+3, 51] = 1
    outputs['reg_offset_output'][real_frames+4, 39] = 1
    outputs['reg_pedal_offset_output'][real_frames+5, 0] = 1
    originals = {key: value.copy() for key, value in outputs.items()}
    cropped = crop_predictions(outputs, duration, frames_per_second)
    assert set(cropped) == set(outputs)
    for key, width in shapes.items():
        assert cropped[key].shape == (real_frames+12, width)
        np.testing.assert_array_equal(cropped[key][:real_frames], outputs[key][:real_frames])
        np.testing.assert_array_equal(cropped[key][real_frames:], 0)
        np.testing.assert_array_equal(outputs[key], originals[key])
        assert not np.shares_memory(cropped[key], outputs[key])
    assert cropped['frame_output'][real_frames-1, 39] == pytest.approx(.9)
    assert cropped['pedal_frame_output'][real_frames-1, 0] == pytest.approx(.9)
    assert cropped['reg_onset_output'][:, 51].sum() == 0


@pytest.mark.parametrize('original_source', [
    {'kind': 'youtube', 'videoId': 'pMU3_1VbRn0', 'url': 'https://www.youtube.com/watch?v=pMU3_1VbRn0'},
    {'kind': 'upload', 'youtubeReference': {'videoId': 'pMU3_1VbRn0', 'url': 'https://www.youtube.com/watch?v=pMU3_1VbRn0'}},
])
def test_saved_audio_pipeline_keeps_settings_reference_and_original_piece(tmp_path, monkeypatch, original_source):
    from backend import config, pipeline, store
    monkeypatch.setattr(config, 'DATA', tmp_path)
    monkeypatch.setattr(store, 'DATA', tmp_path)
    monkeypatch.setattr(pipeline, 'DATA', tmp_path)
    store.setup()
    original = {'id': 'original123', 'title': 'Original custom title', 'clipStart': 42,
                'source': original_source, 'duration': 2,
                'raw': {'notes': [{'id': 'old-note', 'pitch': 62, 'start': 0, 'end': .5}], 'duration': 2},
                'edits': [{'id': 'old-note', 'pitch': 65, 'start': .1, 'end': .7, 'hand': 'right'}]}
    store.piece_save(original)
    original_folder = tmp_path/'pieces'/original['id']
    original_folder.mkdir()
    original_audio = original_folder/'source.wav'
    original_audio.write_bytes(b'original audio')
    (original_folder/'raw.json').write_text(json.dumps(original['raw']))
    untouched = copy.deepcopy(original)
    snapshot = tmp_path/'sources'/'snapshot.wav'
    snapshot.write_bytes(b'copied recording')
    source = {'id': 'source123', 'kind': 'saved-audio', 'path': str(snapshot), 'duration': 2,
              'title': 'Original custom title (new transcription)', 'sourcePieceId': original['id'],
              'originalSource': original_source, 'clipStart': 42}
    store.source_save(source)
    settings = ScoreSettings(tempo=73, numerator=3, denominator=8, quantization='1/32',
                             downbeat=.2, cleanup='balanced').model_dump()
    request = {'sourceId': source['id'], 'start': .25, 'end': 1.75, 'settings': settings}
    with store.db() as conn:
        conn.execute('INSERT INTO jobs (id,source_id,status,stage,payload,created,updated) VALUES (?,?,?,?,?,?,?)',
                     ('job123', source['id'], 'running', 'loading model', json.dumps(request), time.time(), time.time()))

    def probe(path):
        assert Path(path) == snapshot
        return 2

    def decode(path, output, start, end):
        assert Path(path) == snapshot
        assert (start, end) == (.25, 1.75)
        output.write_bytes(b'decoded clip')

    notes, pedals = normalize_events([event(.1, .5, 48, 40), event(.2, .7, 72, 80)],
                                    [event(.3, 1.2)], 1.5)
    model_result = {'notes': notes, 'pedals': pedals, 'tempos': [], 'meters': [],
                    'noteEvidence': {n['id']: {'onset': .35} for n in notes},
                    'provenance': {'kind': 'transcription', 'engine': 'piano-crnn'}}

    class Adapter:
        name = 'Test piano engine'

        def available(self):
            return True

        def transcribe(self, audio, output, on_stage):
            assert audio.read_bytes() == b'decoded clip'
            on_stage('transcribing')
            return copy.deepcopy(model_result)

    monkeypatch.setattr(pipeline, 'probe', probe)
    monkeypatch.setattr(pipeline, 'decode_clip', decode)
    monkeypatch.setattr(pipeline, 'get_adapter', Adapter)
    pipeline.run('job123')
    completed = store.job_get('job123')
    assert completed['status'] == 'completed'
    assert completed['piece_id'] != original['id']
    result = store.piece_get(completed['piece_id'])
    assert result['settings'] == settings
    assert result['source'] == {**original_source, 'mediaClip': True}
    assert result['clipStart'] == result['raw']['provenance']['clipStart'] == 42.25
    assert result['duration'] == result['raw']['duration'] == 1.5
    assert result['previousPieceId'] == original['id']
    assert result['edits'] == []
    assert result['notes'] == notes  # Balanced keeps the piano model's .35 attacks.
    assert result['noteEvidence'] == model_result['noteEvidence']
    assert 'noteEvidence' not in result['raw']
    assert result['score']['musicxml']
    assert result['title'] == source['title']
    assert result['subtitle'].startswith(Adapter.name)
    assert (tmp_path/'pieces'/result['id']/'source.wav').read_bytes() == b'decoded clip'
    assert store.piece_get(original['id']) == untouched
    assert original_audio.read_bytes() == b'original audio'
    assert snapshot.read_bytes() == b'copied recording'
    assert json.loads((original_folder/'raw.json').read_text()) == untouched['raw']
