"""Deterministic score draft, with explicit links back to unquantized events."""
from fractions import Fraction
import xml.etree.ElementTree as ET
from music21 import stream, note, chord, meter, tempo, clef, tie, duration, instrument
from music21.musicxml.m21ToXml import GeneralObjectExporter
from .domain import tempo_map, seconds_to_beats, beats_to_seconds

COLORS = {'left': '#0d9488', 'right': '#b453d0'}
GRIDS = {'1/4': 1, '1/8': .5, '1/16': .25, '1/32': .125, '1/8T': 1/3, '1/16T': 1/6}

def build_score(notes, settings, raw, total, timeline=None):
    anchors = timeline['anchors'] if timeline else tempo_map(settings, raw)
    grid = GRIDS[settings['quantization']]
    bar = settings['numerator'] * 4 / settings['denominator']
    first_downbeat = seconds_to_beats(settings['downbeat'], anchors)
    pickup = round((first_downbeat % bar) / grid) * grid
    if pickup >= bar - 1e-7:
        pickup = 0
    # A pickup starts at beat zero, followed by complete bars.
    boundaries = [0.0]
    boundaries.append(pickup if pickup > 1e-7 else bar)
    end_beat = max(seconds_to_beats(total, anchors), grid)
    while boundaries[-1] < end_beat - 1e-7:
        boundaries.append(boundaries[-1] + bar)
    quantized = []
    for n in notes:
        start = max(0, round(seconds_to_beats(n['start'], anchors) / grid) * grid)
        end = max(start + grid, round(seconds_to_beats(n['end'], anchors) / grid) * grid)
        # Keep repeated attacks distinct even if nearest-grid rounding collides.
        quantized.append({**n, 'beat': start, 'endBeat': end})
    while boundaries[-1] < max((n['endBeat'] for n in quantized), default=0) - 1e-7:
        boundaries.append(boundaries[-1] + bar)
    score = stream.Score(id='piano-ai')
    fragments = []
    measures = [{'index': i, 'number': i if pickup else i+1, 'startBeat': boundaries[i],
                 'endBeat': boundaries[i+1], 'startTime': beats_to_seconds(boundaries[i], anchors)}
                for i in range(len(boundaries)-1)]
    if timeline and timeline.get('measures'):
        measures = [dict(m) for m in timeline['measures']]
    for hand in ('right', 'left'):
        part = stream.PartStaff(id=hand)
        part.partName = 'Right hand (estimated)' if hand == 'right' else 'Left hand (estimated)'
        part.insert(0, instrument.Piano())
        for measure in measures:
            lo, hi = measure['startBeat'], measure['endBeat']
            m = stream.Measure(number=measure['number'])
            if measure['index'] == 0:
                m.insert(0, clef.TrebleClef() if hand == 'right' else clef.BassClef())
                m.insert(0, meter.TimeSignature(f"{settings['numerator']}/{settings['denominator']}"))
                m.insert(0, tempo.MetronomeMark(number=anchors[0]['bpm']))
                if pickup:
                    m.paddingLeft = Fraction(bar-pickup).limit_denominator(96)
            for a in anchors[1:]:
                if lo <= a['beat'] < hi:
                    m.insert(Fraction(a['beat']-lo).limit_denominator(96), tempo.MetronomeMark(number=a['bpm']))
            groups = {}
            for n in quantized:
                if n['hand'] != hand or n['beat'] >= hi-1e-7 or n['endBeat'] <= lo+1e-7:
                    continue
                a, b = max(lo, n['beat']), min(hi, n['endBeat'])
                tie_type = 'continue' if n['beat'] < lo and n['endBeat'] > hi else 'stop' if n['beat'] < lo else 'start' if n['endBeat'] > hi else None
                groups.setdefault((round(a-lo, 8), round(b-a, 8), tie_type), []).append(n)
            voices = []
            # A fresh attack and a tied fragment can share offset and duration.
            # None and str are not orderable in Python; keep a total, stable key.
            for (offset, length, tie_type), group in sorted(
                    groups.items(), key=lambda item: (item[0][0], item[0][1], item[0][2] or '')):
                # Identical pitches use separate voices, never collapse raw events.
                pitch_groups = []
                for n in group:
                    target = next((g for g in pitch_groups if n['pitch'] not in [x['pitch'] for x in g]), None)
                    if target is None:
                        target = []
                        pitch_groups.append(target)
                    target.append(n)
                for simultaneous in pitch_groups:
                    obj = chord.Chord([n['pitch'] for n in simultaneous]) if len(simultaneous)>1 else note.Note(simultaneous[0]['pitch'])
                    obj.duration = duration.Duration(Fraction(length).limit_denominator(96))
                    obj.style.color = COLORS[hand]
                    obj.id = f"n-{simultaneous[0]['id']}-m{measure['index']}"
                    if tie_type:
                        obj.tie = tie.Tie(tie_type)
                    slot = next((v for v in voices if v[1] <= offset+1e-7), None)
                    if slot is None:
                        slot = [stream.Voice(id=len(voices)+1), 0.0]
                        voices.append(slot)
                    if offset > slot[1]+1e-7:
                        slot[0].insert(Fraction(slot[1]).limit_denominator(96), note.Rest(quarterLength=Fraction(offset-slot[1]).limit_denominator(96)))
                    slot[0].insert(Fraction(offset).limit_denominator(96), obj)
                    slot[1] = offset+length
                    for n in simultaneous:
                        fragments.append({'noteId': n['id'], 'measure': measure['index'], 'beat': lo+offset,
                                          'endBeat': lo+offset+length, 'hand': hand, 'xmlId': obj.id})
            if not voices:
                voices = [[stream.Voice(id=1), 0.0]]
            for v, used in voices:
                if used < hi-lo-1e-7:
                    v.insert(Fraction(used).limit_denominator(96), note.Rest(quarterLength=Fraction(hi-lo-used).limit_denominator(96)))
                m.insert(0, v)
            part.append(m)
        score.insert(0, part)
    from music21.layout import StaffGroup
    score.insert(0, StaffGroup(list(score.parts), symbol='brace', barTogether=True))
    document = ET.fromstring(GeneralObjectExporter(score).parse())
    # music21 invents random part/instrument IDs. Canonicalize references so
    # identical source/settings produce identical saved arrangement artifacts.
    identifiers = {}
    for i, element in enumerate(document.findall('./part-list/score-part'), 1):
        identifiers[element.get('id')] = f'P{i}'
    for i, element in enumerate(document.findall('.//score-instrument'), 1):
        identifiers[element.get('id')] = f'I{i}'
    for element in document.iter():
        if element.get('id') in identifiers:
            element.set('id', identifiers[element.get('id')])
    for encoding in document.findall('./identification/encoding'):
        for date in encoding.findall('encoding-date'):
            encoding.remove(date)
    # music21 copies an event ID when an irregular duration (e.g. 5/16)
    # is engraved as several tied notes. MusicXML requires unique xs:ID values.
    used = {n.get('id') for n in document.findall('.//note[@id]')}
    exported_ids = {}
    for element in document.findall('.//note[@id]'):
        original_id = element.get('id')
        segments = exported_ids.setdefault(original_id, [])
        unique_id = original_id
        if segments:
            suffix = len(segments)+1
            unique_id = f'{original_id}-segment-{suffix}'
            while unique_id in used:
                suffix += 1
                unique_id = f'{original_id}-segment-{suffix}'
            element.set('id', unique_id)
            used.add(unique_id)
        segments.append(unique_id)
    for fragment in fragments:
        fragment['xmlIds'] = exported_ids.get(fragment['xmlId'], [])
    xml = ET.tostring(document, encoding='utf-8', xml_declaration=True).decode('utf-8')
    return {'musicxml': xml, 'anchors': anchors, 'measures': measures, 'fragments': fragments,
            'warning': 'Draft notation; hand assignment, tempo and meter are estimates.'}
