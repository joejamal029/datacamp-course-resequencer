import json
import time
import subprocess
from pathlib import Path
from dataclasses import dataclass
from PIL import Image

import config
from utils import get_video_fingerprint, calculate_image_sharpness
from audio_identifier import get_audio_title_for_video

@dataclass
class VideoInfo:
    file_path: Path
    file_name: str
    duration_seconds: float
    ocr_title: str
    audio_title: str = ""
    frame_path: str = ""
    fingerprint: str = ""

    @property
    def best_title(self) -> str:
        """Return the strongest title signal available (OCR first, then Audio)."""
        if self.ocr_title and self.ocr_title != "NO_TITLE_CARD":
            return self.ocr_title
        if self.audio_title and self.audio_title != "UNKNOWN":
            return self.audio_title
        return ""

_CACHE_FILE = config.CACHE_DIR / "video_cache.json"

def _load_cache() -> dict:
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_cache(cache: dict):
    with open(_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

def get_video_duration(video_path: Path | str) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(video_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        data = json.loads(res.stdout)
        return float(data.get("format", {}).get("duration", 0.0))
    return 0.0

def extract_best_title_frame(video_path: Path, output_dir: Path) -> Path | None:
    timestamps = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    best_frame = None
    best_score = -1.0

    stem = video_path.stem
    for ts in timestamps:
        out_frame = output_dir / f"{stem}_t{ts:.1f}.jpg"
        cmd = [
            "ffmpeg", "-ss", str(ts),
            "-i", str(video_path),
            "-frames:v", "1",
            "-update", "1",
            "-q:v", "2",
            str(out_frame),
            "-y"
        ]
        subprocess.run(cmd, capture_output=True)
        if out_frame.exists():
            score = calculate_image_sharpness(out_frame)
            if score > best_score:
                best_score = score
                best_frame = out_frame

    return best_frame

def _call_gemini_ocr(image_path: Path, api_key: str) -> str:
    from google import genai
    prompt = """Look at this video title card from a DataCamp lesson.
Extract ONLY the lesson title text (e.g. "What is the OpenAI API?", "Congratulations!", "Text generation").
DO NOT extract the course name subtitle (e.g. "WORKING WITH THE OPENAI API" or "PROMPT ENGINEERING").
Return ONLY the clean lesson title string without quotes or explanations.
If no title card is visible, return "NO_TITLE_CARD"."""
    client = genai.Client(api_key=api_key)
    pil_img = Image.open(image_path)
    for attempt in range(5):
        try:
            resp = client.models.generate_content(
                model=config.DEFAULT_MODEL,
                contents=[pil_img, prompt]
            )
            return resp.text.strip().strip('"\'')
        except Exception as e:
            err_str = str(e).upper()
            if any(k in err_str for k in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "OVERLOADED"]):
                sleep_sec = 4 * (attempt + 1)
                print(f"Temporary OCR issue ({e.__class__.__name__}). Retrying in {sleep_sec}s...")
                time.sleep(sleep_sec)
            else:
                print(f"Notice: OCR skipped for {image_path.name}: {e}")
                return ""
    return ""

def identify_video(
    video_path: Path | str,
    course_dir: Path | str | None = None,
    enable_audio_fallback: bool = True
) -> VideoInfo:
    path = Path(video_path)
    fp = get_video_fingerprint(path)
    cache = _load_cache()

    if fp in cache and cache[fp].get("ocr_title") and "OPENAI API" not in cache[fp].get("ocr_title", "").upper():
        item = cache[fp]
        ocr = item.get("ocr_title", "")
        audio_t = item.get("audio_title", "")

        # If OCR did not find a title and audio fallback is requested but not yet performed
        if enable_audio_fallback and ocr in ("", "NO_TITLE_CARD") and not audio_t:
            try:
                api_key = config.get_gemini_api_key(course_dir or path.parent)
                audio_t = get_audio_title_for_video(path, api_key, fingerprint=fp)
                item["audio_title"] = audio_t
                _save_cache(cache)
            except Exception as e:
                print(f"Notice: Audio fallback skipped for {path.name}: {e}")

        return VideoInfo(
            file_path=path,
            file_name=path.name,
            duration_seconds=item.get("duration_seconds", 0.0),
            ocr_title=ocr,
            audio_title=audio_t,
            frame_path=item.get("frame_path", ""),
            fingerprint=fp
        )

    duration = get_video_duration(path)

    frames_dir = config.CACHE_DIR / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    best_frame = extract_best_title_frame(path, frames_dir)

    ocr_title = ""
    try:
        api_key = config.get_gemini_api_key(course_dir or path.parent)
        if best_frame and best_frame.exists():
            ocr_title = _call_gemini_ocr(best_frame, api_key)
    except Exception as e:
        print(f"Notice: OCR skipped for {path.name}: {e}")
        ocr_title = ""

    audio_title = ""
    if enable_audio_fallback and ocr_title in ("", "NO_TITLE_CARD"):
        try:
            api_key = config.get_gemini_api_key(course_dir or path.parent)
            audio_title = get_audio_title_for_video(path, api_key, fingerprint=fp)
        except Exception as e:
            print(f"Notice: Audio fallback skipped for {path.name}: {e}")

    frame_str = str(best_frame) if best_frame else ""
    info = VideoInfo(
        file_path=path,
        file_name=path.name,
        duration_seconds=duration,
        ocr_title=ocr_title,
        audio_title=audio_title,
        frame_path=frame_str,
        fingerprint=fp
    )

    cache[fp] = {
        "file_name": path.name,
        "duration_seconds": duration,
        "ocr_title": ocr_title,
        "audio_title": audio_title,
        "frame_path": frame_str
    }
    _save_cache(cache)
    return info

def identify_all_videos(course_dir: Path | str, enable_audio_fallback: bool = True) -> list[VideoInfo]:
    c_dir = Path(course_dir)
    videos = sorted(c_dir.glob("*.mp4"))
    results = []
    for vid in videos:
        results.append(identify_video(vid, course_dir=c_dir, enable_audio_fallback=enable_audio_fallback))
    return results

