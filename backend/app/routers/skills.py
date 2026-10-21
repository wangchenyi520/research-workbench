from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Skill, SkillStage

router = APIRouter(prefix="/api/skills", tags=["skills"])

DEFAULT_STAGES = ["入门", "进阶", "实战"]


def serialize_stage(s: SkillStage):
    return {"id": s.id, "name": s.name, "order": s.order, "progress": s.progress}


def serialize_skill(s: Skill):
    stages = s.stages or []
    stage_avg = round(sum(x.progress for x in stages) / len(stages)) if stages else 0
    # 方案A（v2.6）：关联目标时，技能总进度 = 阶段自评平均值 与 目标进度（任务完成比例）的合成，
    # 完成目标任务 → 目标进度涨 → 技能进度跟着涨，两处数据协同、减少手动维护
    if s.goal_id and s.goal is not None:
        total = round((stage_avg + (s.goal.progress or 0)) / 2)
    else:
        total = stage_avg
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "goal_id": s.goal_id,
        "goal_title": s.goal.title if s.goal else None,
        "total_progress": max(0, min(100, total)),
        "stages": [serialize_stage(x) for x in stages],
        "created_at": s.created_at.isoformat(),
    }


@router.get("")
def list_skills(db: Session = Depends(get_db)):
    return [serialize_skill(s) for s in db.query(Skill).order_by(Skill.created_at).all()]


@router.post("")
def create_skill(data: dict, db: Session = Depends(get_db)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "技能名称不能为空")
    s = Skill(
        name=name,
        description=(data.get("description") or "").strip(),
        goal_id=data.get("goal_id"),
    )
    db.add(s)
    db.flush()
    for i, n in enumerate(DEFAULT_STAGES):
        db.add(SkillStage(skill_id=s.id, name=n, order=i, progress=0))
    db.commit()
    db.refresh(s)
    return serialize_skill(s)


@router.put("/{skill_id}")
def update_skill(skill_id: int, data: dict, db: Session = Depends(get_db)):
    s = db.get(Skill, skill_id)
    if not s:
        raise HTTPException(404, "技能不存在")
    if "name" in data:
        n = (data.get("name") or "").strip()
        if not n:
            raise HTTPException(400, "技能名称不能为空")
        s.name = n
    if "description" in data:
        s.description = data["description"]
    if "goal_id" in data:
        s.goal_id = data["goal_id"]
    db.commit()
    db.refresh(s)
    return serialize_skill(s)


@router.delete("/{skill_id}")
def delete_skill(skill_id: int, db: Session = Depends(get_db)):
    s = db.get(Skill, skill_id)
    if not s:
        raise HTTPException(404, "技能不存在")
    db.delete(s)
    db.commit()
    return {"ok": True}


# ---------- 阶段 ----------
@router.post("/{skill_id}/stages")
def add_stage(skill_id: int, data: dict, db: Session = Depends(get_db)):
    s = db.get(Skill, skill_id)
    if not s:
        raise HTTPException(404, "技能不存在")
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "阶段名称不能为空")
    nxt = max((x.order for x in s.stages), default=-1) + 1
    st = SkillStage(skill_id=skill_id, name=name, order=nxt, progress=max(0, min(100, int(data.get("progress") or 0))))
    db.add(st)
    db.commit()
    db.refresh(st)
    return serialize_stage(st)


@router.put("/stages/{stage_id}")
def update_stage(stage_id: int, data: dict, db: Session = Depends(get_db)):
    st = db.get(SkillStage, stage_id)
    if not st:
        raise HTTPException(404, "阶段不存在")
    if "name" in data:
        n = (data.get("name") or "").strip()
        if not n:
            raise HTTPException(400, "阶段名称不能为空")
        st.name = n
    if "progress" in data:
        st.progress = max(0, min(100, int(data.get("progress") or 0)))
    if "order" in data:
        st.order = int(data["order"])
    db.commit()
    db.refresh(st)
    return serialize_stage(st)


@router.delete("/stages/{stage_id}")
def delete_stage(stage_id: int, db: Session = Depends(get_db)):
    st = db.get(SkillStage, stage_id)
    if not st:
        raise HTTPException(404, "阶段不存在")
    db.delete(st)
    db.commit()
    return {"ok": True}