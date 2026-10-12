"""Original 16-bar composition: Windowlight. No borrowed melody."""
import json
from .config import ROOT
from .domain import apply_revision, ScoreSettings

def make_demo():
    notes = []
    # An original study: alternating broken chords and a gentle upper melody.
    bass = [[48,55,60,55], [45,52,57,52], [53,60,65,60], [43,50,55,50]]
    melody = [[72,76,74,67,69,72], [76,79,76,72,71,69], [77,76,72,69,72,74], [71,74,79,77,74,72]]
    seconds = 60/96
    for bar in range(16):
        for step, pitch in enumerate(bass[bar%4]):
            notes.append({'id': f'd{len(notes)}', 'pitch': pitch, 'start': (bar*4+step)*seconds,
                          'end': (bar*4+step+.85)*seconds, 'velocity': 62, 'hand': 'left'})
        for step, pitch in enumerate(melody[bar%4]):
            beat = [0, .5, 1, 2, 2.5, 3][step]
            length = .46 if step in (0,1,3,4) else .9
            notes.append({'id': f'd{len(notes)}', 'pitch': pitch + (0 if bar<8 else -12),
                          'start': (bar*4+beat)*seconds, 'end': (bar*4+beat+length)*seconds,
                          'velocity': 82 if step in (0,3) else 72, 'hand': 'right'})
    raw = {'notes': notes, 'pedals': [], 'tempos': [{'time':0, 'bpm':96}], 'meters': [], 'duration': 40,
           'provenance': {'kind':'demo', 'description':'Original Piano AI composition; not a transcription.'}}
    piece = {'id': 'demo', 'title': 'Windowlight', 'subtitle': 'Original demo · a small study in C', 'raw': raw,
             'source': {'kind': 'demo'}, 'clipStart': 0, 'duration':40}
    return apply_revision(piece, ScoreSettings(tempo=96).model_dump(), [])

if __name__ == '__main__':
    target = ROOT/'frontend/public/demo.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(make_demo()), encoding='utf-8')
    print(f'Wrote {target}')
