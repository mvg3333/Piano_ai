"""Explicit opt-in test; caches noncommercial recording under data/."""
import json
import os
import platform
import time
from backend.config import DATA
from backend.ingestion import decode_clip
from backend.transcription import BasicPitchAdapter

def main():
    directory=DATA/'benchmark';directory.mkdir(parents=True,exist_ok=True)
    os.environ['LIBROSA_DATA_DIR']=str(directory)
    import librosa
    librosa.util.example_info('pistachio')
    recording=librosa.example('pistachio')
    clip=directory/'piano-10s.wav';decode_clip(recording,clip,5,15)
    began=time.perf_counter()
    result=BasicPitchAdapter().transcribe(clip,directory/'result.json')
    elapsed=time.perf_counter()-began
    report={'recording':'Pistachio Ice Cream Ragtime — The Piano Lady / Lena Orsa',
            'source':'https://librosa.org/doc/0.10.2/recordings.html','license':'CC BY-NC 3.0; local noncommercial verification only, not bundled',
            'intervalSeconds':[5,15],'clipSeconds':10,'wallSeconds':round(elapsed,3),'modelReportedSeconds':result['provenance']['inferenceSeconds'],
            'noteCount':len(result['notes']),'pitchRange':[min(n['pitch'] for n in result['notes']),max(n['pitch'] for n in result['notes'])],
            'hardware':platform.processor(),'platform':platform.platform(),
            'limitations':'No aligned ground truth; note accuracy was not measured. Basic Pitch does not infer sustain pedal.'}
    (directory/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
