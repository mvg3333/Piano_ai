"""Delete saved pieces and retry local file cleanup after interrupted deletions."""
import logging
import re
import shutil
from . import store


def piece_directory(piece_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', piece_id) or piece_id == 'demo':
        raise ValueError('Invalid saved piece ID')
    base = (store.DATA / 'pieces').resolve()
    target = (base / piece_id).resolve()
    # Resolve junctions/symlinks before any recursive filesystem operation.
    if base.parent != store.DATA.resolve() or base.name != 'pieces' or target.parent != base or target.name != piece_id:
        raise ValueError('Piece files are outside the storage directory')
    return target


def purge_piece_files(piece_id):
    try:
        with store.db() as conn:
            pending = conn.execute('SELECT 1 FROM pending_piece_deletions WHERE id=?', (piece_id,)).fetchone()
            exists = conn.execute('SELECT 1 FROM pieces WHERE id=?', (piece_id,)).fetchone()
        if not pending:
            return True
        if exists:
            return False
        target = piece_directory(piece_id)
        if target.exists():
            shutil.rmtree(target)
        with store.db() as conn:
            conn.execute('DELETE FROM pending_piece_deletions WHERE id=?', (piece_id,))
        return True
    except (OSError, ValueError):
        logging.exception('Local file cleanup pending for deleted piece %s', piece_id)
        return False


def retry_file_deletions():
    with store.db() as conn:
        pending = conn.execute('SELECT id FROM pending_piece_deletions').fetchall()
    for row in pending:
        purge_piece_files(row['id'])


def delete_piece(piece_id):
    if piece_id == 'demo':
        raise PermissionError('The bundled demo is always available and cannot be deleted.')
    piece_directory(piece_id)
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute('SELECT 1 FROM pieces WHERE id=?', (piece_id,)).fetchone():
            raise LookupError('Piece not found')
        conn.execute('DELETE FROM revisions WHERE piece_id=?', (piece_id,))
        # Keep shared acquisition sources and job history usable by other pieces.
        conn.execute('UPDATE jobs SET piece_id=NULL WHERE piece_id=?', (piece_id,))
        conn.execute('DELETE FROM pieces WHERE id=?', (piece_id,))
        conn.execute('INSERT OR IGNORE INTO pending_piece_deletions VALUES (?)', (piece_id,))
    # A locked audio file must not resurrect a deleted library entry. Retry on startup.
    removed = purge_piece_files(piece_id)
    return {'id': piece_id, 'deleted': True, 'filesPending': not removed}
