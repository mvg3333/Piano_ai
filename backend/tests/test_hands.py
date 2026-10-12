import copy

from backend.hands import assign_hands


def note(pitch, start, duration=.35, id=None, **extra):
    return {'id': id or f'{pitch}-{start}', 'pitch': pitch, 'start': start,
            'end': start + duration, 'velocity': 65,
            'hand': 'left' if pitch < 60 else 'right', **extra}


def test_left_arpeggio_continues_through_middle_c_before_treble_enters():
    notes = [note(53, 16.5, 1.442), note(57, 16.907, 1.053), note(60, 17.365, .589),
             note(52, 17.824, 2.736), note(57, 18.285, 2.273), note(60, 18.899, 1.662),
             note(50, 20.521, 1.337), note(74, 20.549, .821), note(77, 20.744, .216),
             note(86, 20.964, .892)]
    result, summary = assign_hands(notes)
    assert all(n['hand'] == 'left' for n in result[:7])
    assert all(n['hand'] == 'right' for n in result[7:])
    assert summary['estimated'] is True
    assert summary['changedCount'] == 2


def test_monophonic_middle_c_melody_stays_right_including_lower_neighbor():
    notes = [note(p, i * .4) for i, p in enumerate([60, 62, 64, 62, 60, 59, 60, 64])]
    result, _ = assign_hands(notes)
    assert all(n['hand'] == 'right' for n in result)


def test_high_left_arpeggio_and_low_right_melody_use_local_context():
    high = [note(p, i * .35) for i, p in enumerate([60, 64, 67, 64, 60, 67])]
    high += [note(p, i * .35 + .02) for i, p in enumerate([84, 86, 88, 86, 84, 88])]
    result, _ = assign_hands(high)
    assert all(n['hand'] == 'left' for n in result[:6])
    assert all(n['hand'] == 'right' for n in result[6:])
    low = [note(p, i * .4) for i, p in enumerate([36, 40, 43, 40, 36, 43])]
    low += [note(p, i * .4 + .015) for i, p in enumerate([55, 57, 59, 57, 55, 59])]
    result, _ = assign_hands(low)
    assert all(n['hand'] == 'left' for n in result[:6])
    assert all(n['hand'] == 'right' for n in result[6:])


def test_chords_and_repeated_attacks_have_consistent_reachable_hands():
    notes = [note(p, t, .2) for t in (0., .5, 1., 1.5) for p in (48, 55, 60, 76, 79, 84)]
    result, _ = assign_hands(notes)
    assert all(n['hand'] == ('left' if n['pitch'] <= 60 else 'right') for n in result)


def test_brief_remote_detection_does_not_split_a_continuous_arpeggio():
    notes = [note(p, 10 + i * .4, 1.2 - (i % 3) * .4)
             for i, p in enumerate([52, 55, 60, 53, 57, 60, 52, 57, 60])]
    notes.append(note(41, 11.995, .013, id='brief-detection'))
    result, _ = assign_hands(notes)
    assert all(n['hand'] == 'left' for n in result[:-1])
    assert len(result) == len(notes)
    assert result[-1]['id'] == 'brief-detection'
    assert result[-1]['start'] == notes[-1]['start']
    assert result[-1]['end'] == notes[-1]['end']


def test_phrase_rest_resets_previous_hand_and_absolute_time_does_not_matter():
    phrase = [note(p, i * .4) for i, p in enumerate([52, 57, 60, 57, 52])]
    phrase += [note(p, 10 + i * .4) for i, p in enumerate([60, 62, 64, 62, 60])]
    result, _ = assign_hands(phrase)
    assert all(n['hand'] == 'left' for n in result[:5])
    assert all(n['hand'] == 'right' for n in result[5:])
    shifted = [{**n, 'start': n['start'] + 100, 'end': n['end'] + 100} for n in phrase]
    later, _ = assign_hands(shifted)
    assert [n['hand'] for n in later] == [n['hand'] for n in result]


def test_edits_lock_hands_even_for_crossings_and_input_is_unchanged():
    notes = [note(40, 0, channel=3), note(80, 0, channel=1), note(60, .4), note(64, .8)]
    edits = [{'id': notes[0]['id'], 'hand': 'right'},
             {'id': notes[1]['id'], 'hand': 'left'},
             {'id': notes[2]['id'], 'hand': 'right'}]
    original, original_edits = copy.deepcopy(notes), copy.deepcopy(edits)
    result, summary = assign_hands(notes, edits)
    assert [n['hand'] for n in result[:3]] == ['right', 'left', 'right']
    assert notes == original and edits == original_edits
    assert summary['lockedCount'] == 3
    for a, b in zip(notes, result):
        assert a is not b
        assert {k: v for k, v in a.items() if k != 'hand'} == {k: v for k, v in b.items() if k != 'hand'}


def test_unsorted_input_duplicate_pitches_and_empty_input_are_supported():
    notes = [note(64, 1, id='last'), note(48, 0, id='bass'),
             note(64, 0, id='one'), note(64, 0, id='two')]
    result, _ = assign_hands(notes, [{'id': 'two', 'hand': 'left'}])
    assert [n['id'] for n in result] == [n['id'] for n in notes]
    assert result[-1]['hand'] == 'left'
    assert assign_hands([])[0] == []


def test_any_edited_id_preserves_its_current_hand_when_edit_omits_hand():
    notes = [note(52, 0), note(57, .4), note(60, .8)]
    result, summary = assign_hands(notes, [{'id': notes[-1]['id'], 'pitch': 60}])
    assert result[-1]['hand'] == 'right'
    assert summary['lockedCount'] == 1
