---
name: datacamp-course-remediation
description: |
  Ingests, classifies, and organizes raw, unorganized DataCamp course exports
  (unnamed MP4 videos, markdown transcripts with noisy titles, and chapter outline
  screenshots) into structured, numbered chapter and lesson folders.
  Includes automated schema extraction via Gemini Vision, OCR title card matching,
  duration cross-checking, deterministic URL lesson mapping, and full backup/restore rollback capabilities.

  Use this skill when:
    1. Organizing raw DataCamp course folders into chapter folders.
    2. Parsing DataCamp outline screenshots into canonical JSON course schemas.
    3. Matching unnamed DataCamp video files (video.mp4, video (10).mp4) to lesson transcripts.
    4. Restoring an organized course folder back to its original raw state using backup manifests.
---

# DataCamp Course Remediation Skill

## Overview

DataCamp course downloads often export as flat, unorganized folders containing:
1. Generic videos: `video.mp4`, `video (10).mp4` ...
2. Markdown transcripts with noisy suffixes: `Multi-step prompting _ OpenAI.md`
3. Outline screenshots: `1.0.png`, `2.0.png` ...

This skill provides an automated, multi-signal remediation tool located in `remediation_tool/`.

---

## Tool CLI Commands

All commands are executed with the tool's CLI:
```bash
python remediation_tool/remediate.py <TARGET> [OPTIONS]
```

### 1. Dry Run (Preview & Plan)
Simulates reorganization, extracts schemas if missing, and creates `move_plan.json` without modifying disk:
```bash
python remediation_tool/remediate.py "path/to/course_folder"
```

### 2. Execute Organization
Applies file moves with automatic backup manifest creation (`backup_manifest.json`):
```bash
python remediation_tool/remediate.py "path/to/course_folder" --execute
```

### 3. Pure Video Mode (No Transcripts)
When markdown transcripts are unavailable (common when assets are downloaded without web scrapes), run with `--mode pure_video`:
```bash
python remediation_tool/remediate.py "path/to/course_folder" --mode pure_video --execute
```

### 4. Restore / Rollback (`.bak` System)
If anything goes wrong or needs to be reset, restore all files back to their exact original names and locations:
```bash
python remediation_tool/remediate.py "path/to/course_folder" --restore
```

### 5. Batch Mode
Process all courses within a parent directory:
```bash
python remediation_tool/remediate.py "path/to/parent_directory" --batch --execute
```

---

## Architecture: Multi-Signal Corroboration Engine

The remediation pipeline operates in two distinct, auto-detected modes:

### 1. Enhanced Mode (When Markdown Transcripts Exist)
- **Deterministic Primary Key:** Every `.md` file ends with `campus.datacamp.com/courses/<course-slug>/<chapter-slug>?ex=<N>`. This deterministically identifies the chapter slug and exercise index.
- **Title Card OCR:** Early video frames (0.5s–3.0s) are extracted with `ffmpeg`, filtered for maximum Laplacian sharpness (rejecting black frames/fades), and OCR'd via Gemini Flash.
- **Duration Cross-Check:** Exact video duration from `ffprobe` is matched against timestamp ranges in the markdown transcript (`MM:SS - MM:SS`).
- **Ordinal Alignment:** Download order corroborates the sequence position when file counts match.

### 2. Pure Video Mode (When Transcripts Are Absent)
- **Play Icon (`▶`) Syllabus Extraction:** Vision AI identifies video items (`▶`, 50 XP) vs coding exercises (`<>`, 100 XP) from syllabus screenshots.
- **Global Count Constraint:** Pre-execution check verifying syllabus video count equals the `.mp4` file count.
- **Title Card OCR:** Laplacian sharpness selection + Gemini Flash OCR.
- **Opening Audio Speech Fallback:** If OCR is missing or ambiguous, extracts the first 15 seconds of audio via `ffmpeg` and uses Gemini to transcribe the instructor's spoken topic introduction.
- **Global Bipartite Assignment:** N×N similarity matrix matching videos to syllabus slots. **Zero chronological or ordinal bias.**
- **Congratulations! Anchor:** Identifies course completion video and locks it to the final syllabus slot.

---

## Output Structure

The tool organizes courses into:
```
Course Name/
├── Chapter 1 - [Chapter Title]/
│   ├── 01 - [Lesson Title].mp4
│   ├── 01 - [Lesson Title].md
│   ├── 05 - [Lesson Title].mp4
│   └── 05 - [Lesson Title].md
├── Chapter 2 - [Chapter Title]/
│   └── ...
├── 1.0.png, 2.0.png ...
├── course_schema.json
├── move_plan.json
└── backup_manifest.json
```

---

## Troubleshooting & Best Practices

- **API Key:** `GEMINI_API_KEY` is loaded from `remediation_tool/.env` or the course folder `.env`.
- **ffmpeg:** Verify `ffmpeg` and `ffprobe` are on PATH before execution.
- **Idempotency:** The tool is fully idempotent. Running against an already organized course folder reports `Nothing to do.` without modifying any files.
- **Reverting:** Always use `--restore` to safely roll back an organized folder.
