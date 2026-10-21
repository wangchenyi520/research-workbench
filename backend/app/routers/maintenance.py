from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import AUDIO_DIR, BACKUP_DIR, DATA_DIR, IMAGES_DIR
from ..database import get_db
from ..models import Note
from ..services.active_sessions import suspend_all

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])

KEEP_BACKUPS = 20  # 保留最近的手动备份/存档份数


@router.post("/suspend-active")
def suspend_active(db: Session = Depends(get_db)):
    """工作台退出时调用：暂停/结算保存所有进行中的计时（幂等）。

    - 考勤在岗 → 自动「离开」；任务番茄钟 → 存快照下次启动恢复为已暂停；
    - 页面内计时 → 关账；自由番茄钟 → 结算入账并结束。
    """
    return suspend_all(db)


@router.post("/cleanup")
def cleanup(db: Session = Depends(get_db)):
    """清理未引用图片、临时音频、过期手动备份。返回清理统计。"""
    result = {"images": 0, "audio": 0, "backups": 0}

    # 1. 收集所有笔记中引用的图片文件名
    used = set()
    for content, in db.query(Note.content).all():
        for frag in (content or "").split("/api/notes/images/"):
            if frag:
                name = frag.split('"')[0].split(")")[0].split(" ")[0]
                if name and "/" not in name and "\\" not in name:
                    used.add(name)

    # 2. 清理未引用图片
    if IMAGES_DIR.exists():
        for f in IMAGES_DIR.iterdir():
            if f.is_file() and f.name not in used:
                try:
                    f.unlink()
                    result["images"] += 1
                except OSError:
                    pass

    # 3. 清理临时音频
    if AUDIO_DIR.exists():
        for f in AUDIO_DIR.iterdir():
            if f.is_file():
                try:
                    f.unlink()
                    result["audio"] += 1
                except OSError:
                    pass

    # 4. 清理过期手动备份/存档（保留最近 KEEP_BACKUPS 份）
    if BACKUP_DIR.exists():
        files = sorted(BACKUP_DIR.glob("*.db")) + sorted(BACKUP_DIR.glob("*.json"))
        for f in files[:-KEEP_BACKUPS]:
            try:
                f.unlink()
                result["backups"] += 1
            except OSError:
                pass

    return {"ok": True, "cleaned": result}
