import sys
from pathlib import Path
from schema_extractor import extract_or_load_schema, count_schema_videos, validate_video_count
from video_identifier import VideoInfo
from matcher import match_pure_video_mode
from audio_identifier import extract_audio_clip

# 1. Test schema counting & validation
course_dir = Path("..") / "1. Working With the Open AI API"
schema = extract_or_load_schema(course_dir)
total_vids = count_schema_videos(schema)
print(f"Schema total videos: {total_vids}")
assert total_vids == 10, f"Expected 10, got {total_vids}"
assert validate_video_count(schema, 10) is True
assert validate_video_count(schema, 9) is False
print("[PASS] Schema counting & global count constraint validation")

# 2. Test audio clip extraction via ffmpeg
test_video = course_dir / "Chapter 1 - Introduction to the OpenAI API" / "01 - What is the OpenAI API.mp4"
if test_video.exists():
    clip = extract_audio_clip(test_video, duration_secs=5.0)
    print(f"Audio clip extracted: {clip}, size: {clip.stat().st_size if clip else 0} bytes")
    assert clip and clip.exists() and clip.stat().st_size > 0
    print("[PASS] ffmpeg audio clip extraction (16kHz mono WAV)")

# 3. Test match_pure_video_mode with shuffled/synthetic videos (out of order, zero ordinal bias)
mock_videos = [
    VideoInfo(file_path=Path("vid_z.mp4"), file_name="vid_z.mp4", duration_seconds=85.0, ocr_title="Congratulations!"),
    VideoInfo(file_path=Path("vid_a.mp4"), file_name="vid_a.mp4", duration_seconds=210.0, ocr_title="What is the OpenAI API?"),
    VideoInfo(file_path=Path("vid_b.mp4"), file_name="vid_b.mp4", duration_seconds=180.0, ocr_title="NO_TITLE_CARD", audio_title="Applications built on the OpenAI API"),
    VideoInfo(file_path=Path("vid_c.mp4"), file_name="vid_c.mp4", duration_seconds=190.0, ocr_title="Making requests to the OpenAI API"),
    VideoInfo(file_path=Path("vid_d.mp4"), file_name="vid_d.mp4", duration_seconds=200.0, ocr_title="Summarizing and editing text"),
    VideoInfo(file_path=Path("vid_e.mp4"), file_name="vid_e.mp4", duration_seconds=195.0, ocr_title="Text generation"),
    VideoInfo(file_path=Path("vid_f.mp4"), file_name="vid_f.mp4", duration_seconds=220.0, ocr_title="Shot prompting"),
    VideoInfo(file_path=Path("vid_g.mp4"), file_name="vid_g.mp4", duration_seconds=175.0, ocr_title="Chat roles and system messages"),
    VideoInfo(file_path=Path("vid_h.mp4"), file_name="vid_h.mp4", duration_seconds=185.0, ocr_title="Utilizing the assistant role"),
    VideoInfo(file_path=Path("vid_i.mp4"), file_name="vid_i.mp4", duration_seconds=190.0, ocr_title="Multi-turn conversations with GPT"),
]

matches = match_pure_video_mode(schema, mock_videos)
print(f"\nTotal matches: {len(matches)}")
for m in matches:
    print(f"  Ch{m.chapter_number} ex={m.ex:02d} [{m.lesson_title}] -> {m.video_path.name if m.video_path else None} (conf={m.confidence:.2f}, signals={m.signals})")

# Assertions
assert matches[0].video_path.name == "vid_a.mp4", f"First video mismatch: {matches[0].video_path}"
assert matches[1].video_path.name == "vid_b.mp4", f"Audio fallback mismatch: {matches[1].video_path}"
assert any("audio_fallback_match" in s for s in matches[1].signals), f"Expected audio fallback signal: {matches[1].signals}"
assert matches[-1].video_path.name == "vid_z.mp4", f"Congratulations mismatch: {matches[-1].video_path}"

# Check zero ordinal signals
for m in matches:
    for s in m.signals:
        assert "ordinal" not in s.lower(), f"Found forbidden ordinal signal: {s}"
        assert "st_mtime" not in s.lower(), f"Found forbidden mtime signal: {s}"

print("\n[PASS] Bipartite assignment matches correctly with zero ordinal/chronological bias!")
print("\nALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
