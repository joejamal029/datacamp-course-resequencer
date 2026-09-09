import json
import re
import shutil
from pathlib import Path
from matcher import MatchResult
from utils import get_file_hash

BACKUP_MANIFEST_NAME = "backup_manifest.json"
MOVE_PLAN_NAME = "move_plan.json"

def sanitize_filename(title: str) -> str:
    """Sanitize title for Windows filesystem while keeping readability."""
    cleaned = title.replace(":", " -")
    cleaned = re.sub(r'[\\/*?"<>|]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def generate_move_plan(
    course_dir: Path | str,
    matches: list[MatchResult]
) -> list[dict]:
    """Build the complete move-plan manifest for dry-run and execution."""
    course_path = Path(course_dir)
    plan = []

    for m in matches:
        chap_dir_name = f"Chapter {m.chapter_number} - {sanitize_filename(m.chapter_title)}"
        clean_title = sanitize_filename(m.lesson_title)
        base_name = f"{m.ex:02d} - {clean_title}"

        target_dir = course_path / chap_dir_name

        # Plan for video file
        if m.video_path and m.video_path.exists():
            dest_video = target_dir / f"{base_name}{m.video_path.suffix}"
            plan.append({
                "type": "video",
                "source": str(m.video_path.resolve()),
                "destination": str(dest_video.resolve()),
                "relative_dest": f"{chap_dir_name}/{dest_video.name}",
                "confidence": m.confidence,
                "signals": m.signals,
                "needs_review": m.needs_review,
                "review_reason": m.review_reason,
                "status": "pending"
            })

        # Plan for md file
        if m.md_path and m.md_path.exists():
            dest_md = target_dir / f"{base_name}{m.md_path.suffix}"
            plan.append({
                "type": "transcript",
                "source": str(m.md_path.resolve()),
                "destination": str(dest_md.resolve()),
                "relative_dest": f"{chap_dir_name}/{dest_md.name}",
                "confidence": 1.0,
                "signals": ["md_url_deterministic"],
                "needs_review": False,
                "review_reason": "",
                "status": "pending"
            })

    return plan

def execute_move_plan(
    course_dir: Path | str,
    plan: list[dict],
    execute: bool = False
) -> dict:
    """Execute or dry-run the move plan with backup tracking and rollback capabilities."""
    course_path = Path(course_dir)
    manifest_file = course_path / MOVE_PLAN_NAME
    backup_file = course_path / BACKUP_MANIFEST_NAME
    review_dir = course_path / "_review_queue"

    stats = {
        "total_planned": len(plan),
        "moved": 0,
        "already_organized": 0,
        "sent_to_review": 0,
        "errors": 0
    }

    review_items = []
    backup_entries = []

    # Load existing backup manifest if present
    if backup_file.exists():
        try:
            with open(backup_file, "r", encoding="utf-8-sig") as f:
                backup_entries = json.load(f)
        except Exception:
            backup_entries = []

    for item in plan:
        src = Path(item["source"])
        dst = Path(item["destination"])

        if dst.exists() and not src.exists():
            item["status"] = "already_organized"
            stats["already_organized"] += 1
            continue

        if not src.exists():
            item["status"] = "source_not_found"
            stats["errors"] += 1
            continue

        # In "remove guardrails" mode, we proceed with the best candidate move
        # but record any review flag in the manifest for auditability
        if execute:
            try:
                src_hash = get_file_hash(src)
                item["source_hash"] = src_hash

                if dst.exists():
                    dst_hash = get_file_hash(dst)
                    if src_hash == dst_hash:
                        item["status"] = "already_organized_identical"
                        stats["already_organized"] += 1
                        continue
                    else:
                        print(f"Warning: Destination {dst.name} exists with different hash! Skipping to avoid overwrite.")
                        item["status"] = "destination_conflict"
                        stats["errors"] += 1
                        continue

                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                item["status"] = "moved"
                stats["moved"] += 1

                # Record backup restoration record
                backup_entries.append({
                    "original_path": str(src.resolve()),
                    "current_path": str(dst.resolve()),
                    "original_name": src.name,
                    "file_hash": src_hash
                })
            except Exception as e:
                print(f"Error moving {src.name} -> {dst.name}: {e}")
                item["status"] = f"error: {str(e)}"
                stats["errors"] += 1
        else:
            item["status"] = "dry_run"

    # Save backup manifest if files were moved
    if execute and backup_entries:
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_entries, f, indent=2)

    # Save move plan manifest
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    return stats

def restore_from_backup(course_dir: Path | str) -> dict:
    """Restore all moved files back to their original names and locations."""
    course_path = Path(course_dir)
    backup_file = course_path / BACKUP_MANIFEST_NAME
    if not backup_file.exists():
        print(f"No backup manifest found at {backup_file}.")
        return {"restored": 0, "errors": 0}

    with open(backup_file, "r", encoding="utf-8-sig") as f:
        entries = json.load(f)

    stats = {"restored": 0, "errors": 0}
    affected_dirs = set()

    for entry in entries:
        orig = Path(entry["original_path"])
        curr = Path(entry["current_path"])

        if not curr.exists():
            if orig.exists():
                # Already restored
                continue
            print(f"Warning: Current file not found: {curr}")
            stats["errors"] += 1
            continue

        try:
            orig.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(curr), str(orig))
            stats["restored"] += 1
            affected_dirs.add(curr.parent)
        except Exception as e:
            print(f"Error restoring {curr} -> {orig}: {e}")
            stats["errors"] += 1

    # Remove empty chapter directories
    for d in affected_dirs:
        try:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
        except Exception:
            pass

    # Clean up manifest files
    try:
        backup_file.unlink(missing_ok=True)
        (course_path / MOVE_PLAN_NAME).unlink(missing_ok=True)
    except Exception:
        pass

    return stats
