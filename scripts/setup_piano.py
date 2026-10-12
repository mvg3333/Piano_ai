"""Install the optional piano-specific CPU transcriber in this workspace.

Run ``python -m scripts.setup_piano`` after the main application setup.
The lock file intentionally targets Windows x64 and Python 3.11.
"""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_URL = (
    'https://zenodo.org/api/records/4034264/files/'
    'CRNN_note_F1=0.9677_pedal_F1=0.9186.pth/content'
)
CHECKPOINT_SHA256 = 'c3fa9730725bf4a762f1c14bc80cd5986eacda01b026f5a4a2525cd607876141'
CHECKPOINT_SIZE = 171966578
CHECKPOINT_PATH = ROOT / '.tools/models/piano-crnn.pth'
MODEL_PYTHON = ROOT / '.venv-piano/Scripts/python.exe'


def file_digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def download_checkpoint(destination=CHECKPOINT_PATH):
    """Verify an existing checkpoint or atomically install a verified download."""
    destination = Path(destination)
    if (destination.is_file() and destination.stat().st_size == CHECKPOINT_SIZE
            and file_digest(destination) == CHECKPOINT_SHA256):
        print('Piano checkpoint already verified.', flush=True)
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        print('Downloading piano checkpoint (172 MB) from the original Zenodo release...', flush=True)
        request = urllib.request.Request(CHECKPOINT_URL, headers={'User-Agent': 'PianoAI/1.0'})
        with urllib.request.urlopen(request, timeout=60) as response:
            if not response.geturl().startswith('https://'):
                raise RuntimeError('Checkpoint download redirected away from HTTPS.')
            with tempfile.NamedTemporaryFile(prefix=destination.name + '.', suffix='.tmp',
                                             dir=destination.parent, delete=False) as output:
                temporary = Path(output.name)
                digest = hashlib.sha256()
                size = 0
                while chunk := response.read(1024 * 1024):
                    if size + len(chunk) > CHECKPOINT_SIZE:
                        raise RuntimeError('Piano checkpoint download exceeded its expected size; the previous file was preserved.')
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
        if size != CHECKPOINT_SIZE or digest.hexdigest() != CHECKPOINT_SHA256:
            raise RuntimeError('Piano checkpoint checksum or size mismatch; the previous file was preserved.')
        temporary.replace(destination)
        print('Piano checkpoint SHA-256 verified.', flush=True)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run(*args, env=None):
    print('Running:', ' '.join(str(arg) for arg in args), flush=True)
    subprocess.run([str(arg) for arg in args], cwd=ROOT, env=env, check=True)


def setup_piano():
    if os.name != 'nt':
        raise SystemExit('This pinned piano environment targets Windows x64 and Python 3.11.')
    uv = ROOT / '.tools/uv/bin/uv.exe'
    env = {**os.environ, 'UV_PYTHON_INSTALL_DIR': str(ROOT / '.tools/python'),
           'UV_CACHE_DIR': str(ROOT / '.uv-cache')}
    requirements = ROOT / 'backend/piano-requirements.lock'
    if uv.is_file():
        if not MODEL_PYTHON.is_file():
            run(uv, 'venv', '--python', '3.11.17', ROOT / '.venv-piano', env=env)
        run(uv, 'pip', 'sync', requirements, '--python', MODEL_PYTHON, env=env)
    else:
        if not MODEL_PYTHON.is_file():
            application_python = ROOT / '.venv/Scripts/python.exe'
            base = application_python if application_python.is_file() else Path(sys.executable)
            version = subprocess.check_output(
                [str(base), '-c', 'import sys; print("%d.%d" % sys.version_info[:2])'],
                cwd=ROOT, text=True,
            ).strip()
            if version != '3.11':
                raise SystemExit('Run python scripts/setup.py --with-piano-model first to install Python 3.11.')
            run(base, '-m', 'venv', ROOT / '.venv-piano')
        run(MODEL_PYTHON, '-m', 'pip', 'install', '-r', requirements)
    download_checkpoint()
    print('Piano model installed. Restart Piano AI to use it for new transcriptions.', flush=True)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    setup_piano()


if __name__ == '__main__':
    main()
