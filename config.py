import os
from dotenv import load_dotenv

load_dotenv()

# ── YST Backlog (source project) ──────────────────────────────────────────────
BACKLOG_API_KEY_YST: str = os.environ.get("BACKLOG_API_KEY_YST", "")
BACKLOG_HOST_YST: str = os.environ.get("BACKLOG_HOST_YST", "keieikika.backlog.com")
BACKLOG_BASE_URL_YST: str = f"https://{BACKLOG_HOST_YST}/api/v2"
PROJECT_KEY_YST: str = os.environ.get("PROJECT_KEY_YST", "KANTAKIWIZKEIZOKUKAIHATSU")

# ── VTI Backlog (optional second project) ─────────────────────────────────────
BACKLOG_API_KEY_VTI: str = os.environ.get("BACKLOG_API_KEY_VTI", "")
BACKLOG_HOST_VTI: str = os.environ.get("BACKLOG_HOST_VTI", "vti-corp.backlog.com")
BACKLOG_BASE_URL_VTI: str = f"https://{BACKLOG_HOST_VTI}/api/v2"
PROJECT_KEY_VTI: str = os.environ.get("PROJECT_KEY_VTI", "YST_KANTAKI_WIZ")
