import json
import time
import subprocess
from pathlib import Path
from google import genai
from google.genai import types

import config
from utils import get_video_fingerprint

_AUDIO_DIR = config.CACHE_DIR / "audio"
_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

def _load_audio_cache() -> dict:
    if config.AUDIO_CACHE_FILE.exists():
        try:
            with open(config.AUDIO_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_audio_cache(cache: dict):
    with open(config.AUDIO_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

def extract_audio_clip(video_path: Path | str, duration_secs: float = config.AUDIO_CLIP_DURATION) -> Path | None:
    """Extract first N seconds of audio as 16kHz mono WAV using ffmpeg."""
    vpath = Path(video_path)
    output = _AUDIO_DIR / f"{vpath.stem}_clip.wav"
    cmd = [
        "ffmpeg", "-y",
        "-ss", "0",
        "-i", str(vpath),
        "-t", str(duration_secs),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output)
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode == 0 and output.exists() and output.stat().st_size > 0:
        return output
    return None

def transcribe_and_extract_title(audio_path: Path, api_key: str) -> str:
    """Transcribe opening audio clip via Gemini to extract lesson topic."""
    prompt = """Listen to the first 15 seconds of this DataCamp video lesson audio.
The instructor typically announces the lesson topic in the opening sentence.

Extract ONLY the lesson topic or title as a short phrase (2-6 words).
Examples: "What is the OpenAI API?", "Text generation", "Shot prompting", "Chat roles and system messages".
If this is a wrap-up or course completion video, return "Congratulations!".
If you cannot determine the topic, return "UNKNOWN".

Return ONLY the clean topic string without quotes or explanations."""

    client = genai.Client(api_key=api_key)
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")

    for attempt in range(5):
        try:
            resp = client.models.generate_content(
                model=config.DEFAULT_MODEL,
                contents=[audio_part, prompt]
            )
            title = resp.text.strip().strip('"\'')
            return title
        except Exception as e:
            err_str = str(e).upper()
            if any(k in err_str for k in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "OVERLOADED"]):
                sleep_sec = 4 * (attempt + 1)
                print(f"Temporary audio transcription issue ({e.__class__.__name__}). Retrying in {sleep_sec}s...")
                time.sleep(sleep_sec)
            else:
                print(f"Notice: Audio transcription skipped for {audio_path.name}: {e}")
                return "UNKNOWN"
    return "UNKNOWN"

def get_audio_title_for_video(video_path: Path | str, api_key: str, fingerprint: str | None = None) -> str:
    """Get lesson title from audio, using cache if available."""
    vpath = Path(video_path)
    fp = fingerprint or get_video_fingerprint(vpath)
    cache = _load_audio_cache()

    if fp in cache and cache[fp].get("audio_title"):
        return cache[fp]["audio_title"]

    clip_path = extract_audio_clip(vpath)
    if not clip_path:
        return ""

    title = transcribe_and_extract_title(clip_path, api_key)
    cache[fp] = {
        "file_name": vpath.name,
        "audio_title": title,
        "clip_path": str(clip_path)
    }
    _save_audio_cache(cache)
    return title
