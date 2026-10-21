import shutil
from datetime import date, datetime

from ..config import BACKUP_DIR, DB_PATH
from ..database import SessionLocal
from ..models import Setting

KEEP = 14


def _auto_backup_enabled(db) -> bool:
    s = db.get(Setting, "auto_backup_enabled")
    return (s.value if s else "true") == "true"


def _last_backup_date(db) -> str | None:
    s = db.get(Setting, "last_backup_date")
    return (s.value if s else "") or ""


def _set_last_backup_date(db, value: str):
    s = db.get(Setting, "last_backup_date")
    if not s:
        s = Setting(key="last_backup_date", value=value)
        db.add(s)
        try:
            db.commit()
        except Exception:
            db.rollback()
            # 并发启动时可能已被其他线程写入，改用 merge 幂等更新
            db.merge(Setting(key="last_backup_date", value=value))
            db.commit()
    else:
        s.value = value
        db.commit()


def do_backup() -> str | None:
    if not DB_PATH.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"workbench_{stamp}.db"
    shutil.copy2(DB_PATH, dest)
    files = sorted(BACKUP_DIR.glob("workbench_*.db"))
    for f in files[:-KEEP]:
        try:
            f.unlink()
        except OSError:
            pass
    return str(dest)


def auto_backup(force: bool = False):
    db = SessionLocal()
    try:
        if not _auto_backup_enabled(db):
            return None
        today = date.today().isoformat()
        if not force and _last_backup_date(db) == today:
            return None
        dest = do_backup()
        _set_last_backup_date(db, today)
        return dest
    except Exception as e:
        print(f"[backup] failed: {e}")
        return None
    finally:
        db.close()
