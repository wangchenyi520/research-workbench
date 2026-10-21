from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import OJProblem, OJSolve

router = APIRouter(prefix="/api/oj", tags=["oj"])


class ProblemCreate(BaseModel):
    title: str = Field(..., min_length=1)
    platform: str = "LeetCode"
    difficulty: str = "medium"
    tags: str = ""
    status: str = "todo"
    url: str = ""
    notes: str = ""


class ProblemUpdate(BaseModel):
    title: str | None = None
    platform: str | None = None
    difficulty: str | None = None
    tags: str | None = None
    status: str | None = None
    url: str | None = None
    notes: str | None = None


def _serialize(p: OJProblem):
    return {
        "id": p.id,
        "title": p.title,
        "platform": p.platform,
        "difficulty": p.difficulty,
        "tags": p.tags,
        "status": p.status,
        "url": p.url,
        "notes": p.notes,
        "solved_count": len(p.solves),
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


@router.get("/problems")
def list_problems(db: Session = Depends(get_db)):
    rows = db.query(OJProblem).order_by(OJProblem.updated_at.desc()).all()
    return [_serialize(p) for p in rows]


@router.post("/problems")
def create_problem(data: ProblemCreate, db: Session = Depends(get_db)):
    p = OJProblem(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.put("/problems/{pid}")
def update_problem(pid: int, data: ProblemUpdate, db: Session = Depends(get_db)):
    p = db.get(OJProblem, pid)
    if not p:
        raise HTTPException(404, "题目不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return _serialize(p)


@router.delete("/problems/{pid}")
def delete_problem(pid: int, db: Session = Depends(get_db)):
    p = db.get(OJProblem, pid)
    if not p:
        raise HTTPException(404, "题目不存在")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------- 打卡 ----------
@router.post("/problems/{pid}/solve")
def mark_solved(pid: int, solve_date: date | None = None, db: Session = Depends(get_db)):
    """AC/打卡：记录一条 OJSolve，并把题目状态置为 done（若原本非 done）。"""
    p = db.get(OJProblem, pid)
    if not p:
        raise HTTPException(404, "题目不存在")
    d = solve_date or date.today()
    # 幂等：同一天同一题重复打卡不重复计数（C6）
    exists = (
        db.query(OJSolve)
        .filter(OJSolve.problem_id == pid, OJSolve.date == d, OJSolve.kind == "solve")
        .first()
    )
    if not exists:
        db.add(OJSolve(problem_id=pid, date=d, kind="solve"))
    if p.status != "done":
        p.status = "done"
    db.commit()
    return _serialize(p)


# ---------- 统计 ----------
def _streak(db: Session) -> int:
    """连续刷题天数：从今天（或昨天）往前数，按 OJSolve 去重日期。"""
    dates = {s.date for s in db.query(OJSolve.date).all()}
    if not dates:
        return 0
    today = date.today()
    start = today if today in dates else (today - timedelta(days=1))
    if start not in dates:
        return 0
    streak = 0
    cur = start
    while cur in dates:
        streak += 1
        cur -= timedelta(days=1)
    return streak


@router.get("/stats")
def oj_stats(db: Session = Depends(get_db)):
    problems = db.query(OJProblem).all()
    solves = db.query(OJSolve).all()
    today = date.today()
    today_count = sum(1 for s in solves if s.date == today)
    total_done = sum(1 for p in problems if p.status == "done")
    total = len(problems)
    diff = {"easy": 0, "medium": 0, "hard": 0}
    for p in problems:
        diff[p.difficulty] = diff.get(p.difficulty, 0) + 1
    tag_counter: dict[str, int] = {}
    for p in problems:
        if p.status != "done":
            continue
        for t in [x.strip() for x in p.tags.split(",") if x.strip()]:
            tag_counter[t] = tag_counter.get(t, 0) + 1
    top_tags = sorted(tag_counter.items(), key=lambda kv: -kv[1])[:10]
    return {
        "today_count": today_count,
        "streak": _streak(db),
        "total_done": total_done,
        "total": total,
        "difficulty": diff,
        "top_tags": top_tags,
        "total_solve_logs": len(solves),
    }
