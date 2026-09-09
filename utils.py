import re
import hashlib
from pathlib import Path
import cv2
import numpy as np

def slugify(text: str) -> str:
    """Convert a title to a URL-friendly slug matching DataCamp's slug format."""
    text = text.lower().strip()
    # Replace & with and
    text = text.replace("&", "and")
    # Replace non-alphanumeric characters (except spaces and hyphens) with nothing
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    # Replace spaces and underscores with a single hyphen
    text = re.sub(r'[\s_]+', '-', text)
    # Remove multiple consecutive hyphens
    text = re.sub(r'-+', '-', text)
    return text.strip('-')

def get_file_hash(file_path: Path | str) -> str:
    """Compute the full MD5 hash of a file for integrity verification."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def get_video_fingerprint(file_path: Path | str) -> str:
    """Quick fingerprint using file size and first 2MB for caching video operations."""
    p = Path(file_path)
    size = p.stat().st_size
    hasher = hashlib.md5()
    hasher.update(str(size).encode("utf-8"))
    with open(p, "rb") as f:
        chunk = f.read(2 * 1024 * 1024)
        hasher.update(chunk)
    return hasher.hexdigest()

def calculate_image_sharpness(image_path: Path | str) -> float:
    """Calculate the Laplacian variance of an image as a measure of sharpness.
    Returns -1.0 if image is invalid or nearly black (fade transition).
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return -1.0
    mean_val = np.mean(img)
    # If the frame is too dark or pure black (e.g. during a fade), discard
    if mean_val < 30:
        return -1.0
    return float(cv2.Laplacian(img, cv2.CV_64F).var())

def parse_time_str(ts_str: str) -> float:
    """Parse time string like '01:23' or '01:23:45' into seconds."""
    parts = ts_str.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return 0.0

def extract_video_index(filename: str) -> int:
    """Extract numeric index from video filenames for sorting:
    - video.mp4 -> 0
    - video (1).mp4 -> 1
    - video (10).mp4 -> 10
    """
    stem = Path(filename).stem
    m = re.search(r'\((\d+)\)', stem)
    if m:
        return int(m.group(1))
    if stem.lower() == "video":
        return 0
    return 999999
