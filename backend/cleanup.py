"""Reversible filtering of audio transcription candidates, never imported MIDI."""


def clean_notes(raw, notes, edits, profile, evidence=None):
    evidence = evidence or {}
    edited = {e['id'] for e in edits}
    enabled = raw.get('provenance', {}).get('kind') == 'transcription' and profile != 'off'
    piano_model = raw.get('provenance', {}).get('engine') == 'piano-crnn'
    kept, hidden, reasons, reason_by_id = [], [], {}, {}
    onset_floor = .7 if profile == 'strong' else .6
    short_limit = .3 if profile == 'strong' else .22
    weak_limit = 52 if profile == 'strong' else 46
    for n in notes:
        reason = None
        # A user's explicit correction takes precedence over automatic cleanup.
        if enabled and n['id'] not in edited:
            onset = evidence.get(n['id'], {}).get('onset')
            if not 21 <= n['pitch'] <= 108:
                reason = 'outsidePiano'
            elif piano_model:
                # The piano model decodes attacks at .3; its activations are not
                # calibrated to Basic Pitch's .6/.7 cleanup thresholds. Keep
                # its normal detections, and require three weak signals before
                # applying the optional stronger cleanup.
                if (profile == 'strong' and onset is not None and onset < .4
                        and n.get('velocity', 127) < 52 and n['end'] - n['start'] < .3):
                    reason = 'shortWeakNote'
            elif onset is not None and onset < onset_floor:
                reason = 'weakAttack'
            elif n.get('velocity', 127) < weak_limit and n['end'] - n['start'] < short_limit:
                reason = 'shortWeakNote'
        if reason:
            hidden.append(n['id'])
            reason_by_id[n['id']] = reason
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            kept.append(dict(n))

    continuations = []
    if enabled and not piano_model:
        # Basic Pitch splits a held note at inferred re-attacks. Removing only
        # a weak split would silence the remaining sustain. Join its duration
        # back to the preceding same-pitch note, without emitting a new attack.
        # A 15 ms tolerance accommodates one model frame and float rounding.
        by_id = {n['id']: n for n in kept}
        by_pitch = {}
        for n in notes:
            by_pitch.setdefault(n['pitch'], []).append(n)
        for pitch_notes in by_pitch.values():
            pitch_notes.sort(key=lambda n: (n['start'], n['end'], n['id']))
            next_kept_start, next_start = {}, None
            for n in reversed(pitch_notes):
                next_kept_start[n['id']] = next_start
                if n['id'] in by_id:
                    next_start = n['start']
            previous = None
            for n in pitch_notes:
                if n['id'] in by_id:
                    previous = by_id[n['id']]
                elif (reason_by_id.get(n['id']) == 'weakAttack' and previous is not None
                      and previous['id'] not in edited
                      and abs(previous['end'] - n['start']) <= .015):
                    end = n['end']
                    following = next_kept_start[n['id']]
                    if following is not None:
                        end = min(end, following)
                    if end > previous['end']:
                        previous['end'] = end
                        continuations.append(n['id'])
    return kept, {'profile': profile if enabled else 'off', 'hiddenNoteIds': hidden,
                  'reasons': reasons, 'hasOnsetEvidence': bool(evidence),
                  'continuationNoteIds': continuations, 'continuationCount': len(continuations), 'version': 2}
