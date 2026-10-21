import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Experiment, Paper

router = APIRouter(prefix="/api/research", tags=["research"])


# ---------- Experiment ----------
class ExperimentCreate(BaseModel):
    title: str = Field(..., min_length=1)
    dataset: str = ""
    model: str = ""
    metrics: dict = {}
    baseline: str = ""
    status: str = "running"
    notes: str = ""


class ExperimentUpdate(BaseModel):
    title: str | None = None
    dataset: str | None = None
    model: str | None = None
    metrics: dict | None = None
    baseline: str | None = None
    status: str | None = None
    notes: str | None = None


def _serialize_exp(e: Experiment):
    try:
        metrics = json.loads(e.metrics or "{}")
    except Exception:
        metrics = {}
    return {
        "id": e.id,
        "title": e.title,
        "dataset": e.dataset,
        "model": e.model,
        "metrics": metrics,
        "baseline": e.baseline,
        "status": e.status,
        "notes": e.notes,
        "created_at": e.created_at.isoformat(),
        "updated_at": e.updated_at.isoformat(),
    }


@router.get("/experiments")
def list_experiments(db: Session = Depends(get_db)):
    rows = db.query(Experiment).filter(Experiment.status != "archived").order_by(Experiment.updated_at.desc()).all()
    return [_serialize_exp(e) for e in rows]


@router.post("/experiments")
def create_experiment(data: ExperimentCreate, db: Session = Depends(get_db)):
    e = Experiment(**{**data.model_dump(), "metrics": json.dumps(data.metrics, ensure_ascii=False)})
    db.add(e)
    db.commit()
    db.refresh(e)
    return _serialize_exp(e)


@router.put("/experiments/{eid}")
def update_experiment(eid: int, data: ExperimentUpdate, db: Session = Depends(get_db)):
    e = db.get(Experiment, eid)
    if not e:
        raise HTTPException(404, "实验不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        if k == "metrics" and v is not None:
            v = json.dumps(v, ensure_ascii=False)
        setattr(e, k, v)
    db.commit()
    db.refresh(e)
    return _serialize_exp(e)


@router.delete("/experiments/{eid}")
def delete_experiment(eid: int, db: Session = Depends(get_db)):
    e = db.get(Experiment, eid)
    if not e:
        raise HTTPException(404, "实验不存在")
    e.status = "archived"
    db.commit()
    return {"ok": True}


# ---------- Paper ----------
class PaperCreate(BaseModel):
    title: str = Field(..., min_length=1)
    venue: str = ""
    status: str = "planning"
    submitted_at: date | None = None
    notes: str = ""


class PaperUpdate(BaseModel):
    title: str | None = None
    venue: str | None = None
    status: str | None = None
    submitted_at: date | None = None
    notes: str | None = None


PAPER_STATUS = ["planning", "writing", "draft", "polish", "submitted", "revision", "accepted"]


def _serialize_paper(p: Paper):
    return {
        "id": p.id,
        "title": p.title,
        "venue": p.venue,
        "status": p.status,
        "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
        "notes": p.notes,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


@router.get("/papers")
def list_papers(db: Session = Depends(get_db)):
    rows = db.query(Paper).order_by(Paper.updated_at.desc()).all()
    return [_serialize_paper(p) for p in rows]


@router.post("/papers")
def create_paper(data: PaperCreate, db: Session = Depends(get_db)):
    p = Paper(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return _serialize_paper(p)


@router.put("/papers/{pid}")
def update_paper(pid: int, data: PaperUpdate, db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        raise HTTPException(404, "论文不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return _serialize_paper(p)


@router.delete("/papers/{pid}")
def delete_paper(pid: int, db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        raise HTTPException(404, "论文不存在")
    db.delete(p)
    db.commit()
    return {"ok": True}
