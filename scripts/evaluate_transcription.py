"""Reproducible *synthetic* piano transcription benchmark, separate from user music.

    python -m scripts.evaluate_transcription render
    python -m scripts.evaluate_transcription evaluate data/benchmark/accuracy/basic-pitch.json
    python -m scripts.evaluate_transcription self-test

Rendering uses only bundled CC BY 3.0 samples, never the user's library or network.
Onsets use exact scheduled sample attacks, after consistently removing leading
sample padding. Offsets are scheduled key releases (a 90 ms release follows).
This fixture is useful for regression/comparison, not an estimate of accuracy on
the YouTube recording or on acoustic pianos generally. Thresholds should not be
selected solely by optimizing this small, sample-based fixture.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = ROOT / 'data' / 'benchmark' / 'accuracy'
RATE = 22050


def fixture_notes():
    notes = []
    cases = [
        {'id': 'melody', 'start': 0.0, 'end': 8.0},
        {'id': 'chords', 'start': 8.0, 'end': 15.0},
        {'id': 'quiet_inner_voices', 'start': 15.0, 'end': 23.0},
        {'id': 'fast_repetitions', 'start': 23.0, 'end': 29.0},
        {'id': 'wide_register', 'start': 29.0, 'end': 35.0},
    ]

    def add(case, pitch, start, duration, gain=1.0):
        notes.append({'id': f'ref{len(notes)}', 'pitch': pitch, 'start': start,
                      'end': start + duration, 'velocity': round(95 * gain),
                      'gain': gain, 'case': case,
                      'hand': 'left' if pitch < 60 else 'right'})

    for i, pitch in enumerate([60, 62, 64, 67, 69, 67, 64, 62, 60, 55, 59, 60]):
        add('melody', pitch, 1.0 + i * .5, .36, .9 if i % 3 else 1.0)
    for i, chord in enumerate([(48, 60, 64, 67), (45, 60, 64, 69),
                               (41, 60, 65, 69), (43, 59, 62, 67),
                               (48, 60, 64, 67)]):
        for pitch in chord:
            add('chords', pitch, 8.4 + i * 1.15, .9, .8)
    for i, chord in enumerate([(48, 64, 67, 76), (45, 64, 69, 76),
                               (41, 65, 69, 77), (43, 62, 67, 74),
                               (45, 64, 69, 76), (48, 64, 67, 79)]):
        for pitch, gain in zip(chord, (.8, .28, .4, 1.0)):
            add('quiet_inner_voices', pitch, 15.4 + i * 1.1, .85, gain)
    for i in range(16):
        add('fast_repetitions', 64 if i < 8 else (67 if i % 2 else 69),
            23.4 + i * .25, .15, .8 if i % 2 else 1.0)
    for i in range(4):
        add('fast_repetitions', 48, 23.4 + i, .55, .65)
    for i, pair in enumerate([(36, 84), (43, 79), (48, 76), (31, 83), (36, 84)]):
        for pitch in pair:
            add('wide_register', pitch, 29.4 + i * .9, .65, .9)
    return sorted(notes, key=lambda n: (n['start'], n['pitch'])), cases


def render(directory: Path):
    import librosa
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    directory.mkdir(parents=True, exist_ok=True)
    notes, cases = fixture_notes()
    duration = cases[-1]['end']
    mix = np.zeros(round(duration * RATE), dtype=np.float64)
    samples, sample_details = {}, {}
    for octave in range(1, 8):
        path = ROOT / 'frontend' / 'public' / 'samples' / f'C{octave}.mp3'
        audio, _ = librosa.load(path, sr=RATE, mono=True)
        # Use the same 5 ms RMS / 2% peak-RMS attack definition for each source.
        window = max(1, round(.005 * RATE))
        envelope = np.sqrt(np.convolve(audio.astype(np.float64) ** 2,
                                      np.ones(window) / window, mode='valid'))
        attack = int(np.flatnonzero(envelope >= .02 * envelope.max())[0])
        audio = audio[attack:]
        peak = float(np.max(np.abs(audio)))
        samples[12 * (octave + 1)] = audio.astype(np.float64) / peak
        sample_details[f'C{octave}'] = {'removedPaddingSeconds': attack / RATE,
                                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    pitched = {}
    for note in notes:
        pitch = note['pitch']
        if pitch not in pitched:
            anchor = min(samples, key=lambda p: abs(p - pitch))
            ratio = Fraction(2 ** ((anchor - pitch) / 12)).limit_denominator(2048)
            pitched[pitch] = resample_poly(samples[anchor], ratio.numerator, ratio.denominator)
        audio = pitched[pitch]
        held = round((note['end'] - note['start']) * RATE)
        release = round(.09 * RATE)
        length = held + release
        voice = np.zeros(length, dtype=np.float64)
        voice[:min(length, len(audio))] = audio[:length]
        envelope = np.ones(length)
        # A short fade prevents sample-splice clicks; modest decay retains inner voices.
        attack_length = round(.003 * RATE)
        envelope[:attack_length] = np.linspace(0, 1, attack_length)
        envelope *= np.exp(-np.arange(length) / RATE * .15)
        envelope[held:] *= np.linspace(1, 0, release)
        at = round(note['start'] * RATE)
        mix[at:at + length] += voice * envelope * note['gain']
    normalization = .88 / float(np.max(np.abs(mix)))
    mix *= normalization
    audio_path = directory / 'synthetic-piano.wav'
    sf.write(audio_path, mix, RATE, subtype='PCM_16')
    truth = {'notes': notes, 'cases': cases, 'duration': duration,
             'provenance': {'kind': 'synthetic-ground-truth', 'fixtureVersion': 1,
                            'sampleRate': RATE, 'samples': sample_details,
                            'audioSha256': hashlib.sha256(audio_path.read_bytes()).hexdigest(),
                            'gainNormalization': normalization,
                            'source': 'Bundled tonejs-instruments C1–C7 piano samples, CC BY 3.0; see frontend/public/samples/ATTRIBUTION.txt.',
                            'offsetDefinition': 'Key release; rendered 90 ms release tail follows.',
                            'limitation': 'Sample-based synthetic fixture; does not measure accuracy on the YouTube recording.'}}
    (directory / 'reference.json').write_text(json.dumps(truth, indent=2), encoding='utf-8')
    print(json.dumps({'audio': str(audio_path), 'reference': str(directory / 'reference.json'),
                      'notes': len(notes), 'seconds': duration}, indent=2))


def matching(reference, predictions, onset_tolerance=.05, offset_tolerance=None):
    """Maximum-cardinality bipartite matching, exact pitch and inclusive timing gates.

    Augmenting paths avoid greedy undercount when repeated-note gates overlap.
    Each reference and prediction can be used at most once. Offset tolerance is
    max(the supplied floor, 20% of reference duration), following common note
    transcription evaluation practice. No transposition/timing alignment is fit.
    """
    by_pitch = defaultdict(list)
    for index, predicted in enumerate(predictions):
        by_pitch[predicted['pitch']].append(index)
    edges = {}
    for index, note in enumerate(reference):
        candidates = []
        for j in by_pitch[note['pitch']]:
            predicted = predictions[j]
            if abs(note['start'] - predicted['start']) > onset_tolerance + 1e-9:
                continue
            if offset_tolerance is not None:
                tolerance = max(offset_tolerance, .2 * (note['end'] - note['start']))
                if abs(note['end'] - predicted['end']) > tolerance + 1e-9:
                    continue
            candidates.append(j)
        edges[index] = sorted(candidates, key=lambda j: abs(note['start'] - predictions[j]['start']))
    owners = {}

    def augment(i, visited):
        for j in edges[i]:
            if j in visited:
                continue
            visited.add(j)
            if j not in owners or augment(owners[j], visited):
                owners[j] = i
                return True
        return False

    for index in range(len(reference)):
        augment(index, set())
    return sorted((i, j) for j, i in owners.items())


def metrics(reference, predictions, onset_tolerance=.05):
    pairs = matching(reference, predictions, onset_tolerance)
    strict_pairs = matching(reference, predictions, onset_tolerance, .05)

    def summarize(count):
        precision = count / len(predictions) if predictions else 0.0
        recall = count / len(reference) if reference else 0.0
        return {'matched': count, 'falsePositives': len(predictions) - count,
                'missed': len(reference) - count, 'referenceNotes': len(reference),
                'predictedNotes': len(predictions), 'precision': round(precision, 4),
                'recall': round(recall, 4),
                'f1': round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0}

    errors = [abs(reference[i]['start'] - predictions[j]['start']) for i, j in pairs]
    return {'onset': summarize(len(pairs)), 'onsetAndOffset': summarize(len(strict_pairs)),
            'meanMatchedOnsetErrorMs': round(sum(errors) / len(errors) * 1000, 2) if errors else None}


def read_notes(value):
    notes = value if isinstance(value, list) else value.get('notes', value.get('raw', {}).get('notes'))
    if notes is None:
        raise ValueError('JSON must be a note list or an object containing notes (or raw.notes).')
    for n in notes:
        if not isinstance(n['pitch'], int) or not 0 <= n['pitch'] <= 127:
            raise ValueError('Every note needs an integer MIDI pitch between 0 and 127.')
        if not all(math.isfinite(n[key]) for key in ('start', 'end')) or n['start'] < 0 or n['end'] <= n['start']:
            raise ValueError('Every note needs finite times with 0 <= start < end.')
    return notes


def evaluate(prediction_path, reference_path, output=None, onset_tolerance=.05):
    reference = json.loads(reference_path.read_text(encoding='utf-8'))
    predicted = json.loads(prediction_path.read_text(encoding='utf-8'))
    truth, notes = read_notes(reference), read_notes(predicted)
    report = {'reference': str(reference_path), 'prediction': str(prediction_path),
              'onsetToleranceSeconds': onset_tolerance,
              'offsetTolerance': 'max(50 ms, 20% of reference note duration)',
              'matching': 'Maximum cardinality, exact MIDI pitch, one-to-one; no fitted time shift.',
              'limitation': reference.get('provenance', {}).get('limitation'),
              'overall': metrics(truth, notes, onset_tolerance), 'cases': {}}
    for case in reference.get('cases', []):
        # Case windows are separated by silence; each predicted onset belongs to one case.
        selected_truth = [n for n in truth if case['start'] <= n['start'] < case['end']]
        selected_predictions = [n for n in notes if case['start'] <= n['start'] < case['end']]
        report['cases'][case['id']] = metrics(selected_truth, selected_predictions, onset_tolerance)
    encoded = json.dumps(report, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding='utf-8')
    print(encoded)
    return report


def self_test():
    def note(start, pitch=60, duration=.3):
        return {'pitch': pitch, 'start': start, 'end': start + duration}

    # Greedy nearest-first consumes prediction .04 for reference .03 and misses
    # reference .08; augmenting paths correctly find two matches.
    assert len(matching([note(.03), note(.08)], [note(0), note(.04)])) == 2
    assert len(matching([note(0)], [note(0), note(.01)])) == 1
    assert len(matching([note(0)], [note(0, pitch=61)])) == 0
    assert len(matching([note(0)], [note(.05)])) == 1
    assert len(matching([note(0)], [note(.05001)])) == 0
    assert len(matching([note(0)], [note(0, duration=.5)], offset_tolerance=.05)) == 0
    assert metrics([], [])['onset']['f1'] == 0
    notes, _ = fixture_notes()
    assert metrics(notes, notes)['onsetAndOffset']['f1'] == 1
    print('8 evaluation self-checks passed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    render_parser = commands.add_parser('render', help='Render reproducible bundled-sample audio and note labels.')
    render_parser.add_argument('--directory', type=Path, default=DEFAULT_DIRECTORY)
    evaluate_parser = commands.add_parser('evaluate', help='Evaluate prediction JSON against the rendered reference.')
    evaluate_parser.add_argument('prediction', type=Path)
    evaluate_parser.add_argument('--reference', type=Path, default=DEFAULT_DIRECTORY / 'reference.json')
    evaluate_parser.add_argument('--output', type=Path)
    evaluate_parser.add_argument('--onset-tolerance', type=float, default=.05)
    commands.add_parser('self-test', help='Check matching, timing gates, duplicates, and identity evaluation.')
    args = parser.parse_args()
    if args.command == 'render':
        render(args.directory)
    elif args.command == 'evaluate':
        if not 0 < args.onset_tolerance < 1:
            parser.error('--onset-tolerance must be between 0 and 1 second.')
        evaluate(args.prediction, args.reference, args.output, args.onset_tolerance)
    else:
        self_test()


if __name__ == '__main__':
    main()
