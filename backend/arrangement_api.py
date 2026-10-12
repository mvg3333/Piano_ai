"""Transactional arrangement persistence; generation never rewrites a piece."""
import json
import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import store
from .arrangement import ArrangementSettings, Guidance, arrange, fingerprint, performance

router = APIRouter()


class ArrangementInput(BaseModel):
    settings: ArrangementSettings
    expectedSourceFingerprint: str
    predecessorId: str | None = None
    name: str = Field(default='Simplified arrangement', min_length=1, max_length=160)


class GuidanceInput(BaseModel):
    guidance: Guidance
    expectedSourceFingerprint: str


def source(piece_id):
    from .app import get_piece
    return get_piece(piece_id)


def _check(piece, expected):
    if fingerprint(piece) != expected:
        raise HTTPException(409, 'The source changed. Reload the piece and try again; saved arrangements are unchanged.')


def read_arrangement(piece_id, arrangement_id):
    with store.db() as conn:
        row = conn.execute('SELECT payload,source_id FROM arrangements WHERE id=? AND piece_id=?', (arrangement_id, piece_id)).fetchone()
        snapshot = conn.execute('SELECT payload,fingerprint FROM arrangement_sources WHERE id=?', (row['source_id'],)).fetchone() if row else None
    if not row or not snapshot:
        raise HTTPException(404, 'Arrangement not found')
    result = json.loads(row['payload'])
    saved_source = json.loads(snapshot['payload'])
    result['sourcePerformance'] = saved_source['performance']
    result['sourceGuidance'] = saved_source['guidance']
    result['outdated'] = snapshot['fingerprint'] != fingerprint(source(piece_id))
    return result


@router.get('/api/pieces/{piece_id}/arrangements')
def arrangements_list(piece_id: str):
    piece = source(piece_id)
    current = fingerprint(piece)
    with store.db() as conn:
        rows = conn.execute('SELECT a.payload,s.fingerprint FROM arrangements a JOIN arrangement_sources s ON s.id=a.source_id WHERE a.piece_id=? ORDER BY a.created DESC', (piece_id,)).fetchall()
    return {'sourceFingerprint': current, 'guidance': piece.get('guidance', Guidance().model_dump()),
            'arrangements': [{k: v for k, v in json.loads(r['payload']).items() if k in ('id', 'name', 'settings', 'created', 'sourceSnapshotId', 'sourceFingerprint', 'predecessorId')} | {'outdated': r['fingerprint'] != current} for r in rows]}


@router.get('/api/pieces/{piece_id}/arrangements/{arrangement_id}')
def arrangement_read(piece_id: str, arrangement_id: str):
    return read_arrangement(piece_id, arrangement_id)


@router.post('/api/pieces/{piece_id}/arrangements', status_code=201)
def arrangement_create(piece_id: str, request: ArrangementInput):
    piece = source(piece_id)
    _check(piece, request.expectedSourceFingerprint)
    if request.predecessorId:
        read_arrangement(piece_id, request.predecessorId)
    try:
        result = arrange(piece, request.settings.model_dump())
    except Exception as exc:
        logging.exception('Arrangement generation failed for %s', piece_id)
        raise HTTPException(500, 'Could not generate the arrangement and score. Your source and saved arrangements are unchanged.') from exc
    ident, snapshot_id, now = store.uid(), store.uid(), time.time()
    snapshot = {'performance': performance(piece), 'edits': piece.get('edits', []),
                'guidance': piece.get('guidance', Guidance().model_dump())}
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT payload FROM pieces WHERE id=?', (piece_id,)).fetchone()
        if not row and piece_id != 'demo':
            raise HTTPException(404, 'Piece no longer exists')
        current = json.loads(row[0]) if row else piece
        _check(current, request.expectedSourceFingerprint)
        if not row:
            conn.execute('INSERT INTO pieces VALUES (?,?,?,?)', (piece_id, piece['title'], json.dumps(piece), now))
        if request.predecessorId and not conn.execute('SELECT 1 FROM arrangements WHERE id=? AND piece_id=?', (request.predecessorId, piece_id)).fetchone():
            raise HTTPException(409, 'The previous arrangement was deleted. Reload and try again.')
        existing = conn.execute('SELECT id FROM arrangement_sources WHERE piece_id=? AND fingerprint=?', (piece_id, request.expectedSourceFingerprint)).fetchone()
        if existing:
            snapshot_id = existing[0]
        else:
            conn.execute('INSERT INTO arrangement_sources VALUES (?,?,?,?)', (snapshot_id, piece_id, request.expectedSourceFingerprint, json.dumps(snapshot)))
        result.update(id=ident, name=request.name.strip() or 'Simplified arrangement', created=now, pieceId=piece_id,
                      sourceSnapshotId=snapshot_id, sourceFingerprint=request.expectedSourceFingerprint, predecessorId=request.predecessorId)
        conn.execute('INSERT INTO arrangements VALUES (?,?,?,?,?)', (ident, piece_id, snapshot_id, json.dumps(result), now))
    return read_arrangement(piece_id, ident)


@router.delete('/api/pieces/{piece_id}/arrangements/{arrangement_id}')
def arrangement_delete(piece_id: str, arrangement_id: str):
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        result = conn.execute('DELETE FROM arrangements WHERE id=? AND piece_id=?', (arrangement_id, piece_id))
        if not result.rowcount:
            raise HTTPException(404, 'Arrangement not found')
        conn.execute('DELETE FROM arrangement_sources WHERE piece_id=? AND id NOT IN (SELECT source_id FROM arrangements)', (piece_id,))
    return {'deleted': True, 'id': arrangement_id}


@router.put('/api/pieces/{piece_id}/guidance')
def guidance_update(piece_id: str, request: GuidanceInput):
    piece = source(piece_id)
    known = {n['id'] for n in piece['raw']['notes']}
    guidance = request.guidance.model_dump()
    if (set(guidance['roles']) | set(guidance['protectedNoteIds'])) - known:
        raise HTTPException(422, 'Guidance refers to a missing source note')
    guidance['protectedNoteIds'] = sorted(set(guidance['protectedNoteIds']))
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT payload FROM pieces WHERE id=?', (piece_id,)).fetchone()
        if not row and piece_id != 'demo':
            raise HTTPException(404, 'Piece no longer exists')
        current = json.loads(row[0]) if row else piece
        _check(current, request.expectedSourceFingerprint)
        current['guidance'] = guidance
        conn.execute('INSERT INTO pieces VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (piece_id, current['title'], json.dumps(current), time.time()))
        conn.execute('INSERT INTO revisions VALUES (?,?,?,?)', (store.uid(), piece_id, json.dumps({'guidance': guidance}), time.time()))
    return {'guidance': guidance, 'sourceFingerprint': fingerprint(current)}
