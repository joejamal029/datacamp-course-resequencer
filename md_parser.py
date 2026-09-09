import re
from pathlib import Path
from dataclasses import dataclass
from utils import parse_time_str

@dataclass
class MdLessonInfo:
    file_path: Path
    file_name: str
    course_slug: str
    chapter_slug: str
    ex: int
    duration_seconds: float
    clean_title: str
    raw_title: str

def parse_md_file(md_path: Path | str) -> MdLessonInfo | None:
    path = Path(md_path)
    if not path.is_file():
        return None

    try:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as e:
        print(f"Warning: Could not read {path}: {e}")
        return None

    # Parse footer URL: campus.datacamp.com/courses/{course_slug}/{chapter_slug}?ex={ex_num}
    url_match = re.search(
        r'campus\.datacamp\.com/courses/([^/]+)/([^?]+)\?ex=(\d+)',
        content
    )
    if not url_match:
        # Some transcripts might have slight URL variations
        url_match = re.search(
            r'campus\.datacamp\.com/courses/([^/\s\)]+)/([^?\s\)]+)\?ex=(\d+)',
            content
        )

    course_slug = url_match.group(1) if url_match else ""
    chapter_slug = url_match.group(2) if url_match else ""
    ex_num = int(url_match.group(3)) if url_match else -1

    # Extract timestamps e.g. "00:00 - 00:16" to find total duration
    timestamps = re.findall(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})', content)
    duration = 0.0
    if timestamps:
        start_sec = parse_time_str(timestamps[0][0])
        end_sec = parse_time_str(timestamps[-1][1])
        duration = max(0.0, end_sec - start_sec)

    # Clean the filename to produce a candidate title:
    # e.g., "Multi-step prompting _ OpenAI.md" -> "Multi-step prompting"
    raw_stem = path.stem
    # Strip any trailing ' _ <Something>'
    clean_stem = re.sub(r'\s*_\s*[^_]+$', '', raw_stem)
    # If no trailing pattern matched, strip common extensions or trailing underscores
    clean_stem = clean_stem.replace("_", " ").strip()

    return MdLessonInfo(
        file_path=path,
        file_name=path.name,
        course_slug=course_slug,
        chapter_slug=chapter_slug,
        ex=ex_num,
        duration_seconds=duration,
        clean_title=clean_stem,
        raw_title=raw_stem
    )

def parse_all_mds_in_course(course_dir: Path | str) -> list[MdLessonInfo]:
    c_dir = Path(course_dir)
    md_files = sorted(c_dir.glob("*.md"))
    results = []
    for md_file in md_files:
        info = parse_md_file(md_file)
        if info:
            results.append(info)
    return results

if __name__ == "__main__":
    import sys
    test_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    parsed = parse_all_mds_in_course(test_dir)
    print(f"Parsed {len(parsed)} markdown files from {test_dir}:")
    for p in parsed:
        print(f"  [{p.chapter_slug}] ex={p.ex:02d} | dur={p.duration_seconds:05.1f}s | title='{p.clean_title}' ({p.file_name})")
