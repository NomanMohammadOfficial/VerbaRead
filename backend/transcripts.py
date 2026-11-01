import re

VIDEO_PATTERNS = [
    r"(?:youtube\.com/watch\?(?:.*&)?v=)([A-Za-z0-9_-]{11})",
    r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
    r"(?:youtube\.com/live/)([A-Za-z0-9_-]{11})",
]


def video_id(url: str) -> str | None:
    for pattern in VIDEO_PATTERNS:
        match = re.search(pattern, url or "")
        if match:
            return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", (url or "").strip()):
        return url.strip()
    return None


def _snips(payload):
    if hasattr(payload, "snippets"):
        items = payload.snippets
    elif hasattr(payload, "to_raw_data"):
        items = payload.to_raw_data()
    else:
        items = list(payload)
    cues = []
    for item in items:
        if isinstance(item, dict):
            start, duration, text = item.get("start"), item.get("duration"), item.get("text")
        else:
            start, duration, text = getattr(item, "start", None), getattr(item, "duration", None), getattr(item, "text", None)
        text = (text or "").replace("\n", " ").strip()
        if not text:
            continue
        start = float(start or 0)
        duration = float(duration or 0)
        cues.append({"start": round(start, 3), "duration": round(duration, 3), "text": text})
    return cues


def fetch(video: str) -> dict:
    vid = video_id(video) or video
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {"videoId": vid, "cues": [], "error": "youtube-transcript-api is not installed"}

    try:
        api = YouTubeTranscriptApi()
        last_error = "No transcript available"
        attempts = [["ru"], ["ru-RU"], ["en"], None]
        for languages in attempts:
            try:
                if hasattr(api, "fetch"):
                    kwargs = {"languages": languages} if languages else {}
                    payload = api.fetch(vid, **kwargs)
                else:
                    if languages:
                        payload = YouTubeTranscriptApi.get_transcript(vid, languages=languages)
                    else:
                        payload = YouTubeTranscriptApi.get_transcript(vid)
                cues = _snips(payload)
                if cues:
                    language = getattr(payload, "language_code", None) or (languages[0] if languages else "unknown")
                    return {"videoId": vid, "cues": cues, "language": language, "error": None}
            except Exception as exc:
                last_error = str(exc)
        return {"videoId": vid, "cues": [], "error": last_error}
    except Exception as exc:
        return {"videoId": vid, "cues": [], "error": str(exc)}
