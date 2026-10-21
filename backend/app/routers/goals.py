from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Goal, Milestone, Task
from ..schemas import GoalCreate, GoalUpdate, MilestoneCreate, MilestoneUpdate

router = APIRouter(prefix="/api/goals", tags=["goals"])


def serialize_goal(g: Goal):
    task_ids = [t.id for t in g.tasks if t.status not in ("archived", "deferred")]
    return {
        "id": g.id,
        "title": g.title,
        "description": g.description,
        "level": g.level,
        "period_start": g.period_start.isoformat() if g.period_start else None,
        "period_end": g.period_end.isoformat() if g.period_end else None,
        "parent_id": g.parent_id,
        "status": g.status,
        "progress": g.progress,
        "task_ids": task_ids,
        "created_at": g.created_at.isoformat(),
    }


@router.get("")
def list_goals(db: Session = Depends(get_db)):
    goals = db.query(Goal).order_by(Goal.created_at).all()
    return [serialize_goal(g) for g in goals]


@router.post("")
def create_goal(data: GoalCreate, db: Session = Depends(get_db)):
    g = Goal(**data.model_dump())
    db.add(g)
    db.commit()
    db.refresh(g)
    return serialize_goal(g)


@router.put("/{goal_id}")
def update_goal(goal_id: int, data: GoalUpdate, db: Session = Depends(get_db)):
    g = db.get(Goal, goal_id)
    if not g:
        raise HTTPException(404, "目标不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(g, k, v)
    db.commit()
    db.refresh(g)
    return serialize_goal(g)


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_db)):
    g = db.get(Goal, goal_id)
    if not g:
        raise HTTPException(404, "目标不存在")
    db.delete(g)
    db.commit()
    return {"ok": True}


def _subtree_tasks(db: Session, goal_id: int) -> list[Task]:
    """递归收集该目标及其所有子孙目标下的任务（C8：子目标任务计入父目标进度）。

    归档任务（远期规划被收紧归档）不计入进度分母，否则目标永远到不了 100%。
    """
    out: list[Task] = []
    stack = [goal_id]
    while stack:
        gid = stack.pop()
        out.extend(db.query(Task).filter(Task.goal_id == gid, Task.status.notin_(["archived", "deferred"])).all())
        for (cid,) in db.query(Goal.id).filter(Goal.parent_id == gid).all():
            stack.append(cid)
    return out


@router.post("/{goal_id}/progress")
def auto_progress(goal_id: int, db: Session = Depends(get_db)):
    """根据子目标/任务自动估算进度（含递归子孙目标的任务）。"""
    g = db.get(Goal, goal_id)
    if not g:
        raise HTTPException(404, "目标不存在")
    tasks = _subtree_tasks(db, goal_id)
    if tasks:
        done = sum(1 for t in tasks if t.status == "done")
        g.progress = round(done / len(tasks) * 100, 1)
    db.commit()
    return serialize_goal(g)


# ---------- Milestone ----------
def serialize_milestone(m: Milestone):
    days_left = None
    if m.due_date:
        days_left = (m.due_date - date.today()).days
    return {
        "id": m.id,
        "title": m.title,
        "description": m.description,
        "due_date": m.due_date.isoformat() if m.due_date else None,
        "completed": m.completed,
        "color": m.color,
        "sort_order": m.sort_order,
        "days_left": days_left,
    }


@router.get("/milestones")
def list_milestones(db: Session = Depends(get_db)):
    rows = db.query(Milestone).order_by(Milestone.sort_order, Milestone.due_date).all()
    return [serialize_milestone(m) for m in rows]


@router.post("/milestones")
def create_milestone(data: MilestoneCreate, db: Session = Depends(get_db)):
    m = Milestone(**data.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return serialize_milestone(m)


@router.put("/milestones/{mid}")
def update_milestone(mid: int, data: MilestoneUpdate, db: Session = Depends(get_db)):
    m = db.get(Milestone, mid)
    if not m:
        raise HTTPException(404, "里程碑不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return serialize_milestone(m)


@router.delete("/milestones/{mid}")
def delete_milestone(mid: int, db: Session = Depends(get_db)):
    m = db.get(Milestone, mid)
    if not m:
        raise HTTPException(404, "里程碑不存在")
    db.delete(m)
    db.commit()
    return {"ok": True}
