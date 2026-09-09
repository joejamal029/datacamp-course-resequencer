import argparse
import sys
import shutil
from pathlib import Path

import config
from schema_extractor import extract_or_load_schema
from md_parser import parse_all_mds_in_course
from video_identifier import identify_all_videos
from matcher import match_course_assets
from file_ops import generate_move_plan, execute_move_plan, restore_from_backup

def check_dependencies():
    """Verify system prerequisites like ffmpeg."""
    if not shutil.which("ffmpeg"):
        print("ERROR: ffmpeg binary not found on PATH.")
        print("Please install ffmpeg (e.g. 'winget install ffmpeg') and ensure it is in your system PATH.")
        sys.exit(1)
    if not shutil.which("ffprobe"):
        print("ERROR: ffprobe binary not found on PATH.")
        print("Please ensure ffprobe is installed and on your system PATH.")
        sys.exit(1)

def print_header(title: str):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def remediate_single_course(course_dir: Path, execute: bool = False, restore: bool = False, threshold: float = config.CONFIDENCE_THRESHOLD):
    if restore:
        print_header(f"RESTORING COURSE FROM BACKUP: {course_dir.name}")
        stats = restore_from_backup(course_dir)
        print(f"Restoration Complete: {stats['restored']} files restored, {stats['errors']} errors.")
        return

    print_header(f"DATACAMP REMEDIATION PIPELINE: {course_dir.name}")
    print(f"Mode: {'EXECUTE (Modifying disk with rollback manifest)' if execute else 'DRY RUN (Simulated)'}")
    print(f"Target Directory: {course_dir}")

    # Stage 0: Schema Extraction
    print_header("Stage 0: Course Schema Extraction")
    try:
        schema = extract_or_load_schema(course_dir)
        print(f"Canonical schema loaded: {len(schema.chapters)} chapters")
        for ch in schema.chapters:
            videos_count = sum(1 for it in ch.items if it.type == "video" or it.xp == 50)
            print(f"  - Chapter {ch.chapter_number}: '{ch.chapter_title}' ({videos_count} video lessons)")
    except Exception as e:
        print(f"Failed to extract or load schema: {e}")
        return

    # Stage 1: Markdown Parsing
    print_header("Stage 1: Markdown Transcripts Normalization")
    md_lessons = parse_all_mds_in_course(course_dir)
    print(f"Found {len(md_lessons)} unorganized markdown transcripts.")

    # Stage 2: Video Identification
    print_header("Stage 2: Video Asset Fingerprinting & Title Extraction")
    videos = identify_all_videos(course_dir)
    print(f"Found {len(videos)} unorganized video files.")

    # Early exit if everything is already organized
    if len(md_lessons) == 0 and len(videos) == 0:
        print("\nAll assets in this course directory are already organized into chapter folders!")
        print("Nothing to do.")
        return

    # Stage 3: Multi-Signal Matching Engine
    print_header("Stage 3: Multi-Signal Corroboration Engine")
    matches = match_course_assets(schema, md_lessons, videos)

    # Stage 4: Generate Move Plan Manifest
    plan = generate_move_plan(course_dir, matches)
    print(f"\nGenerated move plan with {len(plan)} file operations:")
    print("-" * 80)
    for p in plan:
        src_name = Path(p["source"]).name
        conf_str = f"conf={p['confidence']:.2f}"
        print(f"  [{p['type'].upper():10s}] {src_name} -> {p['relative_dest']} ({conf_str})")
    print("-" * 80)

    # Stage 5: File Operations
    print_header("Stage 4 & 5: File Operations & Backup Manifest")
    if execute:
        print("Executing file moves with backup tracking enabled...")
        stats = execute_move_plan(course_dir, plan, execute=True)
        print("\nExecution Completed:")
        print(f"  - Total files processed: {stats['total_planned']}")
        print(f"  - Files successfully moved: {stats['moved']}")
        print(f"  - Already organized: {stats['already_organized']}")
        print(f"  - Errors encountered: {stats['errors']}")
        print(f"\nAudit manifest: {course_dir / 'move_plan.json'}")
        print(f"Backup manifest (use --restore to undo): {course_dir / 'backup_manifest.json'}")
    else:
        execute_move_plan(course_dir, plan, execute=False)
        print(f"DRY RUN COMPLETE.")
        print(f"Manifest written to: {course_dir / 'move_plan.json'}")
        print("\nTo apply these file movements to disk, run with '--execute':")
        print(f"  python remediate.py \"{str(course_dir)}\" --execute")

def main():
    parser = argparse.ArgumentParser(
        description="DataCamp Course Remediation Pipeline — Organize unorganized course assets into clean chapter folders."
    )
    parser.add_argument("target", type=str, help="Path to course folder, or root learning folder when using --batch")
    parser.add_argument("--execute", action="store_true", help="Execute file moves immediately with backup tracking")
    parser.add_argument("--restore", action="store_true", help="Restore course folder back to original state from backup")
    parser.add_argument("--batch", action="store_true", help="Process all course subdirectories under target folder")
    parser.add_argument("--threshold", type=float, default=config.CONFIDENCE_THRESHOLD, help="Confidence threshold")
    parser.add_argument("--model", type=str, default=config.DEFAULT_MODEL, help="Gemini model name")

    args = parser.parse_args()

    check_dependencies()
    target_path = Path(args.target).resolve()
    if not target_path.exists():
        print(f"ERROR: Target path does not exist: {target_path}")
        sys.exit(1)

    config.load_course_env(target_path)
    config.DEFAULT_MODEL = args.model
    config.CONFIDENCE_THRESHOLD = args.threshold

    if args.batch:
        # Find all course subdirectories
        subdirs = [p for p in target_path.iterdir() if p.is_dir() and not p.name.startswith((".", "_")) and p.name != "remediation_tool"]
        subdirs.sort(key=lambda x: x.name)
        print(f"Batch mode: found {len(subdirs)} course directories to process.")
        for d in subdirs:
            # Check if directory has outline images or mds or videos
            has_course_assets = any(d.glob("*.png")) or any(d.glob("*.mp4")) or any(d.glob("*.md"))
            if has_course_assets:
                remediate_single_course(d, execute=args.execute, restore=args.restore, threshold=args.threshold)
    else:
        remediate_single_course(target_path, execute=args.execute, restore=args.restore, threshold=args.threshold)

if __name__ == "__main__":
    main()
