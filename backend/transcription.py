import json
import os
from pathlib import Path
import subprocess
import time
from typing import Protocol
from .config import MODEL_PYTHON, PIANO_CRNN_PYTHON, PIANO_CRNN_CHECKPOINT, ROOT

class TranscriptionAdapter(Protocol):
    def available(self) -> bool: ...
    def transcribe(self, audio: Path, output: Path) -> dict: ...

class BasicPitchAdapter:
    name = 'Basic Pitch'
    python = MODEL_PYTHON
    runner = 'model_runner.py'

    def available(self):
        return Path(MODEL_PYTHON).is_file()

    def transcribe(self, audio, output, on_stage=None):
        if not self.available():
            raise RuntimeError('Basic Pitch environment is not installed. Run python scripts/setup.py --with-model. Demo and MIDI import remain available.')
        env = {**os.environ, 'TF_CPP_MIN_LOG_LEVEL': '2', 'CUDA_VISIBLE_DEVICES': '-1'}
        stage_path = Path(str(output)+'.stage')
        stage_path.unlink(missing_ok=True)
        log_path = Path(str(output)+'.log')
        with log_path.open('w', encoding='utf-8') as log:
            process = subprocess.Popen([self.python, str(ROOT/'backend'/self.runner), str(audio), str(output)],
                                       stdout=log, stderr=log, env=env)
            began = time.monotonic()
            announced = False
            while process.poll() is None:
                if on_stage and not announced and stage_path.exists():
                    on_stage('transcribing')
                    announced = True
                if time.monotonic()-began > 7200:
                    process.kill();process.wait()
                    raise RuntimeError('Transcription exceeded the two-hour job limit. Try a shorter interval.')
                time.sleep(.2)
        if process.returncode:
            raise RuntimeError(self.name+' failed: '+log_path.read_text(encoding='utf-8',errors='replace')[-2500:])
        return json.loads(output.read_text(encoding='utf-8'))


class PianoCRNNAdapter(BasicPitchAdapter):
    name = 'Piano CRNN'
    python = PIANO_CRNN_PYTHON
    runner = 'piano_runner.py'

    def available(self):
        return (Path(self.python).is_file() and PIANO_CRNN_CHECKPOINT.is_file()
                and PIANO_CRNN_CHECKPOINT.stat().st_size == 171966578)


def get_adapter():
    """Prefer the piano specialist when installed; keep the lightweight fallback."""
    piano = PianoCRNNAdapter()
    return piano if piano.available() else BasicPitchAdapter()
