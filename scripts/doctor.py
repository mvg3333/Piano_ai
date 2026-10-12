import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
from backend.config import FFMPEG,FFPROBE,MODEL_PYTHON,ROOT
from scripts.setup_piano import CHECKPOINT_SHA256, CHECKPOINT_SIZE, file_digest

def check_environment(label, python, code, timeout=90):
    try:
        result=subprocess.run([str(python),'-c',code],capture_output=True,text=True,timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f'{label} check failed: {error}')
        return False
    print(result.stdout.strip() if result.returncode==0 else f'{label} check failed: {result.stderr[-1800:]}')
    return result.returncode==0

def main():
    print('Piano AI dependency check')
    for binary in (FFMPEG,FFPROBE):
        if shutil.which(binary):
            result=subprocess.run([binary,'-version'],capture_output=True,text=True,timeout=15)
            print(result.stdout.splitlines()[0])
        else:print(f'MISSING: {binary}. Upload transcription needs FFmpeg and ffprobe on PATH.')
    print('music21',importlib.metadata.version('music21'))
    print('yt-dlp',importlib.metadata.version('yt-dlp'))
    if Path(MODEL_PYTHON).is_file():
        check_environment('Basic Pitch',MODEL_PYTHON,'from basic_pitch.inference import Model; from basic_pitch import ICASSP_2022_MODEL_PATH; Model(ICASSP_2022_MODEL_PATH); print("Basic Pitch fallback model loads on CPU")')
    else:print('Basic Pitch fallback not installed. Optional: python scripts/setup.py --with-model')
    piano_python=Path(os.getenv('PIANO_CRNN_PYTHON',ROOT/'.venv-piano/Scripts/python.exe'))
    checkpoint=Path(os.getenv('PIANO_CRNN_CHECKPOINT',ROOT/'.tools/models/piano-crnn.pth'))
    if piano_python.is_file():
        ready=check_environment('Piano CRNN',piano_python,'import torch, librosa; from piano_transcription_inference import PianoTranscription; print("Piano CRNN dependencies load; PyTorch", torch.__version__, "CPU")')
        try:
            verified=(checkpoint.is_file() and checkpoint.stat().st_size==CHECKPOINT_SIZE
                      and file_digest(checkpoint)==CHECKPOINT_SHA256)
        except OSError as error:
            print(f'Piano checkpoint check failed: {error}')
            verified=False
        if verified:
            print('Piano CRNN checkpoint SHA-256 verified.' + (' Preferred for new transcriptions.' if ready else ''))
        else:print('Piano CRNN checkpoint missing or unrecognized. Restore the official checkpoint: python -m scripts.setup_piano')
    else:print('Piano CRNN not installed. For solo piano: python -m scripts.setup_piano')

if __name__=='__main__':main()
