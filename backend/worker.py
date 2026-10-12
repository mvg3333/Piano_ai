"""Single-worker durable queue; the API never executes heavy model inference."""
import os
import subprocess
import sys
import time
import psutil
from . import store
from .config import DATA, ROOT

def stop_tree(process):
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in reversed(children):
            try: child.kill()
            except psutil.NoSuchProcess: pass
        parent.kill()
        psutil.wait_procs(children+[parent], timeout=5)
    except psutil.NoSuchProcess:
        pass

def work():
    store.setup()
    print('Piano AI worker ready (one CPU job at a time)', flush=True)
    while True:
        with store.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            now = time.time()
            conn.execute("UPDATE jobs SET status='failed', stage='interrupted',error='Worker interrupted. Retry this job.', updated=? WHERE status='running' AND heartbeat < ?", (now,now-30))
            conn.execute("UPDATE jobs SET status='cancelled',stage='cancelled',updated=? WHERE status='queued' AND cancel=1", (now,))
            running = conn.execute("SELECT id FROM jobs WHERE status='running'").fetchone()
            job = None if running else conn.execute("SELECT id FROM jobs WHERE status='queued' AND cancel=0 ORDER BY created LIMIT 1").fetchone()
            if job:
                conn.execute("UPDATE jobs SET status='running',stage='validating',heartbeat=?,updated=? WHERE id=?", (now,now,job['id']))
        if not job:
            time.sleep(1)
            continue
        job_id = job['id']
        folder = DATA/'jobs'/job_id
        folder.mkdir(parents=True, exist_ok=True)
        with (folder/'worker.log').open('w', encoding='utf-8') as log:
            proc = subprocess.Popen([sys.executable, '-m', 'backend.pipeline', job_id], cwd=ROOT, stdout=log, stderr=log)
            try:
                while proc.poll() is None:
                    current = store.job_get(job_id)
                    if current['cancel']:
                        stop_tree(proc)
                        with store.db() as conn:
                            conn.execute("UPDATE jobs SET status='cancelled',stage='cancelled',updated=? WHERE id=? AND status!='completed'", (time.time(),job_id))
                        break
                    with store.db() as conn:
                        conn.execute('UPDATE jobs SET heartbeat=? WHERE id=?', (time.time(),job_id))
                    time.sleep(.5)
            except KeyboardInterrupt:
                stop_tree(proc)
                with store.db() as conn:
                    conn.execute("UPDATE jobs SET status='failed',stage='interrupted',error='Worker stopped. Retry this job.',updated=? WHERE id=? AND status='running'", (time.time(),job_id))
                return
        with store.db() as conn:
            conn.execute("UPDATE jobs SET status='failed',stage='failed',error='Processing exited unexpectedly. See job log.',updated=? WHERE id=? AND status='running'", (time.time(),job_id))

if __name__ == '__main__':
    work()
