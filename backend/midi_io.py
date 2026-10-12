from collections import defaultdict, deque
import io
import mido

def read_midi(path):
    midi = mido.MidiFile(path)
    if midi.type == 2:
        raise ValueError('Asynchronous type-2 MIDI is not supported; export as type 0 or 1.')
    if midi.ticks_per_beat <= 0:
        raise ValueError('SMPTE MIDI timing is not supported; export with musical ticks.')
    active = defaultdict(deque)
    notes, pedals, tempos, meters = [], [], [{'time': 0.0, 'bpm': 120.0}], []
    t = 0.0
    for msg in midi:
        t += msg.time
        if msg.type == 'set_tempo':
            change = {'time': t, 'bpm': mido.tempo2bpm(msg.tempo)}
            if t == tempos[-1]['time']:
                tempos[-1] = change
            else:
                tempos.append(change)
        elif msg.type == 'time_signature':
            meters.append({'time': t, 'numerator': msg.numerator, 'denominator': msg.denominator})
        elif msg.type == 'control_change' and msg.control == 64:
            pedals.append({'time': t, 'value': msg.value, 'channel': msg.channel})
        elif msg.type == 'note_on' and msg.velocity > 0:
            active[(msg.channel, msg.note)].append((t, msg.velocity))
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            queue = active[(msg.channel, msg.note)]
            if queue:
                start, velocity = queue.popleft()
                if t > start:
                    notes.append({'id': f'n{len(notes)}', 'pitch': msg.note, 'start': start, 'end': t,
                                  'velocity': velocity, 'hand': 'left' if msg.note < 60 else 'right', 'channel': msg.channel})
    for (channel, pitch), queue in active.items():
        for start, velocity in queue:
            notes.append({'id': f'n{len(notes)}', 'pitch': pitch, 'start': start, 'end': max(t, start+.1),
                          'velocity': velocity, 'hand': 'left' if pitch < 60 else 'right', 'channel': channel})
    if not notes:
        raise ValueError('This MIDI file contains no playable notes.')
    return {'notes': sorted(notes, key=lambda n: (n['start'], n['pitch'])), 'pedals': pedals, 'tempos': tempos,
            'meters': meters, 'duration': max(t, max(n['end'] for n in notes)), 'provenance': {'kind': 'midi'}}

def write_midi(piece):
    midi = mido.MidiFile(ticks_per_beat=960)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    # Constant export tempo permits exact performance-second representation.
    track.append(mido.MetaMessage('set_tempo', tempo=500000))
    events = []
    for n in piece['notes']:
        channel = n.get('channel', 0 if n['hand']=='right' else 1)
        events.extend([(round(n['start']*1920), 1, mido.Message('note_on', channel=channel, note=n['pitch'], velocity=max(1, n.get('velocity') or 80))),
                       (round(n['end']*1920), 0, mido.Message('note_off', channel=channel, note=n['pitch'], velocity=0))])
    for p in piece.get('pedals', piece.get('raw', {}).get('pedals', [])):
        events.append((round(p['time']*1920), 0, mido.Message('control_change', channel=p.get('channel',0), control=64, value=p['value'])))
    last = 0
    for tick, _, event in sorted(events, key=lambda e: (e[0], e[1])):
        track.append(event.copy(time=max(0, tick-last)))
        last = tick
    track.append(mido.MetaMessage('end_of_track', time=max(0, round(piece.get('duration', 0)*1920)-last)))
    buffer = io.BytesIO()
    midi.save(file=buffer)
    return buffer.getvalue()
