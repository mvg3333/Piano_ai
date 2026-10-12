import copy

import pytest

from backend.cleanup import clean_notes
from backend.domain import effective_notes


def note(ident, start, end, pitch=60, velocity=80):
    return {'id': ident, 'pitch': pitch, 'start': start, 'end': end,
            'velocity': velocity, 'hand': 'right'}


def fixture(notes, engine=None):
    provenance = {'kind': 'transcription'}
    if engine:
        provenance['engine'] = engine
    return {'notes': notes, 'provenance': provenance}


def test_weak_splits_preserve_sustain_and_strong_repeated_attack_without_mutation():
    notes = [note('attack', 0, .5), note('split-a', .5, 1),
             note('split-b', 1, 2), note('repeated', 2, 2.5),
             note('split-c', 2.5, 4), note('other-pitch', .5, 1, pitch=64)]
    raw = fixture(notes)
    untouched = copy.deepcopy(raw)
    evidence = {n['id']: {'onset': .55 if n['id'].startswith('split') else .9} for n in notes}
    kept, summary = clean_notes(raw, notes, [], 'balanced', evidence)
    by_id = {n['id']: n for n in kept}
    assert by_id['attack']['end'] == 2
    assert by_id['repeated']['start'] == 2
    assert by_id['repeated']['end'] == 4
    assert by_id['other-pitch']['end'] == 1
    assert set(summary['hiddenNoteIds']) == {'split-a', 'split-b', 'split-c'}
    assert summary['continuationNoteIds'] == ['split-a', 'split-b', 'split-c']
    assert summary['continuationCount'] == 3
    assert raw == untouched
    restored, summary = clean_notes(raw, notes, [], 'off', evidence)
    assert restored == notes
    assert summary['continuationCount'] == 0


def test_filter_never_bridges_silence_or_a_different_pitch():
    notes = [note('attack', 0, .5), note('other', .5, 1, pitch=64),
             note('gap', .6, 1), note('gap-tail', 1, 2)]
    raw = fixture(notes)
    evidence = {n['id']: {'onset': .9 if n['id'] == 'attack' else .55} for n in notes}
    kept, summary = clean_notes(raw, notes, [], 'balanced', evidence)
    assert kept == [notes[0]]
    assert summary['continuationCount'] == 0


@pytest.mark.parametrize('correction', ['predecessor', 'continuation', 'delete'])
def test_manual_edits_take_precedence_over_continuation_merging(correction):
    notes = [note('attack', 0, .5), note('split', .5, 2)]
    raw = fixture(notes)
    evidence = {'attack': {'onset': .9}, 'split': {'onset': .55}}
    edit = dict(notes[0] if correction == 'predecessor' else notes[1])
    if correction == 'delete':
        edit['deleted'] = True
    kept, summary = clean_notes(raw, effective_notes(raw, [edit]), [edit], 'balanced', evidence)
    assert next(n for n in kept if n['id'] == 'attack')['end'] == .5
    assert summary['continuationCount'] == 0
    if correction == 'continuation':
        assert next(n for n in kept if n['id'] == 'split') == edit
    else:
        assert len(kept) == 1


def test_continuation_does_not_overlap_a_later_strong_attack():
    notes = [note('attack', 0, .5), note('split', .5, 3), note('repeated', 2, 4)]
    raw = fixture(notes)
    evidence = {'attack': {'onset': .9}, 'split': {'onset': .55}, 'repeated': {'onset': .95}}
    kept, summary = clean_notes(raw, notes, [], 'balanced', evidence)
    assert [(n['start'], n['end']) for n in kept] == [(0, 2), (2, 4)]
    assert summary['continuationCount'] == 1


def test_short_note_with_a_clear_attack_is_not_merged_as_a_weak_split():
    notes = [note('attack', 0, .5), note('quiet', .5, .65, velocity=40)]
    raw = fixture(notes)
    kept, summary = clean_notes(raw, notes, [], 'balanced', {'quiet': {'onset': .9}})
    assert kept == [notes[0]]
    assert summary['reasons'] == {'shortWeakNote': 1}
    assert summary['continuationCount'] == 0


def test_piano_model_balanced_keeps_attacks_at_its_own_detection_threshold():
    notes = [note('quiet-short', 0, .12, velocity=40), note('held', .3, 1, velocity=40),
             note('loud-short', 1, 1.12), note('clear-short', 1.2, 1.32, velocity=40),
             note('outside', 1.5, 2, pitch=110)]
    raw = fixture(notes, engine='piano-crnn')
    evidence = {n['id']: {'onset': .7 if n['id'] == 'clear-short' else .35} for n in notes}
    kept, summary = clean_notes(raw, notes, [], 'balanced', evidence)
    assert kept == notes[:-1]
    assert summary['hiddenNoteIds'] == ['outside']
    kept, summary = clean_notes(raw, notes, [], 'strong', evidence)
    assert {n['id'] for n in kept} == {'held', 'loud-short', 'clear-short'}
    assert summary['continuationCount'] == 0
    assert summary['reasons'] == {'shortWeakNote': 1, 'outsidePiano': 1}


def test_piano_model_strong_does_not_assume_missing_onset_evidence_is_weak():
    notes = [note('quiet-short', 0, .12, velocity=30)]
    raw = fixture(notes, engine='piano-crnn')
    assert clean_notes(raw, notes, [], 'strong')[0] == notes
