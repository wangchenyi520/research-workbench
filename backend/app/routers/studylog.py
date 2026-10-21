from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import StudyLog

router = APIRouter(prefix="/api/studylog", tags=["studylog"])


@router.get("")
def list_logs(db: Session = Depends(get_db), limit: int = 50):
    rows = db.query(StudyLog).order_by(StudyLog.date.desc(), StudyLog.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "date": r.date.isoformat(),
            "content": r.content,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("")
def add_log(data: dict, db: Session = Depends(get_db)):
    content = data.get("content", "").strip()
    if not content:
        raise HTTPException(400, "内容为空")
    d = data.get("date") or date.today().isoformat()
    try:
        log_date = datetime.strptime(str(d), "%Y-%m-%d").date()
    except ValueError:
        log_date = date.today()
    log = StudyLog(date=log_date, content=content)
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"id": log.id, "date": log.date.isoformat(), "content": log.content}


@router.delete("/{log_id}")
def delete_log(log_id: int, db: Session = Depends(get_db)):
    log = db.get(StudyLog, log_id)
    if not log:
        raise HTTPException(404, "记录不存在")
    db.delete(log)
    db.commit()
    return {"ok": True}
