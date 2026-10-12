"""Estimate piano hands from local registers and continuity, without changing notes.

Audio does not identify a player's hands. This is an editable voice-separation
heuristic, not fingering recognition. Only transcription callers should use it;
MIDI hand/channel assignments are not inferred here.
"""
from bisect import bisect_left

VERSION = 1
ONSET_GROUP_SECONDS = .04
CONTEXT_SECONDS = 3.0
REST_SECONDS = 2.5
BEAM_SIZE = 8
MAX_CANDIDATES = 12


def _local_boundaries(ordered, groups):
    """Sliding pitch histogram: linear updates, at most 128 bins per group."""
    counts = [0] * 128
    lo = hi = 0
    boundaries = []
    for group in groups:
        time = group[0][1]['start']
        while hi < len(ordered) and ordered[hi][1]['start'] <= time + CONTEXT_SECONDS:
            counts[ordered[hi][1]['pitch']] += 1
            hi += 1
        while lo < hi and ordered[lo][1]['start'] < time - CONTEXT_SECONDS:
            counts[ordered[lo][1]['pitch']] -= 1
            lo += 1
        pitches = [p for p, count in enumerate(counts) if count]
        total = sum(counts)
        lower = 0
        best = None
        for a, b in zip(pitches, pitches[1:]):
            lower += counts[a]
            # A single extreme detection must not establish an entire voice.
            if b - a >= 9 and lower >= 2 and total - lower >= 2:
                choice = (b - a, min(lower, total - lower), (a + b) / 2)
                if best is None or choice[:2] > best[:2]:
                    best = choice
        boundaries.append(None if best is None else best[2])
    return boundaries


def _candidates(group, boundary, locks):
    """Ordered pitch partitions, with manual assignments overriding each cut."""
    pitches = sorted({n['pitch'] for _, n in group if n['id'] not in locks})
    cuts = {0, len(pitches)}
    if pitches:
        cuts.add(bisect_left(pitches, 60))
        if boundary is not None:
            cuts.add(bisect_left(pitches, boundary))
        # Limit dense/duplicate-heavy input independently of the note count.
        gaps = sorted(range(1, len(pitches)),
                      key=lambda i: (-(pitches[i] - pitches[i-1]), abs(pitches[i] - (boundary or 60))))
        for cut in gaps:
            if len(cuts) >= MAX_CANDIDATES:
                break
            cuts.add(cut)
    candidates, seen = [], set()
    for cut in sorted(cuts):
        threshold = pitches[cut] if cut < len(pitches) else 128
        hands = tuple(locks.get(n['id'], 'left' if n['pitch'] < threshold else 'right')
                      for _, n in group)
        if hands in seen:
            continue
        seen.add(hands)
        sets = [set(), set()]
        anchors = [set(), set()]
        for (_, note), hand in zip(group, hands):
            sets[hand == 'right'].add(note['pitch'])
            # A detection shorter than the onset grouping tolerance cannot
            # reliably establish a simultaneous hand stretch. Keep the note,
            # but let sustained attacks establish reach/motion when present.
            if note['end'] - note['start'] >= ONSET_GROUP_SECONDS or note['id'] in locks:
                anchors[hand == 'right'].add(note['pitch'])
        cost = 0.
        means = []
        for hand, assigned in enumerate(sets):
            stable = anchors[hand] or assigned
            means.append(sum(stable) / len(stable) if stable else None)
            if not assigned:
                continue
            # An octave is comfortable for many simultaneous piano voicings;
            # wider stretches are penalized softly, never forbidden for edits.
            cost += .055 * max(0, max(stable) - min(stable) - 12) ** 2
            cost += .25 * max(0, len(stable) - 5) ** 2
            for pitch in assigned:
                cost += .025 * max(0, (pitch - 59) if hand == 0 else (60 - pitch))
                if boundary is not None and (pitch < boundary) != (hand == 0):
                    cost += .8 + .02 * min(24, abs(pitch - boundary))
        mask = (1 if sets[0] else 0) | (2 if sets[1] else 0)
        if mask == 3:
            cost += .12
            if means[0] > means[1]:
                cost += .2 * (means[0] - means[1])
        candidates.append((hands, means[0], means[1], mask, cost))
    return candidates


def _advance(state, candidate, time):
    """One bounded beam transition; rests release old register/motion history."""
    cost, left, left_time, right, right_time, old_mask, old_mean, old_time = state
    _, new_left, new_right, mask, own_cost = candidate
    cost += own_cost
    previous = [(left, left_time), (right, right_time)]
    updated = []
    for pitch, (old_pitch, then) in zip((new_left, new_right), previous):
        if pitch is None:
            updated.append((old_pitch, then))
            continue
        gap = time - then if then is not None else REST_SECONDS + 1
        if old_pitch is not None and gap <= REST_SECONDS:
            distance = abs(pitch - old_pitch)
            cost += (.028 * min(distance, 12) + .035 * max(0, distance - 12) ** 2) / (1 + gap)
        elif old_time is not None and time - old_time <= REST_SECONDS:
            # Starting the previously idle hand should need more evidence than
            # a few-semitone movement within the current arpeggio or melody.
            cost += .55
        updated.append((pitch, time))
    mean = new_left if mask == 1 else new_right if mask == 2 else (new_left + new_right) / 2
    gap = time - old_time if old_time is not None else REST_SECONDS + 1
    if mask in (1, 2) and old_mask in (1, 2) and mask != old_mask and gap < .85:
        distance = abs(mean - old_mean)
        if distance <= 9:
            cost += .55 * (1 - gap / .85) * (1 - distance / 16)
    return (cost, *updated[0], *updated[1], mask, mean, time)


def assign_hands(notes, edits=None):
    """Return copied notes in input order and an honest, versioned summary.

    Only ``hand`` changes. Every explicit edited hand is a hard constraint,
    including crossed hands and assignments that exceed the span heuristic.
    The beam and candidates are capped. Backpointers use two bytes per state;
    no growing path is copied at each step, keeping long recordings bounded.
    """
    copied = [dict(note) for note in notes]
    edited_ids = {edit['id'] for edit in edits or []}
    locks = {note['id']: note['hand'] for note in copied
             if note['id'] in edited_ids and note.get('hand') in ('left', 'right')}
    locks.update({edit['id']: edit['hand'] for edit in edits or []
                  if edit.get('hand') in ('left', 'right')})
    ordered = sorted(enumerate(copied), key=lambda item: (item[1]['start'], item[1]['pitch'], item[1]['id']))
    groups = []
    for item in ordered:
        if not groups or item[1]['start'] - groups[-1][0][1]['start'] > ONSET_GROUP_SECONDS:
            groups.append([])
        groups[-1].append(item)
    boundaries = _local_boundaries(ordered, groups)
    beam = [(0., None, None, None, None, 0, None, None)]
    backpointers = []
    choices = []
    for group, boundary in zip(groups, boundaries):
        candidates = _candidates(group, boundary, locks)
        choices.append(candidates)
        time = group[0][1]['start']
        distinct = {}
        for prior, state in enumerate(beam):
            for index, candidate in enumerate(candidates):
                advanced = _advance(state, candidate, time)
                key = advanced[1:]
                existing = distinct.get(key)
                if existing is None or advanced[0] < existing[0][0]:
                    distinct[key] = (advanced, prior, index)
        selected = sorted(distinct.values(), key=lambda item: item[0][0])[:BEAM_SIZE]
        beam = [item[0] for item in selected]
        backpointers.append(bytes(value for _, prior, index in selected for value in (prior, index)))
    state_index = 0
    for group, candidates, history in zip(reversed(groups), reversed(choices), reversed(backpointers)):
        previous, candidate_index = history[state_index*2:state_index*2+2]
        for (index, _), hand in zip(group, candidates[candidate_index][0]):
            copied[index]['hand'] = hand
        state_index = previous
    summary = {'version': VERSION, 'method': 'context-and-continuity', 'estimated': True,
               'changedCount': sum(a.get('hand') != b['hand'] for a, b in zip(notes, copied)),
               'lockedCount': sum(n['id'] in locks for n in copied),
               'leftCount': sum(n['hand'] == 'left' for n in copied),
               'rightCount': sum(n['hand'] == 'right' for n in copied)}
    return copied, summary
