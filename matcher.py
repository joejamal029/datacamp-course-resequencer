from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from schema_extractor import CourseSchema, ChapterSchema, SchemaItem
from md_parser import MdLessonInfo
from video_identifier import VideoInfo
from utils import extract_video_index
import config

@dataclass
class MatchResult:
    video_path: Path | None
    md_path: Path | None
    chapter_number: int
    chapter_title: str
    chapter_slug: str
    ex: int
    lesson_title: str
    confidence: float
    signals: list[str] = field(default_factory=list)
    needs_review: bool = False
    review_reason: str = ""

def _string_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

def _match_enhanced_mode(
    schema: CourseSchema,
    md_lessons: list[MdLessonInfo],
    videos: list[VideoInfo]
) -> list[MatchResult]:
    """Enhanced Mode: Corroborate multiple signals (MD footer URL, OCR, duration) to match assets."""
    
    # 1. Map md files to (chapter_slug, ex)
    md_by_key: dict[tuple[str, int], MdLessonInfo] = {}
    for md in md_lessons:
        key = (md.chapter_slug, md.ex)
        md_by_key[key] = md

    # 2. Map all video lessons from the schema in canonical order.
    # When markdown transcripts exist, they are ground truth for which items are video lessons.
    canonical_video_lessons: list[tuple[ChapterSchema, SchemaItem]] = []
    for chapter in sorted(schema.chapters, key=lambda c: c.chapter_number):
        for item in sorted(chapter.items, key=lambda it: it.order):
            if md_lessons:
                if (chapter.chapter_slug, item.ex) in md_by_key:
                    canonical_video_lessons.append((chapter, item))
            else:
                if item.type == "video" or item.xp == 50:
                    canonical_video_lessons.append((chapter, item))

    # 3. Sort videos chronologically and by filename index
    def video_sort_key(v: VideoInfo):
        mtime = v.file_path.stat().st_mtime if v.file_path.exists() else 0
        idx = extract_video_index(v.file_name)
        return (mtime, idx)

    sorted_videos = sorted(videos, key=video_sort_key)
    results: list[MatchResult] = []

    total_videos = len(sorted_videos)
    total_canonical = len(canonical_video_lessons)
    count_matches = (total_videos == total_canonical)

    used_video_paths = set()
    unassigned_canonical_indices = []

    for i, (chapter, item) in enumerate(canonical_video_lessons):
        md_match = md_by_key.get((chapter.chapter_slug, item.ex))
        cand_video = sorted_videos[i] if i < total_videos and count_matches else None

        signals = []
        score = 0.0

        if md_match:
            signals.append(f"md_url_exact(slug={chapter.chapter_slug}, ex={item.ex})")
            score += 0.30

        matched_video: VideoInfo | None = None
        best_ocr_video: VideoInfo | None = None
        best_ocr_score = 0.0

        # Look for OCR match first among unused videos
        for v in sorted_videos:
            if v.file_path in used_video_paths:
                continue
            if v.ocr_title and v.ocr_title != "NO_TITLE_CARD":
                sim = _string_similarity(v.ocr_title, item.title)
                if sim > best_ocr_score:
                    best_ocr_score = sim
                    best_ocr_video = v

        if best_ocr_video and best_ocr_score >= 0.70:
            matched_video = best_ocr_video
            signals.append(f"ocr_match('{matched_video.ocr_title}' ~ '{item.title}', sim={best_ocr_score:.2f})")
            score += 0.40
        elif cand_video is not None and cand_video.file_path not in used_video_paths:
            # Check duration match with candidate
            matched_video = cand_video
            signals.append(f"ordinal_align(idx={i+1}/{total_videos})")
            score += 0.35
            if cand_video.ocr_title and cand_video.ocr_title != "NO_TITLE_CARD":
                sim = _string_similarity(cand_video.ocr_title, item.title)
                if sim >= 0.60:
                    signals.append(f"ocr_fuzzy_corroboration('{cand_video.ocr_title}', sim={sim:.2f})")
                    score += 0.30

        # Duration cross-check
        if matched_video and md_match and matched_video.duration_seconds > 0 and md_match.duration_seconds > 0:
            diff = abs(matched_video.duration_seconds - md_match.duration_seconds)
            if diff <= 5.0:
                signals.append(f"duration_exact_match(diff={diff:.1f}s)")
                score += 0.35
            elif diff <= config.DURATION_TOLERANCE_SECONDS:
                signals.append(f"duration_close_match(diff={diff:.1f}s)")
                score += 0.25
            else:
                signals.append(f"duration_divergence(diff={diff:.1f}s)")
                score -= 0.15

        if md_match and _string_similarity(md_match.clean_title, item.title) >= 0.80:
            signals.append(f"md_title_match('{md_match.clean_title}')")
            score += 0.15

        if matched_video:
            used_video_paths.add(matched_video.file_path)
        else:
            unassigned_canonical_indices.append(i)

        final_confidence = min(1.0, max(0.0, score))
        needs_review = (final_confidence < config.CONFIDENCE_THRESHOLD)
        reason = f"Confidence {final_confidence:.2f} below threshold" if needs_review else ""

        results.append(MatchResult(
            video_path=matched_video.file_path if matched_video else None,
            md_path=md_match.file_path if md_match else None,
            chapter_number=chapter.chapter_number,
            chapter_title=chapter.chapter_title,
            chapter_slug=chapter.chapter_slug,
            ex=item.ex,
            lesson_title=item.title,
            confidence=final_confidence,
            signals=signals,
            needs_review=needs_review,
            review_reason=reason
        ))

    # Second pass: If any videos remain unused and lessons unassigned, match them
    unused_videos = [v for v in sorted_videos if v.file_path not in used_video_paths]
    for idx in unassigned_canonical_indices:
        if not unused_videos:
            break
        # Pick best unused video by duration match
        chapter, item = canonical_video_lessons[idx]
        md_match = md_by_key.get((chapter.chapter_slug, item.ex))
        best_v = unused_videos[0]
        if md_match and md_match.duration_seconds > 0:
            best_diff = 999999.0
            for v in unused_videos:
                d = abs(v.duration_seconds - md_match.duration_seconds)
                if d < best_diff:
                    best_diff = d
                    best_v = v
        unused_videos.remove(best_v)
        results[idx].video_path = best_v.file_path
        results[idx].signals.append(f"duration_fallback_pairing(dur={best_v.duration_seconds:.1f}s)")
        results[idx].confidence = max(results[idx].confidence, 0.75)
        results[idx].needs_review = False

    return results

def match_pure_video_mode(
    schema: CourseSchema,
    videos: list[VideoInfo]
) -> list[MatchResult]:
    """Pure Video Mode: Bipartite assignment using content-derived signals only.

    Zero chronological bias. Zero ordinal alignment. Zero filename index sorting.
    Signals used:
      1. OCR Title Card similarity
      2. Audio Speech transcription fallback similarity
      3. Congratulations wrap-up anchor (final schema slot + short duration)
    """
    # 1. Canonical video lessons from schema
    canonical_video_lessons: list[tuple[ChapterSchema, SchemaItem]] = []
    for chapter in sorted(schema.chapters, key=lambda c: c.chapter_number):
        for item in sorted(chapter.items, key=lambda it: it.order):
            if item.type == "video" or item.xp == 50:
                canonical_video_lessons.append((chapter, item))

    N = len(canonical_video_lessons)
    M = len(videos)

    # 2. Build candidate match list for (canonical_idx, video_idx)
    candidates = []
    for i, (ch, item) in enumerate(canonical_video_lessons):
        for j, vid in enumerate(videos):
            ocr_sim = _string_similarity(vid.ocr_title, item.title) if vid.ocr_title and vid.ocr_title != "NO_TITLE_CARD" else 0.0
            audio_sim = _string_similarity(vid.audio_title, item.title) if vid.audio_title and vid.audio_title != "UNKNOWN" else 0.0

            if ocr_sim >= config.TITLE_MATCH_THRESHOLD:
                candidates.append((ocr_sim, "ocr", ocr_sim, i, j))
            elif audio_sim >= config.TITLE_MATCH_THRESHOLD:
                weighted_score = audio_sim * 0.95
                candidates.append((weighted_score, "audio", audio_sim, i, j))

    # Sort candidates descending by score
    candidates.sort(key=lambda x: -x[0])

    assigned_c: dict[int, tuple[int, str, float]] = {}  # c_idx -> (v_idx, sig_type, sim)
    used_v: set[int] = set()

    for score, sig_type, sim, c_idx, v_idx in candidates:
        if c_idx in assigned_c or v_idx in used_v:
            continue
        assigned_c[c_idx] = (v_idx, sig_type, sim)
        used_v.add(v_idx)

    # 3. Congratulations Anchor Lock
    congrats_c_idx = None
    for i, (ch, item) in enumerate(canonical_video_lessons):
        if "congratulat" in item.title.lower():
            congrats_c_idx = i

    if congrats_c_idx is not None:
        congrats_already_matched = False
        if congrats_c_idx in assigned_c:
            v_idx, sig, sim = assigned_c[congrats_c_idx]
            v = videos[v_idx]
            if "congratulat" in v.best_title.lower():
                congrats_already_matched = True

        if not congrats_already_matched:
            unused_v_indices = [j for j in range(M) if j not in used_v]
            shortest_unused = None
            if unused_v_indices:
                shortest_unused = min(unused_v_indices, key=lambda j: videos[j].duration_seconds)

            if shortest_unused is not None and videos[shortest_unused].duration_seconds < config.CONGRATS_MAX_DURATION:
                if congrats_c_idx in assigned_c:
                    old_v, _, _ = assigned_c[congrats_c_idx]
                    used_v.discard(old_v)
                assigned_c[congrats_c_idx] = (shortest_unused, "congrats_anchor", 1.0)
                used_v.add(shortest_unused)

    # 4. Fill any remaining unassigned canonical slots with remaining unused videos
    unassigned_c_indices = [i for i in range(N) if i not in assigned_c]
    remaining_v_indices = [j for j in range(M) if j not in used_v]

    for c_idx in unassigned_c_indices:
        if not remaining_v_indices:
            break
        v_idx = remaining_v_indices.pop(0)
        used_v.add(v_idx)
        assigned_c[c_idx] = (v_idx, "unmatched_fallback", 0.0)

    # 5. Build MatchResults
    results: list[MatchResult] = []
    for i, (chapter, item) in enumerate(canonical_video_lessons):
        if i in assigned_c:
            v_idx, sig_type, sim = assigned_c[i]
            matched_video = videos[v_idx]
            signals = []

            if sig_type == "ocr":
                signals.append(f"ocr_match('{matched_video.ocr_title}' ~ '{item.title}', sim={sim:.2f})")
                confidence = min(1.0, 0.50 + sim * 0.50)
                needs_review = confidence < config.CONFIDENCE_THRESHOLD
            elif sig_type == "audio":
                signals.append(f"audio_fallback_match('{matched_video.audio_title}' ~ '{item.title}', sim={sim:.2f})")
                confidence = min(0.95, 0.40 + sim * 0.50)
                needs_review = confidence < config.CONFIDENCE_THRESHOLD
            elif sig_type == "congrats_anchor":
                signals.append(f"congratulations_anchor_lock(dur={matched_video.duration_seconds:.1f}s)")
                confidence = 0.95
                needs_review = False
            else:
                signals.append("bipartite_residual_fallback")
                confidence = 0.40
                needs_review = True

            reason = f"Confidence {confidence:.2f} below threshold ({config.CONFIDENCE_THRESHOLD})" if needs_review else ""
            results.append(MatchResult(
                video_path=matched_video.file_path,
                md_path=None,
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.chapter_title,
                chapter_slug=chapter.chapter_slug,
                ex=item.ex,
                lesson_title=item.title,
                confidence=confidence,
                signals=signals,
                needs_review=needs_review,
                review_reason=reason
            ))
        else:
            results.append(MatchResult(
                video_path=None,
                md_path=None,
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.chapter_title,
                chapter_slug=chapter.chapter_slug,
                ex=item.ex,
                lesson_title=item.title,
                confidence=0.0,
                signals=["no_video_available"],
                needs_review=True,
                review_reason="No video found to assign to this lesson"
            ))

    return results

def match_course_assets(
    schema: CourseSchema,
    md_lessons: list[MdLessonInfo],
    videos: list[VideoInfo]
) -> list[MatchResult]:
    """Corroborate signals to match course assets.
    Dispatches to Enhanced Mode if MD transcripts are present,
    or Pure Video Mode (zero ordinal bias) if MD transcripts are absent.
    """
    if md_lessons:
        return _match_enhanced_mode(schema, md_lessons, videos)
    else:
        return match_pure_video_mode(schema, videos)
