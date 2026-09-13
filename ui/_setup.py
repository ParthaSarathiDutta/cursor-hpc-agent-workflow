"""Ensure repo root is on sys.path and .env is loaded for Streamlit pages."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blast_lib.env import load_repo_dotenv  # noqa: E402

load_repo_dotenv()
