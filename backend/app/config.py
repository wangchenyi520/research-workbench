import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional for minimal installs
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent
if load_dotenv is not None:
    load_dotenv(BASE_DIR.parent / ".env")
DATA_DIR = Path(os.environ.get("WORKBENCH_DATA", BASE_DIR / "data"))
IMAGES_DIR = DATA_DIR / "images"
ATTACH_DIR = DATA_DIR / "attachments"
PDF_DIR = DATA_DIR / "pdfs"
DB_PATH = Path(os.environ.get("WORKBENCH_DB", DATA_DIR / "workbench.db"))
BACKUP_DIR = DATA_DIR / "backups"
AUDIO_DIR = DATA_DIR / "audio"
# 每日论文 PDF 下载目录（用户指定固定路径：项目根 daily_paper，可用环境变量覆盖）
DAILY_PAPER_DIR = Path(
    os.environ.get("WORKBENCH_DAILY_PAPER_DIR", BASE_DIR.parent / "daily_paper")
)

DATA_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
ATTACH_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
DAILY_PAPER_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
ZOTERO_LOCAL_URL = "http://127.0.0.1:23119"
ZOTERO_API_URL = "https://api.zotero.org"
