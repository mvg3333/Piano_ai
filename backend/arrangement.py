"""Explainable, deterministic arrangements of an immutable effective performance.

All times are source seconds. Melody analysis uses a bounded continuity beam;
the subsequent accompaniment pass never changes a retained melody event.
Heuristic scores are ranking evidence, not probabilities of musical correctness.
"""
import copy
import hashlib
import json
from bisect import bisect_left, bisect_right
from collections import Counter
from statistics import median
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION = 1
Level = Literal['melody', 'beginner', 'easy', 'full']


class HandSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    level: Level = 'beginner'
    maxNotes: int = Field(default=1, ge=1, le=5)
    maxSpan: int = Field(default=7, ge=0, le=24)
    activity: Literal['none', 'changes', 'light'] = 'changes'


class ArrangementSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    left: HandSettings = Field(default_factory=HandSettings)
    right: HandSettings = Field(default_factory=HandSettings)


class Guidance(BaseModel):
    model_config = ConfigDict(extra='forbid')
    roles: dict[str, Literal['melody', 'accompaniment']] = Field(default_factory=dict)
    protectedNoteIds: list[str] = Field(default_factory=list)


def fingerprint(piece):
    fields = {k: piece.get(k) for k in ('notes', 'settings', 'edits', 'duration', 'clipStart')}
    fields['guidance'] = piece.get('guidance', Guidance().model_dump())
    fields['pedals'] = piece['raw'].get('pedals', [])
    fields['tempos'] = piece['raw'].get('tempos', [])
    fields['timeline'] = {k: piece.get('score', {}).get(k) for k in ('anchors', 'measures')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def performance(piece):
    return copy.deepcopy({k: piece.get(k) for k in ('notes', 'settings', 'score', 'duration', 'clipStart')} | {
        'pedals': piece['raw'].get('pedals', [])})


def demand(notes, duration, melody_ids=()):
    result = {}
    melody_ids = set(melody_ids)
    for hand in ('left', 'right'):
        rows = sorted((n for n in notes if n['hand'] == hand), key=lambda n: (n['start'], n['pitch'], n['id']))
        events = sorted([(n['start'], 1, i) for i, n in enumerate(rows)] +
                        [(n['end'], 0, i) for i, n in enumerate(rows)])
        active, peak, span = {}, 0, 0
        for _, on, i in events:
            if on:
                active[i] = rows[i]['pitch']
            else:
                active.pop(i, None)
            peak = max(peak, len(active))
            if active:
                span = max(span, max(active.values()) - min(active.values()))
        attacks = _groups(rows)
        centers = [sum(n['pitch'] for n in g) / len(g) for g in attacks]
        result[hand] = {'noteCount': len(rows), 'maxSimultaneous': peak, 'maxSpan': span,
                        'largeJumps': sum(abs(a-b) > 12 for a, b in zip(centers, centers[1:])),
                        'accompanimentAttacksPerSecond': round(sum(n['id'] not in melody_ids for n in rows) / max(duration, .01), 3)}
    return result


def _groups(notes):
    groups = []
    for n in notes:
        if not groups or n['start'] - groups[-1][0]['start'] > .045:
            groups.append([])
        groups[-1].append(n)
    return groups


def _flag(code, notes, message):
    return {'code': code, 'start': min((n['start'] for n in notes), default=0),
            'end': max((n['end'] for n in notes), default=0),
            'noteIds': [n['id'] for n in notes], 'message': message}


def analyze(notes, settings, guidance):
    """Return melody IDs, local harmony and review flags with bounded context."""
    beat = 60 / settings['tempo']
    groups = _groups(notes)
    typical_velocity = {h: median([n.get('velocity', 80) for n in notes if n['hand'] == h] or [80]) for h in ('left', 'right')}
    roles, protected = guidance.get('roles', {}), set(guidance.get('protectedNoteIds', []))
    # Repeated interval/rhythm cells supply evidence for both recurring themes
    # and regular broken-chord accompaniment, without assuming a highest voice.
    signatures, cells = {}, Counter()
    for hand in ('left', 'right'):
        rows = [n for n in notes if n['hand'] == hand]
        for i in range(2, len(rows)):
            a, b, c = rows[i-2:i+1]
            key = (hand, b['pitch']-a['pitch'], c['pitch']-b['pitch'],
                   round((b['start']-a['start']) / beat, 1), round((c['start']-b['start']) / beat, 1))
            signatures[c['id']] = key
            cells[key] += 1
    times = [n['start'] for n in notes]
    harmony, flags = [], []
    previous_harmony = None
    for group in groups:
        t = group[0]['start']
        local = notes[max(0, bisect_left(times, t-beat)):min(len(notes), bisect_right(times, t+beat))]
        # Bound dense imported clusters as well as the continuity beam.
        local = local[:128]
        weights = Counter()
        for n in local:
            weights[n['pitch'] % 12] += min(2*beat, n['end']-n['start']) * (1.5 if n['hand'] == 'left' else .65)
        candidates = []
        for root in range(12):
            for intervals in ((0, 4, 7), (0, 3, 7), (0, 3, 6), (0, 5, 7), (0, 4, 7, 10)):
                pcs = {(root+i) % 12 for i in intervals}
                score = sum(v if pc in pcs else -v*.8 for pc, v in weights.items())
                score -= .12*beat*(len(intervals)-3)
                candidates.append((score, root, tuple(sorted(pcs))))
        candidates.sort(key=lambda x: (-x[0], x[1], x[2]))
        best = candidates[0]
        prior = next((c for c in candidates if c[2] == previous_harmony), None)
        if prior and best[0]-prior[0] < .22*sum(weights.values()):
            best = prior
        previous_harmony = best[2]
        confidence = best[0] / max(sum(weights.values()), .001)
        bass = min(group, key=lambda n: (n['pitch'], n['id']))
        harmony.append({'start': t, 'root': best[1], 'pcs': best[2], 'certain': confidence > .55,
                        'bass': bass['pitch'] % 12})
    # Beam entries: cost, last note, pointer. Persistent backpointers avoid
    # copying a growing path at every note, keeping long performances bounded.
    beam, history = [(0., None, -1)], []
    for group, chord in zip(groups, harmony):
        t = group[0]['start']
        candidates = [n for n in group if roles.get(n['id']) != 'accompaniment' or n['id'] in protected]
        def salience(n):
            length = (n['end']-n['start']) / beat
            repeated = cells.get(signatures.get(n['id']), 0) > 1
            return (min(length, 2)*1.4 + (n.get('velocity', 80)-60)/70 +
                    (.8 if n.get('velocity', 80) >= typical_velocity[n['hand']]+6 else 0) +
                    (.55 if n['hand'] == 'right' else 0) + min(1., max(0, (n['pitch']-48)/48)) +
                    (.25 if n['pitch'] % 12 in chord['pcs'] else 0) + (.25 if repeated else 0) -
                    (.5 if repeated and length < .45 else 0) +
                    (12 if roles.get(n['id']) == 'melody' or n['id'] in protected else 0))
        candidates = sorted(candidates, key=lambda n: (-salience(n), n['id']))[:16]
        expanded = []
        for cost, last, pointer in beam:
            expanded.append((cost + (.35 if last is None or t > last['end']+beat else 0), last, pointer, None))
            for n in candidates:
                transition = 0.
                if last is not None and t-last['end'] < 2*beat:
                    distance = abs(n['pitch']-last['pitch'])
                    transition += .08*distance + .06*max(0, distance-7)**2
                    if last['end'] > n['start']+.06:
                        transition += 2.5 + (1.5 if n['end'] <= last['end'] else 0)
                    if last['hand'] != n['hand']:
                        transition += .3
                expanded.append((cost + transition - salience(n), n, pointer, n))
        expanded.sort(key=lambda x: (x[0], x[1]['id'] if x[1] else '', x[2]))
        distinct, next_beam = set(), []
        for cost, last, pointer, chosen in expanded:
            key = last['id'] if last else None
            if key in distinct:
                continue
            distinct.add(key)
            if chosen is not None:
                history.append((pointer, chosen['id']))
                pointer = len(history)-1
            next_beam.append((cost, last, pointer))
            if len(next_beam) == 24:
                break
        beam = next_beam
        if len(candidates) > 1:
            ranked = sorted(candidates, key=lambda n: (-salience(n), n['id']))
            if abs(salience(ranked[0])-salience(ranked[1])) < .45:
                flags.append(_flag('melodyAmbiguous', ranked[:2], 'Two voices have similar melodic evidence. Check which line should lead.'))
    melody = set(protected) | {i for i, role in roles.items() if role == 'melody'}
    pointer = beam[0][2] if beam else -1
    while pointer >= 0:
        pointer, ident = history[pointer]
        melody.add(ident)
    # Only remove a short, weak connecting tone bracketed by secure anchors.
    line = [n for n in notes if n['id'] in melody]
    ornaments = set()
    for a, n, b in zip(line, line[1:], line[2:]):
        if (n['id'] not in protected and roles.get(n['id']) != 'melody'
                and n['end']-n['start'] < .23*beat and a['end']-a['start'] >= .5*beat
                and b['end']-b['start'] >= .5*beat and b['start']-a['end'] < beat
                and min(a['pitch'], b['pitch']) <= n['pitch'] <= max(a['pitch'], b['pitch'])
                and n['pitch'] not in (a['pitch'], b['pitch'])
                and n.get('velocity', 80) < min(a.get('velocity', 80), b.get('velocity', 80))-8):
            ornaments.add(n['id'])
    anchors = [n for n in line if n['end']-n['start'] >= .5*beat]
    line_times = [n['start'] for n in anchors]
    for n in notes:
        i = bisect_left(line_times, n['start'])
        if not 0 < i < len(anchors):
            continue
        a, b = anchors[i-1], anchors[i]
        if (n['hand'] == a['hand'] == b['hand'] and n['id'] not in protected
                and roles.get(n['id']) != 'melody' and n['end']-n['start'] < .23*beat
                and a['end']-a['start'] >= .5*beat and b['end']-b['start'] >= .5*beat
                and b['start']-a['end'] < beat
                and min(a['pitch'], b['pitch']) < n['pitch'] < max(a['pitch'], b['pitch'])
                and n.get('velocity', 80) < min(a.get('velocity', 80), b.get('velocity', 80))-8):
            ornaments.add(n['id'])
    melody -= ornaments
    return melody, harmony, flags, ornaments


def arrange(piece, settings):
    settings = ArrangementSettings.model_validate(settings).model_dump()
    notes = sorted(copy.deepcopy(piece['notes']), key=lambda n: (n['start'], n['pitch'], n['id']))
    times = [n['start'] for n in notes]
    guidance = piece.get('guidance', Guidance().model_dump())
    melody, harmony, flags, ornaments = analyze(notes, piece['settings'], guidance)
    known = {n['id'] for n in notes}
    missing = sorted(set(guidance['protectedNoteIds'])-known)
    if missing:
        flags.append({'code': 'protectedUnavailable', 'start': 0, 'end': 0, 'noteIds': missing,
                      'message': 'Some protected source notes were deleted or hidden by cleanup. Review the source before refreshing.'})
    full = all(settings[h]['level'] == 'full' for h in ('left', 'right'))
    kept, operations = [], []
    reasons = {}
    for n in notes:
        if settings[n['hand']]['level'] == 'full' or n['id'] in melody:
            kept.append(dict(n))
    beat = 60/piece['settings']['tempo']
    previous_bass, previous_chord = None, None
    last_attack = {'left': -1e9, 'right': -1e9}
    last_pitch = {'left': None, 'right': None}
    accent_velocity = {h: median([n.get('velocity', 80) for n in notes if n['hand'] == h] or [80]) for h in ('left', 'right')}
    melody_rows = {h: [n for n in kept if n['hand'] == h] for h in ('left', 'right')}
    melody_times = {h: [n['start'] for n in melody_rows[h]] for h in ('left', 'right')}
    melody_cursor = {'left': 0, 'right': 0}
    melody_active = {'left': [], 'right': []}
    accompaniment_active = {'left': [], 'right': []}
    pending_change = {'left': True, 'right': True}
    for group, chord in zip(_groups(notes), harmony):
        t = group[0]['start']
        bass_notes = [n for n in group if n['hand'] == 'left' and n['id'] not in melody]
        bass_pc = min(bass_notes, key=lambda n: n['pitch'])['pitch'] % 12 if bass_notes else previous_bass
        # Root changes and a fresh low bass are structural; ascending arpeggio
        # steps inside the same harmony are not independent chord changes.
        fresh_bass = bool(bass_notes) and min(n['pitch'] for n in bass_notes) <= 55
        sustained_bass = any(n['end']-n['start'] >= beat*1.25 or n.get('velocity', 80) >= accent_velocity['left']+6 for n in bass_notes)
        changed = previous_chord != chord['pcs'] or (fresh_bass and bass_pc != previous_bass
                  and (bass_pc not in (previous_chord or ()) or sustained_bass))
        if changed:
            pending_change = {'left': True, 'right': True}
        for hand in ('left', 'right'):
            cfg = settings[hand]
            while melody_cursor[hand] < len(melody_rows[hand]) and melody_rows[hand][melody_cursor[hand]]['start'] <= t+.045:
                melody_active[hand].append(melody_rows[hand][melody_cursor[hand]])
                melody_cursor[hand] += 1
            melody_active[hand] = [n for n in melody_active[hand] if n['end'] > t]
            accompaniment_active[hand] = [n for n in accompaniment_active[hand] if n['end'] > t]
            if cfg['level'] in ('melody', 'full') or cfg['activity'] == 'none':
                continue
            if cfg['level'] == 'beginner' and hand == 'right':
                continue
            accented = any((n['hand'] == hand or n['id'] in melody)
                           and (n.get('velocity', 80) >= accent_velocity[n['hand']]+3
                                or n['end']-n['start'] >= beat*1.5) for n in group)
            movement = cfg['activity'] == 'light' and accented and t-last_attack[hand] >= beat*.9
            if not pending_change[hand] and not movement:
                continue
            rows = [n for n in group if n['hand'] == hand and n['id'] not in melody]
            rows.sort(key=lambda n: (n['pitch'] % 12 not in chord['pcs'], n['pitch'] if hand == 'left' else -n.get('velocity', 80), n['id']))
            for original in rows:
                if not chord['certain'] and original != rows[0]:
                    continue
                if chord['certain'] and original['pitch'] % 12 not in chord['pcs']:
                    continue
                # A replacement may release older accompaniment at this attack,
                # but neither a melody nor a full-transcription hand is altered.
                for old in accompaniment_active[hand]:
                    if (old['hand'] == hand and old['id'] not in melody and old['start'] < t-.045
                            and old['end'] > t and old.get('arrangedAccompaniment')):
                        old['end'] = t
                active = [n for n in melody_active[hand]+accompaniment_active[hand] if n['end'] > original['start']]
                if len(active) >= cfg['maxNotes']:
                    continue
                options = [original['pitch']+12*k for k in (-2, -1, 0, 1, 2) if 21 <= original['pitch']+12*k <= 108]
                def pitch_cost(p):
                    pitches = [n['pitch'] for n in active]+[p]
                    reach = max(pitches)-min(pitches)
                    return (1000 if reach > cfg['maxSpan'] else 0) + .1*abs(p-original['pitch']) + (abs(p-last_pitch[hand]) if last_pitch[hand] is not None else 0)
                pitch = min(options, key=lambda p: (pitch_cost(p), abs(p-original['pitch']), p)) if options else original['pitch']
                if pitch_cost(pitch) >= 1000 or any(n['pitch'] == pitch for n in active):
                    continue
                n = {**original, 'pitch': pitch, 'arrangedAccompaniment': True}
                # Upcoming melody attacks reserve physical capacity, including
                # notes that start between accompaniment attack groups.
                future = melody_rows[hand][bisect_right(melody_times[hand], original['start']+.045):bisect_left(melody_times[hand], n['end'])]
                for x in sorted(future, key=lambda x: x['start']):
                    overlap = [a for a in melody_active[hand]+future+accompaniment_active[hand] if a['start'] <= x['start'] < a['end']]
                    pitches = [a['pitch'] for a in overlap]+[pitch]
                    if len(overlap) >= cfg['maxNotes'] or max(pitches)-min(pitches) > cfg['maxSpan']:
                        n['end'] = x['start']
                        break
                if n['end'] <= n['start']:
                    continue
                kept.append(n)
                accompaniment_active[hand].append(n)
                last_pitch[hand], last_attack[hand] = pitch, t
                pending_change[hand] = False
            if rows and not chord['certain']:
                flags.append(_flag('harmonyAmbiguous', rows[:4], 'Harmony is uncertain; accompaniment uses a conservative source tone.'))
        previous_chord = chord['pcs']
        if fresh_bass:
            previous_bass = bass_pc
    # Finish a source-linked audit trail. Derived notes retain source IDs, so
    # existing notation fragment IDs and correction navigation remain stable.
    by_id = {n['id']: n for n in kept}
    for n in notes:
        after = by_id.get(n['id'])
        if after is None:
            code = 'ornament' if n['id'] in ornaments else 'octaveDoubling' if any(
                x['id'] in melody and abs(x['start']-n['start']) <= .045 and abs(x['pitch']-n['pitch']) in (12, 24)
                for x in notes[max(0, bisect_left(times, n['start']-.045)):bisect_right(times, n['start']+.045)]) else 'reducedAccompaniment'
            reasons[n['id']] = code
            operations.append({'type': 'remove', 'sourceNoteIds': [n['id']], 'reason': code,
                               'message': {'ornament': 'Removed a weak connecting ornament.', 'octaveDoubling': 'Removed redundant octave doubling.', 'reducedAccompaniment': 'Reduced accompaniment or inner chord density.'}[code]})
        elif after.get('arrangedAccompaniment'):
            after.pop('arrangedAccompaniment')
            if after['pitch'] != n['pitch']:
                operations.append({'type': 'octave', 'sourceNoteIds': [n['id']], 'reason': 'reduceJump', 'message': 'Moved an accompaniment tone by octaves to reduce hand movement.', 'before': n['pitch'], 'after': after['pitch']})
            if after['end'] != n['end']:
                operations.append({'type': 'duration', 'sourceNoteIds': [n['id']], 'reason': 'releaseAccompaniment', 'message': 'Released accompaniment before the next hand movement.', 'before': n['end'], 'after': after['end']})
    kept.sort(key=lambda n: (n['start'], n['pitch'], n['id']))
    for hand in ('left', 'right'):
        cfg = settings[hand]
        if cfg['level'] == 'full':
            continue
        active = []
        for n in (n for n in kept if n['hand'] == hand):
            active = [a for a in active if a['end'] > n['start']]+[n]
            if len(active) > cfg['maxNotes'] or max(a['pitch'] for a in active)-min(a['pitch'] for a in active) > cfg['maxSpan']:
                flags.append(_flag('melodyExceedsLimits', active, f'Preserved {hand}-hand melody exceeds the chosen simultaneous-note or stretch limit.'))
        rows = [n for n in kept if n['hand'] == hand]
        for a, b in zip(rows, rows[1:]):
            if b['start']-a['end'] < beat*2 and abs(a['pitch']-b['pitch']) > 12:
                flags.append(_flag('largeJump', [a, b], f'A {hand}-hand jump remains larger than an octave.'))
    for group in _groups(kept):
        left = [n for n in group if n['hand'] == 'left']
        right = [n for n in group if n['hand'] == 'right']
        if left and right and max(n['pitch'] for n in left) > min(n['pitch'] for n in right):
            flags.append(_flag('voiceCrossing', group, 'The hands cross here. Check the source hand assignments.'))
    view = performance(piece)
    if not full:
        from .score import build_score
        view['notes'] = kept
        view['score'] = build_score(kept, piece['settings'], piece['raw'], piece['duration'], timeline=piece['score'])
    return {'engineVersion': VERSION, 'settings': settings, 'performance': view,
            'sourceNoteMap': {n['id']: [n['id']] for n in kept}, 'melodyNoteIds': sorted(melody & known),
            'operations': operations, 'reviewFlags': flags,
            'metrics': {'before': demand(notes, piece['duration'], melody), 'after': demand(kept, piece['duration'], melody)}}
