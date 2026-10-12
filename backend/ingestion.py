import json
import re
import subprocess
from urllib.parse import urlparse, parse_qs
from .config import FFPROBE, FFMPEG, MAX_SECONDS

ALLOWED_EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.mp4', '.webm'}

def parse_youtube(url):
    parsed = urlparse(url.strip())
    if parsed.scheme not in ('https', 'http') or parsed.username or parsed.password or parsed.port:
        raise ValueError('Use a normal https://youtube.com/watch or https://youtu.be link.')
    host = (parsed.hostname or '').lower()
    query = parse_qs(parsed.query)
    if host in ('youtube.com', 'www.youtube.com', 'm.youtube.com') and parsed.path == '/watch':
        video = query.get('v', [''])[0]
    elif host == 'youtu.be':
        video = parsed.path.strip('/')
    else:
        raise ValueError('Only YouTube watch and youtu.be video links are supported.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
        raise ValueError('The YouTube video ID is invalid.')
    stamp = query.get('t', query.get('start', parse_qs(parsed.fragment).get('t', ['0'])))[0]
    if stamp.isdigit():
        seconds = int(stamp)
    elif re.fullmatch(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', stamp) and stamp:
        h, m, s = re.fullmatch(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', stamp).groups()
        seconds = int(h or 0)*3600+int(m or 0)*60+int(s or 0)
    else:
        raise ValueError('The YouTube timestamp is invalid.')
    return {'videoId': video, 'url': f'https://www.youtube.com/watch?v={video}', 'suggestedStart': seconds}

def probe(path):
    try:
        result = subprocess.run([FFPROBE, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_format', '-show_streams', '-of', 'json', str(path)],
                                capture_output=True, text=True, timeout=30, check=True)
        info = json.loads(result.stdout)
        duration = float(info.get('format', {}).get('duration', 0))
    except FileNotFoundError as exc:
        raise ValueError('ffprobe is missing. Configure PIANO_FFPROBE or install FFmpeg.') from exc
    except (subprocess.SubprocessError, ValueError, KeyError) as exc:
        raise ValueError('This file could not be decoded as audio/video.') from exc
    if not any(s['codec_type'] == 'audio' for s in info.get('streams', [])):
        raise ValueError('The file has no audio track.')
    if not 0 < duration <= MAX_SECONDS:
        raise ValueError(f'Audio duration must be between 0 and {MAX_SECONDS/60:g} minutes.')
    return duration

def decode_clip(path, output, start, end):
    command = [FFMPEG, '-nostdin', '-v', 'error', '-y', '-protocol_whitelist', 'file,pipe', '-ss', str(start), '-i', str(path), '-t', str(end-start),
               '-vn', '-ac', '1', '-ar', '22050', '-c:a', 'pcm_s16le', str(output)]
    try:
        subprocess.run(command, capture_output=True, timeout=600, check=True)
    except FileNotFoundError as exc:
        raise ValueError('FFmpeg is missing. Configure PIANO_FFMPEG or install FFmpeg.') from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(f'FFmpeg decoding failed: {exc.stderr.decode(errors="replace")[-1000:]}') from exc
