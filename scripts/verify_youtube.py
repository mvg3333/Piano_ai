import json
import time
import httpx
from backend.config import DATA

def main():
    client=httpx.Client(base_url='http://127.0.0.1:8000',timeout=30)
    source=client.post('/api/sources/youtube',json={'url':'https://www.youtube.com/watch?v=5U-WL0QvKCg&t=5s'}).json()
    job=client.post('/api/jobs',json={'sourceId':source['id'],'start':5,'end':10}).json()
    stages=[];started=time.monotonic()
    while job['status'] in ('queued','running'):
        if job['stage'] not in stages:stages.append(job['stage']);print(job['stage'],flush=True)
        if time.monotonic()-started>240:raise TimeoutError('YouTube verification exceeded four minutes')
        time.sleep(.5);job=client.get('/api/jobs/'+job['id']).json()
    report={'videoId':'5U-WL0QvKCg','interval':[5,10],'status':job['status'],'stages':stages,'error':job.get('error'),'wallSeconds':round(time.monotonic()-started,3)}
    if job.get('piece_id'):
        piece=client.get('/api/pieces/'+job['piece_id']).json()
        report.update(pieceId=piece['id'],notes=len(piece['notes']),clipStart=piece['clipStart'],score=bool(piece['score']['musicxml']))
    (DATA/'benchmark/youtube.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
