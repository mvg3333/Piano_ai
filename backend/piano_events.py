"""Normalize piano model events without quantizing expressive performance times."""
import math


def normalize_events(note_events, pedal_events, duration):
    notes = []
    for event in note_events:
        try:
            start, end = float(event['onset_time']), float(event['offset_time'])
            pitch, velocity = int(event['midi_note']), int(event['velocity'])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not (math.isfinite(start) and math.isfinite(end)):
            continue
        start, end = max(0., start), min(duration, end)
        if not (0 <= start < end <= duration and 21 <= pitch <= 108):
            continue
        notes.append({'pitch': pitch, 'start': start, 'end': end,
                      'velocity': min(127, max(1, velocity)),
                      # Initial raw guess only; domain.prepare_notes derives
                      # contextual hands for every saved audio revision.
                      'hand': 'left' if pitch < 60 else 'right', 'channel': 0})
    notes.sort(key=lambda n: (n['start'], n['pitch'], n['end']))
    for index, note in enumerate(notes):
        note['id'] = f'n{index}'

    # Union overlapping pedal spans, then emit balanced down/up changes. Both
    # hands are on the same MIDI channel, so one pedal controls the whole piano.
    spans = []
    for event in pedal_events or []:
        try:
            start, end = float(event['onset_time']), float(event['offset_time'])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(start) and math.isfinite(end):
            start, end = max(0., start), min(duration, end)
            if start < end:
                spans.append((start, end))
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    pedals = [event for start, end in merged for event in (
        {'time': start, 'value': 127, 'channel': 0},
        {'time': end, 'value': 0, 'channel': 0})]
    return notes, pedals
