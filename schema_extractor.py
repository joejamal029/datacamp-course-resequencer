import json
import re
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from PIL import Image

import config
from utils import slugify
from md_parser import parse_all_mds_in_course

@dataclass
class SchemaItem:
    order: int
    ex: int
    type: str  # "video" or "exercise"
    xp: int
    title: str

@dataclass
class ChapterSchema:
    chapter_number: int
    chapter_title: str
    chapter_slug: str
    items: list[SchemaItem]

@dataclass
class CourseSchema:
    course_name: str
    chapters: list[ChapterSchema]

def _call_gemini_vision(image_path: Path, prompt: str, api_key: str, model_name: str = "gemini-3.5-flash-lite") -> str:
    """Call Gemini Flash with an image with automatic retry on rate limits."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    pil_img = Image.open(image_path)
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[pil_img, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                )
            )
            return response.text
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                sleep_sec = 4 * (attempt + 1)
                print(f"Rate limit reached. Backing off for {sleep_sec}s...")
                time.sleep(sleep_sec)
            else:
                raise
    raise RuntimeError("Max retries exceeded for vision call.")

def find_best_matching_slug(chapter_title: str, known_slugs: set[str]) -> str:
    calc_slug = slugify(chapter_title)
    if calc_slug in known_slugs:
        return calc_slug
    best_slug = calc_slug
    best_score = 0.0
    for s in known_slugs:
        score = SequenceMatcher(None, calc_slug, s).ratio()
        if score > best_score:
            best_score = score
            best_slug = s
    return best_slug if best_score > 0.6 else calc_slug

def extract_chapter_from_image(image_path: Path, api_key: str, known_slugs: set[str] | None = None) -> ChapterSchema:
    prompt = """Analyze this course outline screenshot from DataCamp.
Extract the chapter structure and return ONLY a valid JSON object with this exact schema:
{
  "chapter_number": <int>,
  "chapter_title": "<exact chapter title text>",
  "items": [
    {
      "order": <int, 1-indexed position in the chapter list>,
      "ex": <int, same as order (1-indexed item number in this chapter)>,
      "type": "video" if 50 XP else "exercise",
      "xp": <50 or 100>,
      "title": "<exact item title text>"
    }
  ]
}
Do not wrap in markdown tags other than standard json code fences if needed. Output pure JSON."""

    raw_response = _call_gemini_vision(image_path, prompt, api_key, config.DEFAULT_MODEL)
    
    cleaned = re.sub(r'^```json\s*', '', raw_response.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```$', '', cleaned.strip(), flags=re.MULTILINE)
    
    data = json.loads(cleaned)
    chap_num = int(data.get("chapter_number", 1))
    chap_title = data.get("chapter_title", "").strip()
    
    if known_slugs:
        slug = find_best_matching_slug(chap_title, known_slugs)
    else:
        slug = slugify(chap_title)

    items = []
    for item in data.get("items", []):
        order = int(item.get("order", 1))
        ex = int(item.get("ex", order))
        xp = int(item.get("xp", 50))
        itype = "video" if xp == 50 else item.get("type", "exercise")
        title = item.get("title", "").strip()
        items.append(SchemaItem(order=order, ex=ex, type=itype, xp=xp, title=title))

    return ChapterSchema(
        chapter_number=chap_num,
        chapter_title=chap_title,
        chapter_slug=slug,
        items=items
    )

def extract_or_load_schema(course_dir: Path | str) -> CourseSchema:
    course_path = Path(course_dir)
    schema_file = course_path / "course_schema.json"
    
    if schema_file.exists():
        print(f"Loading existing schema from {schema_file}")
        with open(schema_file, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
        chapters = []
        for ch in raw.get("chapters", []):
            items = [SchemaItem(**it) for it in ch.get("items", [])]
            chapters.append(ChapterSchema(
                chapter_number=ch["chapter_number"],
                chapter_title=ch["chapter_title"],
                chapter_slug=ch["chapter_slug"],
                items=items
            ))
        return CourseSchema(course_name=raw.get("course_name", course_path.name), chapters=chapters)

    api_key = config.get_gemini_api_key(course_path)
    
    png_files = []
    for p in course_path.glob("*.png"):
        m = re.match(r'^(\d+)\.0\.png$', p.name)
        if m:
            png_files.append((int(m.group(1)), p))
    
    if not png_files:
        raise FileNotFoundError(f"No outline images matching 'N.0.png' found in {course_path}")
    
    png_files.sort(key=lambda x: x[0])
    
    md_lessons = parse_all_mds_in_course(course_path)
    known_slugs = {md.chapter_slug for md in md_lessons if md.chapter_slug}

    print(f"Found {len(png_files)} outline images. Extracting schema via Gemini Vision...")
    chapters = []
    for idx, (chap_num, img_path) in enumerate(png_files):
        print(f"  Analyzing {img_path.name} (Chapter {chap_num})...")
        ch_schema = extract_chapter_from_image(img_path, api_key, known_slugs)
        ch_schema.chapter_number = chap_num
        chapters.append(ch_schema)

    course_schema = CourseSchema(
        course_name=course_path.name,
        chapters=chapters
    )

    schema_dict = {
        "course_name": course_schema.course_name,
        "chapters": [
            {
                "chapter_number": ch.chapter_number,
                "chapter_title": ch.chapter_title,
                "chapter_slug": ch.chapter_slug,
                "items": [asdict(it) for it in ch.items]
            }
            for ch in course_schema.chapters
        ]
    }
    with open(schema_file, "w", encoding="utf-8") as f:
        json.dump(schema_dict, f, indent=2)
    print(f"Saved canonical schema to {schema_file}")

    return course_schema
