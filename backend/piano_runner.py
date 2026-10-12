"""Piano-specific inference, executed only inside .venv-piano.

Uses the upstream model and decoder with correctly cropped frame outputs.
Heavy ML dependencies never enter the API or worker's interpreter.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.piano_events import normalize_events

CHECKPOINT_SHA256 = 'c3fa9730725bf4a762f1c14bc80cd5986eacda01b026f5a4a2525cd607876141'


def crop_predictions(outputs, duration, frames_per_second):
    import numpy as np
    frame_count = int(np.ceil(duration * frames_per_second)) + 1
    # Twelve zero frames let the upstream pedal decoder close a pedal held at
    # the clip boundary (it waits ten silent frames). Normalize events to the
    # true duration afterward. Padded audio predictions are never decoded.
    return {key: np.pad(value[:frame_count], ((0, 12), (0, 0)))
            for key, value in outputs.items()}


def run(audio_path, output_path):
    checkpoint = Path(os.getenv('PIANO_CRNN_CHECKPOINT', ROOT / '.tools/models/piano-crnn.pth'))
    if not checkpoint.is_file():
        raise RuntimeError('Piano model weights are missing. Run python -m scripts.setup_piano.')
    # Verify before calling upstream, which otherwise tries a shell downloader.
    with checkpoint.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != CHECKPOINT_SHA256:
        raise RuntimeError('Piano model checksum mismatch. Run python -m scripts.setup_piano to repair it.')

    import numpy as np
    import torch
    torch.set_num_threads(max(1, min(8, int(os.getenv('PIANO_MODEL_THREADS', '4')))))
    torch.set_num_interop_threads(1)
    import librosa
    from piano_transcription_inference import PianoTranscription
    from piano_transcription_inference.pytorch_utils import forward
    from piano_transcription_inference.utilities import RegressionPostProcessor

    began = time.perf_counter()
    audio, sr = librosa.load(path=audio_path, sr=16000, mono=True)
    if not len(audio):
        raise ValueError('The audio clip is empty.')
    duration = len(audio) / sr
    # PyTorch's default weights_only=True is retained when loading this verified
    # state dictionary. No arbitrary checkpoint pickle execution is enabled.
    model = PianoTranscription(checkpoint_path=str(checkpoint), device='cpu')
    Path(output_path + '.stage').write_text('transcribing', encoding='utf-8')
    segment = model.segment_samples
    padded = np.pad(audio, (0, (-len(audio)) % segment))[None, :]
    segments = model.enframe(padded, segment)
    with torch.inference_mode():
        batched = forward(model.model, segments, batch_size=1)
    # Upstream 0.0.6 slices frames by number of audio samples. Correct the unit
    # before decoding so the padded last segment cannot invent late notes.
    outputs = crop_predictions({key: model.deframe(value) for key, value in batched.items()},
                               duration, model.frames_per_second)
    processor = RegressionPostProcessor(model.frames_per_second, model.classes_num,
        onset_threshold=.3, offset_threshold=.3, frame_threshold=.1, pedal_offset_threshold=.2)
    events, pedal_events = processor.output_dict_to_midi_events(outputs)
    notes, pedals = normalize_events(events, pedal_events, duration)
    evidence = {}
    onsets = outputs['reg_onset_output']
    for note in notes:
        frame = min(len(onsets)-1, max(0, round(note['start'] * model.frames_per_second)))
        evidence[note['id']] = {'onset': float(onsets[frame, note['pitch']-21])}
    result = {'notes': notes, 'noteEvidence': evidence, 'pedals': pedals,
              'tempos': [], 'meters': [], 'duration': duration,
              'provenance': {'kind': 'transcription', 'engine': 'piano-crnn',
                  'model': 'High-resolution piano CRNN (piano-transcription-inference 0.0.6)',
                  'runtime': 'PyTorch CPU', 'checkpointSha256': digest,
                  'onsetThreshold': .3, 'offsetThreshold': .3, 'frameThreshold': .1,
                  'velocity': 'Estimated piano performance velocity; not ground truth.',
                  'pedalAvailable': True, 'inferenceSeconds': time.perf_counter()-began}}
    temporary = Path(output_path + '.tmp')
    temporary.write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
    temporary.replace(output_path)
    print(json.dumps({'notes': len(notes), 'pedalSpans': len(pedals)//2,
                      'seconds': result['provenance']['inferenceSeconds']}), flush=True)


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2])
