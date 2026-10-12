import json
import os
from pathlib import Path
import subprocess
import sys
import time
from . import store
from .config import DATA, MAX_BYTES, MAX_SECONDS, ROOT
from .domain import ScoreSettings, apply_revision
from .ingestion import decode_clip, probe
from .transcription import get_adapter
from .youtube_titles import clean_title, is_placeholder, FALLBACK_TITLE

def run(job_id):
    job = store.job_get(job_id)
    source = store.source_get(job['source_id'])
    request = job['request']
    job_dir = DATA/'jobs'/job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    path = Path(source.get('path', ''))
    if source['kind'] == 'youtube':
        store.job_stage(job_id, 'acquiring')
        # Isolated config/plugins, no credentials, one allowlisted canonical URL.
        command = [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-plugin-dirs', '--no-playlist',
                   '--no-progress', '--no-warnings', '--socket-timeout', '30', '--retries', '2',
                   '--max-filesize', str(MAX_BYTES), '--match-filter', f'duration <= {MAX_SECONDS} & !is_live',
                   '--js-runtimes', f"node:{os.getenv('PIANO_NODE', 'node')}", '-f', 'bestaudio/best',
                   '--print', 'after_move:%(title)j',
                   '-o', str(job_dir/'source.%(ext)s'), '--', source['url']]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900)
        candidates = [p for p in job_dir.glob('source.*') if p.suffix not in ('.part', '.ytdl')]
        if result.returncode or not candidates:
            raise RuntimeError('YouTube audio acquisition is unavailable for this video. Upload audio/video instead; the YouTube reference is preserved. '+result.stderr[-1500:])
        path = candidates[0]
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('Downloaded media exceeds the configured size limit.')
        # The downloader already has metadata; recover the name even if oEmbed
        # was unavailable when the link was entered. JSON protects Unicode/newlines.
        for line in reversed(result.stdout.splitlines()):
            try:
                title = clean_title(json.loads(line))
            except ValueError:
                continue
            if title:
                source['title'] = title
                break
        if is_placeholder(source.get('title'), source['videoId']):
            source['title'] = FALLBACK_TITLE
        store.source_save(source)
    store.job_stage(job_id, 'validating')
    duration = probe(path)
    start = request.get('start', 0)
    end = request.get('end') or duration
    if not 0 <= start < end <= duration+.05:
        raise ValueError(f'Choose an interval inside the {duration:.2f}-second recording.')
    store.job_stage(job_id, 'decoding')
    wav = job_dir/'clip.wav'
    decode_clip(path, wav, start, end)
    store.job_stage(job_id, 'loading model')
    adapter = get_adapter()
    if not adapter.available():
        raise RuntimeError('A transcription model is not installed. Run python -m scripts.setup_piano; MIDI and the demo work independently.')
    began = time.perf_counter()
    raw = adapter.transcribe(wav, job_dir/'raw.json', on_stage=lambda stage: store.job_stage(job_id, stage))
    evidence = raw.pop('noteEvidence', {})
    raw['duration'] = end-start
    clip_start = source.get('clipStart', 0) + start if source['kind'] == 'saved-audio' else start
    raw['provenance']['clipStart'] = clip_start
    if not raw['notes']:
        raise ValueError('The model detected no notes. Try a clearer solo-piano interval.')
    store.job_stage(job_id, 'generating score')
    settings = ScoreSettings(**(request.get('settings') or {})).model_dump()
    if not request.get('settings'):
        try:
            import librosa
            audio, sr = librosa.load(wav, sr=22050)
            bpm, _ = librosa.beat.beat_track(y=audio, sr=sr)
            import numpy as np
            settings['tempo'] = round(float(np.asarray(bpm).reshape(-1)[0]), 2) or 100
            settings['tempo'] = min(300, max(20, settings['tempo']))
        except Exception:
            pass
    piece_id = store.uid()
    public_source = (dict(source['originalSource']) if source['kind'] == 'saved-audio'
                     else {k:v for k,v in source.items() if k != 'path'})
    public_source['mediaClip'] = True
    piece = {'id':piece_id, 'title':source['title'], 'subtitle':adapter.name+' transcription · draft score',
             'raw':raw, 'noteEvidence':evidence, 'source':public_source, 'clipStart':clip_start, 'duration':end-start}
    if source.get('sourcePieceId'):
        piece['previousPieceId'] = source['sourcePieceId']
    try:
        piece = apply_revision(piece, settings, [])
    except Exception as exc:
        import logging
        from .domain import tempo_map, prepare_notes
        logging.exception('Score generation failed for job %s', job_id)
        notes, cleanup, hands = prepare_notes(raw, [], settings, evidence)
        piece.update(settings=settings, edits=[], notes=notes, cleanup=cleanup, handAssignment=hands, score={'musicxml':'', 'anchors':tempo_map(settings,raw), 'measures':[], 'fragments':[], 'warning':'Score generation failed. Your notes were saved. Try Regenerate & save score in Practice settings.'})
    store.job_stage(job_id, 'saving')
    directory = DATA/'pieces'/piece_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'raw.json').write_text(json.dumps(raw), encoding='utf-8')
    wav.replace(directory/'source.wav')
    piece['processingSeconds'] = time.perf_counter()-began
    with store.db() as conn:
        current = conn.execute('SELECT cancel,status FROM jobs WHERE id=?', (job_id,)).fetchone()
        if current['cancel'] or current['status'] != 'running':
            raise RuntimeError('Job cancelled before save.')
        conn.execute('INSERT INTO pieces VALUES (?,?,?,?)', (piece_id, piece['title'], json.dumps(piece), time.time()))
        conn.execute("UPDATE jobs SET status='completed',stage='completed',piece_id=?,updated=? WHERE id=?", (piece_id,time.time(),job_id))

if __name__ == '__main__':
    try:
        run(sys.argv[1])
    except Exception as exc:
        with store.db() as conn:
            conn.execute("UPDATE jobs SET status='failed',stage='failed',error=?,updated=? WHERE id=?", (str(exc),time.time(),sys.argv[1]))
        raise
