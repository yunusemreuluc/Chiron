"""
Tarayıcı kontrolü — Windows için webbrowser modülü ile çalışır.
"""

import re
import urllib.parse
import webbrowser

import requests

from actions.tool_result import fail, ok
from core.tool_registry import register_tool

_VIDEO_ID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')


def _open(url: str) -> None:
    webbrowser.open(url)


def _find_first_youtube_video(query: str) -> str | None:
    encoded = urllib.parse.quote_plus(query)
    response = requests.get(
        f"https://www.youtube.com/results?search_query={encoded}",
        headers={"User-Agent": "Chiron/1.0"},
        timeout=10,
    )
    response.raise_for_status()

    seen: set[str] = set()
    for video_id in _VIDEO_ID_RE.findall(response.text):
        if video_id not in seen:
            seen.add(video_id)
            return video_id
    return None


@register_tool("browser_control")
def browser_control(action: str, url: str = None, query: str = None) -> dict:
    if action == "open_url":
        if not url:
            return fail("URL belirtilmedi.")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        _open(url)
        return ok(f"Açıldı: {url}", url=url)

    elif action == "search":
        if not query:
            return fail("Arama sorgusu belirtilmedi.")
        encoded = urllib.parse.quote(query)
        search_url = f"https://www.google.com/search?q={encoded}"
        _open(search_url)
        return ok(f"'{query}' için arama açıldı.", query=query)

    elif action in ("play_youtube", "youtube_play", "play_music"):
        if not query:
            return fail("YouTube için arama sorgusu belirtilmedi.")

        try:
            video_id = _find_first_youtube_video(query)
        except Exception as exc:
            encoded = urllib.parse.quote(query)
            fallback_url = f"https://www.youtube.com/results?search_query={encoded}"
            _open(fallback_url)
            return ok(
                f"YouTube ilk sonucu alınamadı ({exc}). "
                f"Arama sonuçları açıldı: {query}",
                query=query, fallback=True,
            )

        if not video_id:
            encoded = urllib.parse.quote(query)
            fallback_url = f"https://www.youtube.com/results?search_query={encoded}"
            _open(fallback_url)
            return ok(f"YouTube'da doğrudan video bulunamadı. Arama sonuçları açıldı: {query}", query=query, fallback=True)

        watch_url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
        _open(watch_url)
        return ok(f"YouTube'da oynatılıyor: {query}", query=query, video_id=video_id)

    return fail(f"Bilinmeyen eylem: {action}")
