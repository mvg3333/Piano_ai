"""Executed only by the isolated model Python. stdout is a small JSON result."""
import json
import os
import sys
import time
from pathlib import Path

def extract_note_evidence(model_output, notes):
    """Measure attack support at each original event; do not change its timing.

    Use Basic Pitch's own frame-to-time mapping (it includes window correction),
    and its inferred-onset signal, just as the default decoder does. These are
    model activations, not calibrated probabilities of a correct piano note.
    """
    import numpy as np
    from basic_pitch.note_creation import get_infered_onsets, model_frames_to_time, MIDI_OFFSET
    frames, onsets = model_output['note'], model_output['onset']
    # The upstream normalization divides by the largest positive frame change.
    # Silence and flat activations need no inferred onsets.
    if np.any(np.diff(frames, axis=0) > 0):
        with np.errstate(divide='ignore', invalid='ignore'):
            inferred = get_infered_onsets(onsets, frames)
        onsets = np.maximum(onsets, np.nan_to_num(inferred, nan=0.0, posinf=0.0, neginf=0.0))
    onsets = np.nan_to_num(onsets, nan=0.0, posinf=0.0, neginf=0.0)
    times = model_frames_to_time(len(frames))
    evidence = {}
    for n in notes:
        index = int(np.searchsorted(times, n['start']))
        # Find the nearest exact event frame; don't borrow a neighboring attack.
        choices = range(max(0, index-1), min(len(times), index+1))
        index = min(choices, key=lambda i: abs(float(times[i])-n['start']))
        pitch_index = n['pitch'] - MIDI_OFFSET
        if 0 <= pitch_index < onsets.shape[1]:
            evidence[n['id']] = {'onset': float(onsets[index, pitch_index])}
    return evidence

def run(audio_path, output_path):
    os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
    os.environ.setdefault('CUDA_VISIBLE_DEVICES', '-1')
    from basic_pitch.inference import predict, Model
    from basic_pitch import ICASSP_2022_MODEL_PATH
    model = Model(ICASSP_2022_MODEL_PATH)
    Path(output_path+'.stage').write_text('transcribing', encoding='utf-8')
    start = time.perf_counter()
    model_output, midi, events = predict(audio_path, model)
    notes = []
    # Preserve an initial hand guess in raw data. The shared revision pipeline
    # estimates contextual hands after cleanup and manual corrections.
    for instrument in midi.instruments:
        for n in instrument.notes:
            notes.append({'id': f'n{len(notes)}', 'pitch': int(n.pitch), 'start': float(n.start), 'end': float(n.end),
                          'velocity': int(n.velocity), 'hand': 'left' if n.pitch < 60 else 'right'})
    result = {'notes': sorted(notes, key=lambda n:(n['start'], n['pitch'])),
              'noteEvidence': extract_note_evidence(model_output, notes),
              'pedals': [], 'tempos': [], 'meters': [],
              'provenance': {'kind': 'transcription', 'model': 'Spotify Basic Pitch 0.4.0', 'runtime': 'TensorFlow CPU',
                             'velocity': 'Derived from model note amplitude by Basic Pitch, not calibrated performance velocity.',
                             'pedalAvailable': False, 'inferenceSeconds': time.perf_counter()-start}}
    temporary = Path(output_path+'.tmp')
    temporary.write_text(json.dumps(result), encoding='utf-8')
    temporary.replace(output_path)

if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2])
