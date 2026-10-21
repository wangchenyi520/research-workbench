from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import DATA_DIR, DB_PATH
from ..database import engine, get_db
from ..models import (
    Checkin,
    Experiment,
    Goal,
    LiteratureItem,
    Milestone,
    Note,
    Paper,
    Review,
    StudyLog,
    Task,
    TimeLog,
)

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("/export")
def export_backup():
    db_file = Path(DB_PATH)
    if not db_file.exists():
        raise HTTPException(404, "数据库不存在")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = DATA_DIR / f"workbench_backup_{stamp}.db"
    out.write_bytes(db_file.read_bytes())
    return FileResponse(
        out,
        filename=f"workbench_backup_{stamp}.db",
        media_type="application/octet-stream",
    )


@router.post("/vacuum")
def vacuum_db():
    """压缩优化数据库（不删数据）。"""
    try:
        with engine.begin() as conn:
            conn.execute(text("VACUUM"))
        return {"ok": True, "size": DB_PATH.stat().st_size if DB_PATH.exists() else 0}
    except Exception as e:
        raise HTTPException(500, f"VACUUM 失败：{e}")


@router.post("/restore")
async def restore_archive(file: UploadFile, db: Session = Depends(get_db)):
    """导入全量 JSON 存档（合并）：已存在的记录跳过，缺失的补入，不覆盖现有数据。"""
    import json

    from sqlalchemy import Date, DateTime

    from ..models import (
        Checkin,
        Experiment,
        Goal,
        LiteratureItem,
        Milestone,
        Note,
        Paper,
        Review,
        StudyLog,
        Task,
        TimeLog,
    )

    MODELS = {
        "tasks": Task,
        "goals": Goal,
        "milestones": Milestone,
        "checkins": Checkin,
        "time_logs": TimeLog,
        "notes": Note,
        "literature": LiteratureItem,
        "reviews": Review,
        "study_logs": StudyLog,
        "experiments": Experiment,
        "papers": Paper,
    }
    raw = await file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "文件不是有效的 JSON 存档")
    if not isinstance(data, dict) or "exported_at" not in data:
        raise HTTPException(400, "缺少 exported_at，不是工作台存档")

    restored = 0
    skipped = 0
    errors = 0
    for table, model in MODELS.items():
        rows = data.get(table) or []
        for r in rows:
            if not isinstance(r, dict) or "id" not in r:
                continue
            if db.get(model, r["id"]):
                skipped += 1
                continue
            obj = model()
            for col in model.__table__.columns:
                if col.name not in r or r[col.name] is None:
                    continue
                v = r[col.name]
                if isinstance(col.type, (Date, DateTime)) and isinstance(v, str):
                    try:
                        if isinstance(col.type, DateTime):
                            v = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                        else:
                            v = date.fromisoformat(str(v)[:10])
                    except ValueError:
                        continue
                try:
                    setattr(obj, col.name, v)
                except Exception:
                    errors += 1
            try:
                db.add(obj)
                restored += 1
            except Exception:
                errors += 1
    db.commit()
    return {"ok": True, "restored": restored, "skipped": skipped, "errors": errors}


@router.get("/archive")
def export_archive(db: Session = Depends(get_db)):
    """导出全量 JSON 存档（所有数据，便于留存/迁移）。"""
    def rows(model):
        cols = [c.name for c in model.__table__.columns]
        return [{c: (getattr(r, c).isoformat() if hasattr(getattr(r, c), "isoformat") else getattr(r, c)) for c in cols} for r in db.query(model).all()]

    data = {
        "exported_at": datetime.now().isoformat(),
        "tasks": rows(Task),
        "goals": rows(Goal),
        "milestones": rows(Milestone),
        "checkins": rows(Checkin),
        "time_logs": rows(TimeLog),
        "notes": rows(Note),
        "literature": rows(LiteratureItem),
        "reviews": rows(Review),
        "study_logs": rows(StudyLog),
        "experiments": rows(Experiment),
        "papers": rows(Paper),
    }
    import json

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = DATA_DIR / f"workbench_archive_{stamp}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return FileResponse(out, filename=f"workbench_archive_{stamp}.json", media_type="application/json")
