"""Performance seconds and notation quarter-note beats are separate domains."""
import copy
import math
from bisect import bisect_right
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class ScoreSettings(BaseModel):
    tempo: float = Field(default=100, ge=20, le=300)
    numerator: int = Field(default=4, ge=1, le=12)
    denominator: int = Field(default=4)
    quantization: str = '1/16'
    downbeat: float = Field(default=0, ge=0)
    useMidiTempo: bool = False
    cleanup: Literal['off', 'balanced', 'strong'] = 'balanced'

    @model_validator(mode='after')
    def validate_settings(self):
        if self.denominator not in (2, 4, 8, 16):
            raise ValueError('Meter denominator must be 2, 4, 8, or 16')
        if self.quantization not in ('1/4', '1/8', '1/16', '1/32', '1/8T', '1/16T'):
            raise ValueError('Unsupported quantization')
        return self

class NoteEdit(BaseModel):
    id: str
    pitch: int = Field(ge=0, le=127)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    hand: str
    deleted: bool = False

    @model_validator(mode='after')
    def validate_note(self):
        if self.end <= self.start or not all(math.isfinite(x) for x in (self.start, self.end)):
            raise ValueError('Note end must be after its onset')
        if self.hand not in ('left', 'right'):
            raise ValueError('Hand must be left or right')
        return self

def effective_notes(raw, edits):
    notes = []
    by_id = {x['id']: x for x in edits}
    for original in raw['notes']:
        note = {**original, **by_id.get(original['id'], {})}
        if not note.get('deleted'):
            notes.append(note)
    return sorted(notes, key=lambda n: (n['start'], n['pitch'], n['id']))


def prepare_notes(raw, edits, settings, evidence=None):
    """Derive practice notes without modifying the recorded model output."""
    from .cleanup import clean_notes
    notes, cleanup = clean_notes(raw, effective_notes(raw, edits), edits,
                                 settings.get('cleanup', 'off'), evidence)
    if raw.get('provenance', {}).get('kind') == 'transcription':
        from .hands import assign_hands
        notes, hands = assign_hands(notes, edits)
    else:
        # The demo is composed with known hands. Imported MIDI and existing
        # manual hand labels are not replaced by audio-transcription inference.
        hands = {'method': 'preserved', 'version': 1}
    return notes, cleanup, hands

def tempo_map(settings, raw):
    changes = raw.get('tempos', []) if settings.get('useMidiTempo') else []
    if not changes:
        changes = [{'time': 0, 'bpm': settings['tempo']}]
    anchors = []
    beat, last_time, bpm = 0.0, 0.0, settings['tempo']
    for change in sorted(changes, key=lambda a: a['time']):
        t = change['time']
        beat += (t - last_time) * bpm / 60
        anchors.append({'time': t, 'beat': beat, 'bpm': change['bpm']})
        last_time, bpm = t, change['bpm']
    if anchors[0]['time'] > 0:
        anchors.insert(0, {'time': 0, 'beat': 0, 'bpm': settings['tempo']})
    # Align notation through the time map, never by moving performance events.
    from .score import GRIDS
    grid = GRIDS[settings['quantization']]
    downbeat = seconds_to_beats(settings['downbeat'], anchors)
    shift = round(downbeat / grid) * grid - downbeat
    for anchor in anchors:
        anchor['beat'] += shift
    return anchors

def seconds_to_beats(seconds, anchors):
    a = anchors[max(0, bisect_right([x['time'] for x in anchors], seconds) - 1)]
    return a['beat'] + (seconds - a['time']) * a['bpm'] / 60

def beats_to_seconds(beat, anchors):
    a = anchors[max(0, bisect_right([x['beat'] for x in anchors], beat) - 1)]
    return a['time'] + (beat - a['beat']) * 60 / a['bpm']

def apply_revision(piece, settings, edits):
    from .score import build_score
    updated = copy.deepcopy(piece)
    known = {n['id'] for n in piece['raw']['notes']}
    if any(e['id'] not in known for e in edits):
        raise ValueError('Correction refers to a missing note')
    updated['settings'] = settings
    updated['edits'] = edits
    updated['notes'], updated['cleanup'], updated['handAssignment'] = prepare_notes(
        piece['raw'], edits, settings, piece.get('noteEvidence'))
    updated['duration'] = max(piece['raw']['duration'], max((n['end'] for n in updated['notes']), default=0))
    updated['score'] = build_score(updated['notes'], settings, piece['raw'], updated['duration'])
    return updated
