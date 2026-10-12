"""Public YouTube titles, with a readable fallback when metadata is unavailable."""
import httpx
from .ingestion import parse_youtube

FALLBACK_TITLE = 'YouTube performance'


def clean_title(value):
    if not isinstance(value, str):
        return None
    return ' '.join(value.split())[:160] or None


def is_placeholder(title, video_id):
    return title in (None, '', FALLBACK_TITLE, f'YouTube · {video_id}')


def fetch_youtube_title(url):
    # Always reconstruct the video URL; requests go only to this fixed endpoint.
    canonical = parse_youtube(url)['url']
    try:
        response = httpx.get('https://www.youtube.com/oembed',
                             params={'url': canonical, 'format': 'json'},
                             timeout=5, follow_redirects=False)
        response.raise_for_status()
        metadata = response.json()
        return clean_title(metadata.get('title')) if isinstance(metadata, dict) else None
    except (httpx.HTTPError, ValueError):
        # A temporary metadata failure must not prevent audio acquisition.
        return None


def refresh_saved_titles():
    """Backfill automatic names only. Preserve user titles and all practice data."""
    import json
    from . import store
    store.setup()
    with store.db() as conn:
        sources = [json.loads(r['payload']) for r in conn.execute('SELECT payload FROM sources')]
        pieces = [json.loads(r['payload']) for r in conn.execute('SELECT payload FROM pieces')]
    videos = set()
    for source in sources + [p.get('source', {}) for p in pieces]:
        if source.get('kind') == 'youtube' and is_placeholder(source.get('title'), source.get('videoId')):
            videos.add(source['videoId'])
    for piece in pieces:
        source = piece.get('source', {})
        if source.get('kind') == 'youtube' and not piece.get('titleEdited') and is_placeholder(piece.get('title'), source.get('videoId')):
            videos.add(source['videoId'])
    titles = {video: fetch_youtube_title(f'https://www.youtube.com/watch?v={video}') for video in videos}
    renamed = []
    # Fetch before locking, then reread so a concurrent manual rename wins.
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        for row in conn.execute('SELECT id,payload FROM sources').fetchall():
            source = json.loads(row['payload'])
            title = titles.get(source.get('videoId')) if source.get('kind') == 'youtube' else None
            if title and is_placeholder(source.get('title'), source.get('videoId')):
                source['title'] = title
                conn.execute('UPDATE sources SET payload=? WHERE id=?', (json.dumps(source), row['id']))
        for row in conn.execute('SELECT id,payload FROM pieces').fetchall():
            piece = json.loads(row['payload'])
            source = piece.get('source', {})
            title = titles.get(source.get('videoId')) if source.get('kind') == 'youtube' else None
            if not title:
                continue
            changed = False
            if is_placeholder(source.get('title'), source.get('videoId')):
                source['title'] = title
                changed = True
            if not piece.get('titleEdited') and is_placeholder(piece.get('title'), source.get('videoId')):
                piece['title'] = title
                changed = True
                renamed.append({'id': row['id'], 'title': title})
            if changed:
                conn.execute('UPDATE pieces SET title=?,payload=? WHERE id=?',
                             (piece['title'], json.dumps(piece), row['id']))
    return {'renamed': renamed, 'unavailable': [video for video, title in titles.items() if not title]}
