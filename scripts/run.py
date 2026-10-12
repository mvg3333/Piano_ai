import argparse
import os
import socket
import subprocess
import sys
import time
import psutil
from backend.config import ROOT
from backend.worker import stop_tree

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    node_dir=ROOT/'.tools/node-v24.21.0-win-x64'
    if (node_dir/'node.exe').exists():
        os.environ['PATH']=str(node_dir)+os.pathsep+os.environ['PATH']
        os.environ.setdefault('PIANO_NODE',str(node_dir/'node.exe'))
    # Check before spawning a worker, so a port conflict leaves no background process.
    with socket.socket() as sock:
        try:sock.bind(('0.0.0.0',args.port))
        except OSError:raise SystemExit(f'Port {args.port} is in use. Stop the existing server or choose -Port 8001.')
    children=[]
    try:
        for command in [[sys.executable,'-m','backend.worker'],[sys.executable,'-m','uvicorn','backend.app:app','--host','0.0.0.0','--port',str(args.port)]]:
            children.append(subprocess.Popen(command,cwd=ROOT))
        print(f'\nPiano AI: http://localhost:{args.port}',flush=True)
        for addresses in psutil.net_if_addrs().values():
            for address in addresses:
                if address.family==socket.AF_INET and address.address.startswith(('192.168.','10.','172.')):
                    print(f'Phone/tablet candidate: http://{address.address}:{args.port}',flush=True)
        print('Same Wi-Fi; allow Python on Private networks if Windows asks. Ctrl+C stops both processes.\n',flush=True)
        while all(p.poll() is None for p in children):time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(children):
            if process.poll() is None:stop_tree(process)

if __name__=='__main__':main()
