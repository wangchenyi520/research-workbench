from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import JobApplication, JobEvent

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

JOB_STATUS = [
    "applied", "online_test", "interview1", "interview2", "interview3", "hr", "offer", "rejected",
]


class ApplicationCreate(BaseModel):
    company: str = Field(..., min_length=1)
    position: str = ""
    city: str = ""
    channel: str = ""
    resume_version: str = ""
    status: str = "applied"
    applied_at: date | None = None
    notes: str = ""


class ApplicationUpdate(BaseModel):
    company: str | None = None
    position: str | None = None
    city: str | None = None
    channel: str | None = None
    resume_version: str | None = None
    status: str | None = None
    applied_at: date | None = None
    notes: str | None = None


class EventCreate(BaseModel):
    event_date: date
    stage: str = "interview1"
    note: str = ""


class EventUpdate(BaseModel):
    event_date: date | None = None
    stage: str | None = None
    note: str | None = None


def _serialize(app_: JobApplication):
    return {
        "id": app_.id,
        "company": app_.company,
        "position": app_.position,
        "city": app_.city,
        "channel": app_.channel,
        "resume_version": app_.resume_version,
        "status": app_.status,
        "applied_at": app_.applied_at.isoformat() if app_.applied_at else None,
        "notes": app_.notes,
        "events": [
            {
                "id": e.id,
                "event_date": e.event_date.isoformat(),
                "stage": e.stage,
                "note": e.note,
            }
            for e in app_.events
        ],
        "created_at": app_.created_at.isoformat(),
        "updated_at": app_.updated_at.isoformat(),
    }


@router.get("/applications")
def list_applications(db: Session = Depends(get_db)):
    rows = db.query(JobApplication).order_by(JobApplication.updated_at.desc()).all()
    return [_serialize(a) for a in rows]


@router.post("/applications")
def create_application(data: ApplicationCreate, db: Session = Depends(get_db)):
    a = JobApplication(**data.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.put("/applications/{aid}")
def update_application(aid: int, data: ApplicationUpdate, db: Session = Depends(get_db)):
    a = db.get(JobApplication, aid)
    if not a:
        raise HTTPException(404, "投递不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.delete("/applications/{aid}")
def delete_application(aid: int, db: Session = Depends(get_db)):
    a = db.get(JobApplication, aid)
    if not a:
        raise HTTPException(404, "投递不存在")
    db.delete(a)
    db.commit()
    return {"ok": True}


# ---------- 时间线事件 ----------
@router.post("/applications/{aid}/events")
def add_event(aid: int, data: EventCreate, db: Session = Depends(get_db)):
    a = db.get(JobApplication, aid)
    if not a:
        raise HTTPException(404, "投递不存在")
    # C9：事件阶段领先于当前状态时自动推进投递状态（不倒退、不影响 offer/rejected 终态）
    if data.stage in JOB_STATUS:
        try:
            cur_idx = JOB_STATUS.index(a.status)
        except ValueError:
            cur_idx = -1
        if JOB_STATUS.index(data.stage) > cur_idx:
            a.status = data.stage
    e = JobEvent(application_id=aid, **data.model_dump())
    db.add(e)
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.delete("/events/{eid}")
def delete_event(eid: int, db: Session = Depends(get_db)):
    e = db.get(JobEvent, eid)
    if not e:
        raise HTTPException(404, "事件不存在")
    db.delete(e)
    db.commit()
    return {"ok": True}


# ---------- 漏斗统计 ----------
@router.get("/stats")
def job_stats(db: Session = Depends(get_db)):
    apps = db.query(JobApplication).all()
    counts = {s: 0 for s in JOB_STATUS}
    for a in apps:
        counts[a.status] = counts.get(a.status, 0) + 1
    active = [a for a in apps if a.status not in ("offer", "rejected")]
    return {
        "total": len(apps),
        "active": len(active),
        "offer": counts["offer"],
        "rejected": counts["rejected"],
        "by_status": counts,
        "pipeline": [
            {"stage": "applied", "label": "已投递", "count": counts["applied"]},
            {"stage": "online_test", "label": "笔试", "count": counts["online_test"]},
            {"stage": "interview1", "label": "一面", "count": counts["interview1"]},
            {"stage": "interview2", "label": "二面", "count": counts["interview2"]},
            {"stage": "interview3", "label": "三面", "count": counts["interview3"]},
            {"stage": "hr", "label": "HR面", "count": counts["hr"]},
            {"stage": "offer", "label": "Offer", "count": counts["offer"]},
        ],
    }
