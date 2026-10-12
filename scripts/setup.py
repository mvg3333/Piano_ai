"""Windows setup without changing PowerShell execution policy or system Python."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PYTHON='3.11.17'
NODE='24.21.0'

def run(*args):
    print('Running:', ' '.join(str(x) for x in args),flush=True)
    subprocess.run([str(x) for x in args],cwd=ROOT,env=os.environ,check=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--with-model',action='store_true',help='Install the Basic Pitch fallback model')
    parser.add_argument('--with-piano-model',action='store_true',help='Install the piano-specific CRNN model (recommended for solo piano)')
    args=parser.parse_args()
    if os.name!='nt':raise SystemExit('This bootstrap targets Windows. See README for the architecture and dependencies.')
    tools=ROOT/'.tools';tools.mkdir(exist_ok=True)
    uv=tools/'uv/bin/uv.exe'
    if not uv.exists():run(sys.executable,'-m','pip','install','--target',tools/'uv','uv==0.13.0')
    os.environ['UV_PYTHON_INSTALL_DIR']=str(tools/'python')
    os.environ['UV_CACHE_DIR']=str(ROOT/'.uv-cache')
    run(uv,'python','install',PYTHON,'--no-bin')
    python=ROOT/'.venv/Scripts/python.exe'
    if not python.exists():run(uv,'venv','--python',PYTHON,ROOT/'.venv')
    run(uv,'pip','sync',ROOT/'backend/requirements.lock','--python',python)
    node_dir=tools/f'node-v{NODE}-win-x64'
    if not (node_dir/'node.exe').exists():
        filename=f'node-v{NODE}-win-x64.zip';base=f'https://nodejs.org/dist/v{NODE}/'
        archive=tools/filename
        print('Downloading portable Node',NODE,flush=True)
        urllib.request.urlretrieve(base+filename,archive)
        checksums=urllib.request.urlopen(base+'SHASUMS256.txt').read().decode()
        expected=next(line.split()[0] for line in checksums.splitlines() if line.split()[-1]==filename)
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:raise RuntimeError('Node checksum mismatch')
        with zipfile.ZipFile(archive) as package:package.extractall(tools)
    os.environ['PATH']=str(node_dir)+os.pathsep+os.environ['PATH']
    npm=node_dir/'npm.cmd'
    run(npm,'--prefix',ROOT/'frontend','ci')
    if args.with_model:
        model=ROOT/'.venv-model/Scripts/python.exe'
        if not model.exists():run(uv,'venv','--python',PYTHON,ROOT/'.venv-model')
        run(uv,'pip','sync',ROOT/'backend/model-requirements.lock','--python',model)
    if args.with_piano_model:
        run(python,'-m','scripts.setup_piano')
    run(python,'-m','backend.demo')
    run(python,'-m','scripts.build_icons')
    run(npm,'--prefix',ROOT/'frontend','run','build')
    run(python,'-m','scripts.doctor')
    print('Ready. Run .\\.venv\\Scripts\\python.exe -m scripts.run, then open http://localhost:8000')

if __name__=='__main__':main()
