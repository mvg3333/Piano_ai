import json
import logging
import math
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import store
from .config import ROOT, DATA, MAX_BYTES, MAX_SECONDS, FFMPEG, FFPROBE
from .domain import ScoreSettings, NoteEdit, apply_revision
from .ingestion import ALLOWED_EXTENSIONS, parse_youtube, probe
from .midi_io import read_midi, write_midi
from .transcription import get_adapter
from .youtube_titles import fetch_youtube_title, is_placeholder, FALLBACK_TITLE
from .library import delete_piece, retry_file_deletions

@asynccontextmanager
async def lifespan(app):
    store.setup()
    retry_file_deletions()
    yield

app = FastAPI(title='Piano AI', version='1.0.0', lifespan=lifespan)
from .arrangement_api import router as arrangement_router
app.include_router(arrangement_router)

class YouTubeInput(BaseModel):
    url: str

class JobInput(BaseModel):
    sourceId: str
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, gt=0)
    settings: ScoreSettings | None = None

class TranscriptionInput(BaseModel):
    settings: ScoreSettings

class RevisionInput(BaseModel):
    settings: ScoreSettings
    edits: list[NoteEdit] = []

class TitleInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)

def get_piece(piece_id):
    piece = store.piece_get(piece_id)
    if piece_id == 'demo' and piece is None:
        from .demo import make_demo
        piece = make_demo()
    if piece is None:
        raise HTTPException(404, 'Piece not found')
    return piece

@app.get('/api/health')
def health():
    adapter = get_adapter()
    return {'ok':True, 'model':adapter.available(), 'engine':adapter.name, 'ffmpeg':bool(shutil.which(FFMPEG)),
            'ffprobe':bool(shutil.which(FFPROBE)), 'maxBytes':MAX_BYTES, 'maxSeconds':MAX_SECONDS}

@app.get('/api/pieces')
def pieces():
    with store.db() as conn:
        rows = conn.execute('SELECT id,title,created FROM pieces ORDER BY created DESC').fetchall()
    return [dict(r) for r in rows]

@app.get('/api/pieces/{piece_id}')
def piece_read(piece_id: str):
    return get_piece(piece_id)

@app.delete('/api/pieces/{piece_id}')
def piece_delete(piece_id: str):
    try:
        return delete_piece(piece_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

@app.patch('/api/pieces/{piece_id}')
def rename(piece_id: str, request: TitleInput):
    piece = get_piece(piece_id)
    piece['title'] = request.title.strip() or 'Untitled'
    piece['titleEdited'] = True
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if piece_id == 'demo':
            conn.execute('INSERT OR IGNORE INTO pieces VALUES (?,?,?,?)', (piece_id, piece['title'], json.dumps(piece), time.time()))
        result = conn.execute('UPDATE pieces SET title=?,payload=? WHERE id=?', (piece['title'], json.dumps(piece), piece_id))
        if not result.rowcount:
            raise HTTPException(404, 'Piece no longer exists')
    return piece

@app.post('/api/pieces/{piece_id}/revisions')
def revise(piece_id: str, request: RevisionInput):
    original = get_piece(piece_id)
    try:
        piece = apply_revision(original, request.settings.model_dump(), [e.model_dump() for e in request.edits])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logging.exception('Score generation failed for piece %s', piece_id)
        raise HTTPException(500, 'Could not generate the score. Your saved piece and original notes are unchanged.') from exc
    revision_id = store.uid()
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if piece_id != 'demo' and not conn.execute('SELECT 1 FROM pieces WHERE id=?', (piece_id,)).fetchone():
            raise HTTPException(404, 'Piece no longer exists')
        conn.execute('INSERT INTO revisions VALUES (?,?,?,?)', (revision_id,piece_id,json.dumps(request.model_dump()),time.time()))
        conn.execute('INSERT INTO pieces VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,payload=excluded.payload',
                     (piece_id, piece['title'], json.dumps(piece), time.time()))
    return piece

@app.post('/api/pieces/{piece_id}/transcriptions', status_code=202)
def retranscribe(piece_id: str, request: TranscriptionInput):
    if not piece_id.isascii() or not piece_id.isalnum() or len(piece_id) > 80:
        raise HTTPException(400, 'Invalid saved piece ID')
    original = get_piece(piece_id)
    if (piece_id == 'demo' or original.get('source', {}).get('kind') in ('demo', 'midi')
            or original.get('raw', {}).get('provenance', {}).get('kind') in ('demo', 'midi')):
        raise HTTPException(409, 'This piece has no recorded audio to transcribe. Import a recording first.')

    data_root = DATA.resolve()
    pieces_root = (DATA/'pieces').resolve()
    directory = (pieces_root/piece_id).resolve()
    audio = (directory/'source.wav').resolve()
    if (pieces_root.parent != data_root or pieces_root.name != 'pieces'
            or directory.parent != pieces_root or directory.name != piece_id
            or audio.parent != directory or audio.name != 'source.wav'):
        raise HTTPException(400, 'Piece audio is outside the storage directory')
    if not audio.is_file():
        raise HTTPException(404, 'The original audio is no longer stored. Import the recording again to transcribe it.')
    if not get_adapter().available():
        raise HTTPException(409, 'The transcription model is not installed. Run python -m scripts.setup_piano, then try again.')
    try:
        duration = float(original.get('raw', {}).get('duration', original.get('duration', 0)))
    except (TypeError, ValueError):
        duration = 0
    if not math.isfinite(duration) or not 0 < duration <= MAX_SECONDS:
        raise HTTPException(409, 'The saved recording duration is invalid. Import the recording again.')

    source_id, job_id, now = store.uid(), store.uid(), time.time()
    sources_root = (DATA/'sources').resolve()
    snapshot = (sources_root/f'{source_id}.wav').resolve()
    if (sources_root.parent != data_root or sources_root.name != 'sources'
            or snapshot.parent != sources_root):
        raise HTTPException(400, 'Source storage is outside the data directory')
    suffix = ' (new transcription)'
    title = str(original.get('title') or 'Untitled')[:160-len(suffix)] + suffix
    source = {'id': source_id, 'kind': 'saved-audio', 'path': str(snapshot),
              'duration': duration, 'title': title, 'sourcePieceId': piece_id,
              'clipStart': original.get('clipStart', 0),
              'originalSource': {k: v for k, v in original.get('source', {}).items() if k != 'path'}}
    job_request = JobInput(sourceId=source_id, start=0, end=duration, settings=request.settings)
    try:
        # The queued job owns its recording copy. Deleting or editing the
        # original piece later cannot alter an already requested transcription.
        shutil.copyfile(audio, snapshot)
        with store.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if not conn.execute('SELECT 1 FROM pieces WHERE id=?', (piece_id,)).fetchone():
                raise HTTPException(404, 'Piece no longer exists')
            conn.execute('INSERT INTO sources VALUES (?,?)', (source_id, json.dumps(source)))
            conn.execute('INSERT INTO jobs (id,source_id,status,stage,payload,created,updated) VALUES (?,?,?,?,?,?,?)',
                         (job_id, source_id, 'queued', 'queued', json.dumps(job_request.model_dump()), now, now))
    except Exception as exc:
        try:
            snapshot.unlink(missing_ok=True)
        except OSError:
            logging.exception('Could not remove unused transcription audio %s', source_id)
        if isinstance(exc, HTTPException):
            raise
        logging.exception('Could not queue a new transcription for piece %s', piece_id)
        if isinstance(exc, OSError):
            raise HTTPException(409, 'Could not copy the saved audio. Close applications using the recording and try again. Your saved piece is unchanged.') from exc
        raise HTTPException(500, 'Could not queue a new transcription. Your saved piece is unchanged; please try again.') from exc
    return store.job_get(job_id)

@app.get('/api/pieces/{piece_id}/export/{format}')
def export(piece_id: str, format: str, arrangementId: str | None = None):
    piece = get_piece(piece_id)
    if arrangementId:
        from .arrangement_api import read_arrangement
        piece = read_arrangement(piece_id, arrangementId)['performance']
    if format == 'midi':
        return Response(write_midi(piece), media_type='audio/midi', headers={'Content-Disposition':'attachment; filename="piano-ai.mid"'})
    if format == 'musicxml':
        if not piece['score']['musicxml']:
            raise HTTPException(409, 'Regenerate a score before exporting MusicXML.')
        return Response(piece['score']['musicxml'], media_type='application/vnd.recordare.musicxml+xml', headers={'Content-Disposition':'attachment; filename="piano-ai.musicxml"'})
    raise HTTPException(404, 'Export format not found')

@app.get('/api/pieces/{piece_id}/media')
def media(piece_id: str):
    get_piece(piece_id)
    if not piece_id.isalnum():
        raise HTTPException(400, 'Invalid piece ID')
    path = DATA/'pieces'/piece_id/'source.wav'
    if not path.is_file():
        raise HTTPException(404, 'No original audio is stored for this piece')
    return FileResponse(path, media_type='audio/wav')

@app.post('/api/sources/youtube')
def youtube(request: YouTubeInput):
    try:
        parsed = parse_youtube(request.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    source = {**parsed, 'id':store.uid(), 'kind':'youtube',
              'title':fetch_youtube_title(parsed['url']) or FALLBACK_TITLE}
    store.source_save(source)
    return source

@app.post('/api/sources/upload')
async def upload(file: UploadFile, youtubeReference: str | None = None):
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS | {'.mid', '.midi'}:
        raise HTTPException(415, 'Choose MIDI, WAV, MP3, FLAC, OGG, M4A, AAC, MP4, or WebM.')
    source_id = store.uid()
    path = DATA/'sources'/f'{source_id}{suffix}'
    size = 0
    try:
        with path.open('wb') as target:
            while chunk := await file.read(1024*1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, f'File exceeds the {MAX_BYTES//1024//1024} MiB limit.')
                target.write(chunk)
        if suffix in ('.mid', '.midi'):
            raw = read_midi(path)
            if raw['duration'] > MAX_SECONDS or len(raw['notes']) > 100000:
                raise ValueError('MIDI exceeds the duration or 100,000-note limit.')
            settings = ScoreSettings(tempo=raw['tempos'][0]['bpm'], useMidiTempo=True)
            if raw['meters']:
                settings.numerator = raw['meters'][0]['numerator']
                settings.denominator = raw['meters'][0]['denominator']
            piece = apply_revision({'id':source_id, 'title':Path(file.filename or 'Imported MIDI').stem, 'subtitle':'Imported MIDI · estimated hands',
                                    'source':{'kind':'midi'}, 'clipStart':0, 'raw':raw, 'duration':raw['duration']}, settings.model_dump(), [])
            directory = DATA/'pieces'/source_id
            directory.mkdir(parents=True, exist_ok=True)
            (directory/'raw.json').write_text(json.dumps(raw), encoding='utf-8')
            store.piece_save(piece)
            return {'piece':piece}
        # ffprobe and parsing run off the event loop.
        from starlette.concurrency import run_in_threadpool
        duration = await run_in_threadpool(probe, path)
        source = {'id':source_id, 'kind':'upload', 'path':str(path), 'duration':duration, 'title':Path(file.filename or 'Recording').stem, 'suggestedStart':0}
        if youtubeReference:
            original = store.source_get(youtubeReference)
            if original and original['kind']=='youtube':
                source['youtubeReference'] = {k: original[k] for k in ('url','videoId')}
                if not is_placeholder(original.get('title'), original['videoId']):
                    source['title'] = original['title']
        store.source_save(source)
        return {k:v for k,v in source.items() if k!='path'}
    except (ValueError, EOFError, OSError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

@app.post('/api/jobs', status_code=202)
def create_job(request: JobInput):
    if not store.source_get(request.sourceId):
        raise HTTPException(404, 'Source not found')
    if request.end is not None and request.end <= request.start:
        raise HTTPException(422, 'End must be after start')
    job_id, now = store.uid(), time.time()
    with store.db() as conn:
        conn.execute('INSERT INTO jobs (id,source_id,status,stage,payload,created,updated) VALUES (?,?,?,?,?,?,?)',
                     (job_id,request.sourceId,'queued','queued',json.dumps(request.model_dump()),now,now))
    return store.job_get(job_id)

@app.get('/api/jobs/{job_id}')
def read_job(job_id: str):
    job = store.job_get(job_id)
    if not job:
        raise HTTPException(404, 'Job not found')
    return job

@app.post('/api/jobs/{job_id}/cancel')
def cancel_job(job_id: str):
    read_job(job_id)
    with store.db() as conn:
        conn.execute("UPDATE jobs SET cancel=1,updated=? WHERE id=? AND status IN ('running','queued')", (time.time(),job_id))
    return read_job(job_id)

@app.post('/api/jobs/{job_id}/retry', status_code=202)
def retry_job(job_id: str):
    job = read_job(job_id)
    if job['status'] not in ('failed','cancelled'):
        raise HTTPException(409, 'Only failed or cancelled jobs can be retried')
    return create_job(JobInput(**job['request']))

dist = ROOT/'frontend/dist'
if dist.is_dir():
    app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
