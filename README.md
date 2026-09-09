# DataCamp Course Remediation Pipeline

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

An autonomous, multi-signal remediation engine designed to transform flat, disorganized dumps of downloaded DataCamp courses into clean, structured, and numbered chapter libraries with **zero silent misfiles**.

---

## The Problem

When downloading courses in parts, assets typically land in a single unorganized folder:
* **Unnamed Videos:** Files named generically like `video.mp4`, `video (1).mp4`, `video (10).mp4`.
* **Noisy Transcripts:** Markdown files with extra suffixes, e.g. `Multi-step prompting _ OpenAI.md` or `Deployment _ Theory.md`.
* **Chapter Outlines:** Loose screenshots (`1.0.png`, `2.0.png`...) showing the syllabus.

Sorting dozens of lessons manually is tedious and prone to errors. Furthermore, naive matching algorithms fail because:
1. Videos are often downloaded asynchronously or out of order.
2. Title cards may fade in after 1–2 seconds.
3. Some lessons share identical or near-duplicate titles across chapters.

---

## The Solution

This tool combines **deterministic parsing**, **computer vision OCR**, **audio/video duration analysis**, and **smart multi-signal corroboration** to match every video and transcript to its canonical position in the course syllabus.

```
Raw Flat Folder                                      Organized Course
-------------------                                  ----------------
1.0.png                                              ├── Chapter 1 - Introduction/
2.0.png                                              │   ├── 01 - What is the API.mp4
video.mp4                                            │   ├── 01 - What is the API.md
video (10).mp4             =================>        │   ├── 05 - First Request.mp4
Multi-step prompting.md                              │   └── 05 - First Request.md
What is the API.md                                   ├── Chapter 2 - Advanced/
...                                                  │   └── ...
                                                     ├── course_schema.json
                                                     ├── move_plan.json
                                                     └── backup_manifest.json
```

---

## Key Features

* **Multi-Signal Corroboration (No Best-Guess Moves):**
  * **Deterministic URL Indexing:** Extracts `(chapter_slug, ex)` directly from the transcript footer URL for 100% ground truth lesson identification.
  * **Vision AI Title Card OCR:** Samples video frames across early timestamps (`0.5s` to `3.0s`) and filters for highest Laplacian variance (sharpness), ignoring fade-ins and black frames.
  * **Duration Cross-Checking:** Verifies `ffprobe` video duration against the lesson transcript timestamp ranges.
  * **Ordinal Alignment:** Corroborates chronological sequence when video counts align.
* **100% Rollback Protection (`--restore`):** Every execution writes a `backup_manifest.json`. If anything ever looks wrong, a single command restores all files back to their exact original names and paths.
* **Dry-Run by Default:** Inspect the full execution manifest (`move_plan.json`) before moving a single file on disk.
* **Zero Dependencies Outside Standard Open-Source Stacks:** Uses `google-genai` / Gemini Flash Vision for free-tier speed, `opencv-python` for frame sharpness scoring, and `ffmpeg` for frame extraction.
* **Fully Idempotent:** Safe to run repeatedly; detects already-organized folders and performs zero redundant operations.
* **Batch Processing:** Organize an entire library of courses with a single `--batch` flag.

---

## Installation

### 1. Prerequisites
* **Python 3.10+**
* **FFmpeg and FFprobe:** Ensure `ffmpeg` and `ffprobe` are installed and available on your system `PATH`.
  * *Windows:* `winget install ffmpeg`
  * *macOS:* `brew install ffmpeg`
  * *Linux:* `sudo apt-get install ffmpeg`

### 2. Clone and Setup
```bash
git clone https://github.com/your-username/datacamp-remediation.git
cd datacamp-remediation

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### 3. Configure API Key
Create a `.env` file in the project directory:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

---

## Usage

### 1. Dry Run (Preview Changes)
Simulate the reorganization and generate the audit manifest without touching files:
```bash
python remediate.py "/path/to/course_folder"
```

### 2. Execute Organization
Organize the course into structured chapter folders with automatic backup manifest creation:
```bash
python remediate.py "/path/to/course_folder" --execute
```

### 3. Instant Rollback / Restore
Restore all files back to their original names and locations:
```bash
python remediate.py "/path/to/course_folder" --restore
```

### 4. Batch Mode
Process all courses inside a parent learning directory:
```bash
python remediate.py "/path/to/all_courses" --batch --execute
```

---

## Architecture & Pipeline Flow

```mermaid
flowchart TD
    A[Course Folder] --> B[Stage 0: Schema Extraction]
    B -->|Outline PNGs| B1[Gemini Flash Vision]
    B1 -->|course_schema.json| C[Canonical Course Tree]

    A --> D[Stage 1: Transcript Normalization]
    D -->|Footer URLs ?ex=N| E[Deterministic Lesson Mapping]

    A --> F[Stage 2: Video Identification]
    F -->|ffmpeg early frames| G[Laplacian Sharpness Filter]
    G -->|Optimal Frame| H[Gemini OCR Title Card]

    C & E & H --> I[Stage 3: Multi-Signal Matcher]
    I -->|Corroborate >= 2 Signals| J[Move Plan Manifest]

    J --> K[Stage 4: File Operations]
    K -->|--execute| L[Structured Chapter Directories]
    K -->|backup_manifest.json| M[Full Rollback Capability]
```

---

## Project Structure

```
remediation_tool/
├── remediate.py           # CLI entry point (dry-run, --execute, --restore, --batch)
├── schema_extractor.py    # Vision AI syllabus parser (outline images -> course_schema.json)
├── md_parser.py           # Regex extractor for deterministic (?ex=N) footer URLs
├── video_identifier.py    # Multi-timestamp frame extractor, sharpness scorer, and OCR
├── matcher.py             # Multi-signal corroboration engine
├── file_ops.py            # Manifest generator, safe mover, and backup/restore engine
├── config.py              # Environment configuration and thresholds
├── utils.py               # Sanitization, Laplacian sharpness, hashing, time utilities
├── requirements.txt       # Python dependencies
├── .env.example           # Example configuration template
├── .gitignore             # Ignore keys, cache, and OS files
└── README.md              # Documentation
```

---

## License

This project is licensed under the MIT License.
