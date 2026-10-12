"""All state stays in the project unless explicitly configured otherwise."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('PIANO_DATA_DIR', ROOT / 'data')).resolve()
MAX_BYTES = int(os.getenv('PIANO_MAX_BYTES', 500 * 1024 * 1024))
MAX_SECONDS = float(os.getenv('PIANO_MAX_SECONDS', 3600))
FFMPEG = os.getenv('PIANO_FFMPEG', 'ffmpeg')
FFPROBE = os.getenv('PIANO_FFPROBE', 'ffprobe')
MODEL_PYTHON = os.getenv('PIANO_MODEL_PYTHON', str(ROOT / '.venv-model' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')))
PIANO_CRNN_PYTHON = os.getenv('PIANO_CRNN_PYTHON', str(ROOT / '.venv-piano' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')))
PIANO_CRNN_CHECKPOINT = Path(os.getenv('PIANO_CRNN_CHECKPOINT', ROOT / '.tools/models/piano-crnn.pth'))

def initialize():
    for folder in ('sources', 'pieces', 'jobs'):
        (DATA / folder).mkdir(parents=True, exist_ok=True)
