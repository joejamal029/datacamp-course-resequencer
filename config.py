import os
from pathlib import Path
from dotenv import load_dotenv

# Try loading from multiple standard .env locations
_TOOL_DIR = Path(__file__).resolve().parent
_PARENT_DIR = _TOOL_DIR.parent

# Load tool dir .env, then parent dir .env
load_dotenv(_TOOL_DIR / ".env")
load_dotenv(_PARENT_DIR / ".env")

def load_course_env(course_dir: Path | str | None = None):
    """Load .env if present in the course directory or working directory."""
    if course_dir:
        c_path = Path(course_dir)
        if (c_path / ".env").exists():
            load_dotenv(c_path / ".env", override=True)
    load_dotenv(Path.cwd() / ".env")

def get_gemini_api_key(course_dir: Path | str | None = None) -> str:
    """Retrieve the Gemini API key or raise an instructive error."""
    load_course_env(course_dir)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "GEMINI_API_KEY is not set.\n"
            "Please create a .env file with 'GEMINI_API_KEY=your_key_here' in:\n"
            f"  - {str(_TOOL_DIR / '.env')}\n"
            f"  - or {str(_PARENT_DIR / '.env')}\n"
            "or set the GEMINI_API_KEY environment variable."
        )
    return key

# Configuration Defaults
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
CONFIDENCE_THRESHOLD = 0.70
DURATION_TOLERANCE_SECONDS = 15.0
CACHE_DIR = _TOOL_DIR / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
