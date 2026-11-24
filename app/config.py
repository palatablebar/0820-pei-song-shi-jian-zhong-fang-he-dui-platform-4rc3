import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE = 256 * 1024
MAX_ROWS = 2000
RULE_VERSION = "1.0.0"
OWNER_GUARD_SECONDS = int(os.getenv("OWNER_GUARD_SECONDS", "1800"))
