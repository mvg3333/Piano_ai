"""Refresh old automatic video-ID names without retranscribing or changing edits."""
import json
from backend.youtube_titles import refresh_saved_titles

if __name__ == '__main__':
    print(json.dumps(refresh_saved_titles(), indent=2, ensure_ascii=True))
