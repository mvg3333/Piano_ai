"""Local integration check. Requires the API, worker and benchmark audio."""
import json
import time
from pathlib import Path
import httpx
from backend.config import DATA

def main():
    client=httpx.Client(base_url='http://127.0.0.1:8000',timeout=90)
    path=DATA/'benchmark/piano-10s.wav'
    with path.open('rb') as f:
        upload=client.post('/api/sources/upload',files={'file':('Piano verification.wav',f,'audio/wav')})
    upload.raise_for_status();source=upload.json()
    created=client.post('/api/jobs',json={'sourceId':source['id'],'start':2,'end':7});created.raise_for_status()
    job=created.json();stages=[];started=time.monotonic()
    while job['status'] in ('queued','running'):
        if job['stage'] not in stages:stages.append(job['stage']);print(job['stage'],flush=True)
        if time.monotonic()-started>240:raise TimeoutError('Job took longer than four minutes')
        time.sleep(.4);job=client.get('/api/jobs/'+job['id']).json()
    assert job['status']=='completed',job
    piece=client.get('/api/pieces/'+job['piece_id']).json()
    assert piece['clipStart']==2 and piece['duration']==5
    assert piece['notes'] and piece['score']['musicxml']
    assert client.get('/api/pieces/'+piece['id']+'/media',headers={'Range':'bytes=0-100'}).status_code==206
    assert client.get('/api/pieces/'+piece['id']+'/export/midi').content.startswith(b'MThd')
    assert client.get('/api/pieces/'+piece['id']+'/export/musicxml').status_code==200
    # Cancel a running process, not just a queued status flag.
    cancelled=client.post('/api/jobs',json={'sourceId':source['id'],'start':0,'end':10}).json()
    for _ in range(100):
        current=client.get('/api/jobs/'+cancelled['id']).json()
        if current['stage']=='loading model':break
        time.sleep(.2)
    assert current['status']=='running',current
    client.post('/api/jobs/'+cancelled['id']+'/cancel')
    for _ in range(100):
        current=client.get('/api/jobs/'+cancelled['id']).json()
        if current['status']=='cancelled':break
        time.sleep(.2)
    assert current['status']=='cancelled',current
    report={'jobId':job['id'],'pieceId':piece['id'],'stagesObserved':stages,'clipStart':2,'clipDuration':5,
            'noteCount':len(piece['notes']),'scoreGenerated':True,'mediaRangeResponse':206,'exportsPassed':True,'runningCancellationPassed':True}
    (DATA/'benchmark/integration.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
