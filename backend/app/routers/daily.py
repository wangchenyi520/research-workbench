from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DailyItem, Task
from ..services.daily_ops import _split_rings, apply_item_status, renorm_pending as _renorm_pending

router = APIRouter(prefix="/api/daily", tags=["daily"])

QUADRANT_LABEL = {
    "important_urgent": "重要紧急",
    "important_not": "重要不紧急",
    "not_urgent_important": "紧急不重要",
    "not_important_not": "不重要不紧急",
}
KIND_LABEL = {
    "task": "任务",
    "habit": "习惯",
    "literature": "文献",
    "manual": "手动",
    "ai": "AI建议",
}


def serialize_item(i: DailyItem, today: date, est_map: dict | None = None):
    # 顺延欠账：计划日已过还没完成（中性表述，不制造压迫感）
    overdue = i.status == "pending" and i.scheduled_date < today
    overdue_text = f"计划日 {i.scheduled_date}，待补" if overdue else ""
    # 截止已过期：due_date 到了还没完成（与顺延体系无关，可能计划日就是今天）
    due_overdue = False
    due_overdue_text = ""
    if i.status == "pending" and i.due_date and i.due_date < today:
        due_overdue = True
        due_overdue_text = f"截止日 {i.due_date}，待补"
    # 预估时长：关联任务优先（kind=task 且任务有预估），否则用清单项自身的预估
    est_minutes = None
    if i.kind == "task" and i.source_id:
        est_minutes = (est_map or {}).get(i.source_id)
    if est_minutes is None:
        est_minutes = i.est_minutes
    return {
        "id": i.id,
        "content": i.content,
        "kind": i.kind,
        "kind_label": KIND_LABEL.get(i.kind, i.kind),
        "source_id": i.source_id,
        "scheduled_date": i.scheduled_date.isoformat(),
        "due_date": i.due_date.isoformat() if i.due_date else None,
        "quadrant": i.quadrant,
        "quadrant_label": QUADRANT_LABEL.get(i.quadrant, i.quadrant),
        "weight": i.weight,
        "pomodoros": i.pomodoros,
        "time_range": i.time_range,
        "est_minutes": est_minutes,
        "status": i.status,
        "completed_at": i.completed_at.isoformat() if i.completed_at else None,
        "overdue": overdue,
        "overdue_text": overdue_text,
        "due_overdue": due_overdue,
        "due_overdue_text": due_overdue_text,
        "auto_done": i.auto_done_at is not None,
        "created_at": i.created_at.isoformat(),
    }


@router.get("")
def get_daily(db: Session = Depends(get_db)):
    """今日清单：pending 且计划日 <= 今天（未完成自动顺延）。"""
    today = date.today()
    _renorm_pending(db)  # 读取前归一（今日/顺延两套体系各自恒=100），修正历史脏数据
    items = (
        db.query(DailyItem)
        .filter(DailyItem.status == "pending", DailyItem.scheduled_date <= today)
        .order_by(DailyItem.due_date, DailyItem.created_at)
        .all()
    )
    done = (
        db.query(DailyItem)
        .filter(DailyItem.status == "done", DailyItem.completed_at >= datetime.combine(today, datetime.min.time()))
        .order_by(DailyItem.completed_at)
        .all()
    )
    today_done, today_pending, carry_done, carry_pending = _split_rings(db, today)
    # 清单项带出任务预估时长（kind=task 时），一次查询避免 N+1
    task_ids = {i.source_id for i in items + done if i.kind == "task" and i.source_id}
    est_map: dict = {}
    if task_ids:
        est_map = {t.id: t.est_minutes for t in db.query(Task.id, Task.est_minutes).filter(Task.id.in_(task_ids)).all()}
    # 今日体系
    td_w = sum(i.weight for i in today_done)
    tp_w = sum(i.weight for i in today_pending)
    t_total = td_w + tp_w
    # 顺延体系（欠账）
    cd_w = sum(i.weight for i in carry_done)
    cp_w = sum(i.weight for i in carry_pending)
    c_total = cd_w + cp_w
    return {
        "today": today.isoformat(),
        "items": [serialize_item(i, today, est_map) for i in items],
        "done": [serialize_item(i, today, est_map) for i in done],
        "stats": {
            # 今日体系（今日完成度圆环）
            "pending_weight": tp_w,
            "done_weight": td_w,
            "total_weight": t_total or 1,
            "percent": min(100, round(td_w / t_total * 100, 1)) if t_total else 0,
            "pending_count": len(today_pending),
            "done_count": len(today_done),
            # 顺延体系（顺延完成度圆环，欠账）
            "carryover_pending_weight": cp_w,
            "carryover_done_weight": cd_w,
            "carryover_total_weight": c_total or 1,
            "carryover_percent": min(100, round(cd_w / c_total * 100, 1)) if c_total else 0,
            "carryover_pending_count": len(carry_pending),
            "carryover_done_count": len(carry_done),
        },
    }


@router.get("/upcoming")
def upcoming_items(db: Session = Depends(get_db), days: int = 7):
    """未来 N 天内到期的清单项（pending）：due_date 在未来，或计划日（scheduled_date）在未来。"""
    today = date.today()
    horizon = today + timedelta(days=days)
    items = (
        db.query(DailyItem)
        .filter(
            DailyItem.status == "pending",
            or_(
                and_(DailyItem.due_date.isnot(None), DailyItem.due_date > today, DailyItem.due_date <= horizon),
                and_(DailyItem.scheduled_date > today, DailyItem.scheduled_date <= horizon),
            ),
        )
        .order_by(DailyItem.due_date, DailyItem.scheduled_date)
        .all()
    )
    task_ids = {i.source_id for i in items if i.kind == "task" and i.source_id}
    est_map: dict = {}
    if task_ids:
        est_map = {t.id: t.est_minutes for t in db.query(Task.id, Task.est_minutes).filter(Task.id.in_(task_ids)).all()}
    return [serialize_item(i, today, est_map) for i in items]


@router.post("")
def create_item(data: dict, db: Session = Depends(get_db)):
    content = (data.get("content") or "").strip()
    if not content:
        raise HTTPException(400, "内容不能为空")
    today = date.today()
    sd = data.get("scheduled_date")
    scheduled_date = today
    if sd:
        try:
            scheduled_date = date.fromisoformat(str(sd))
        except ValueError:
            pass
    due = data.get("due_date")
    due_date = None
    if due:
        try:
            due_date = date.fromisoformat(str(due))
        except ValueError:
            pass
    quadrant = data.get("quadrant") or "important_urgent"
    if quadrant not in QUADRANT_LABEL:
        quadrant = "important_urgent"
    kind = data.get("kind") or "manual"
    if kind not in KIND_LABEL:
        kind = "manual"
    weight = max(1, min(100, int(data.get("weight") or 10)))
    # C5 幂等：同文献当天已在清单里（待办）→ 直接返回已有项，不重复添加
    if kind == "literature" and data.get("source_id"):
        exists = (
            db.query(DailyItem)
            .filter(
                DailyItem.kind == "literature",
                DailyItem.source_id == data["source_id"],
                DailyItem.scheduled_date == today,
                DailyItem.status == "pending",
            )
            .first()
        )
        if exists:
            return serialize_item(exists, today)
    item = DailyItem(
        content=content,
        kind=kind,
        source_id=data.get("source_id"),
        scheduled_date=scheduled_date,
        due_date=due_date,
        quadrant=quadrant,
        weight=weight,
        pomodoros=max(0, int(data.get("pomodoros") or 0)),
        time_range=str(data.get("time_range") or "").strip(),
        est_minutes=data.get("est_minutes"),
        status="pending",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    _renorm_pending(db)
    db.refresh(item)
    return serialize_item(item, today)


@router.put("/{item_id}")
def update_item(item_id: int, data: dict, db: Session = Depends(get_db)):
    item = db.get(DailyItem, item_id)
    if not item:
        raise HTTPException(404, "清单项不存在")
    today = date.today()
    if "content" in data:
        c = (data.get("content") or "").strip()
        if not c:
            raise HTTPException(400, "内容不能为空")
        item.content = c
    for f in ("kind", "source_id", "quadrant", "pomodoros", "time_range"):
        if f in data:
            setattr(item, f, data[f])
    if "weight" in data:
        item.weight = max(1, min(100, int(data.get("weight") or 10)))
    if "scheduled_date" in data:
        try:
            item.scheduled_date = date.fromisoformat(str(data["scheduled_date"]))
        except (ValueError, TypeError):
            pass
    if "est_minutes" in data:
        em = data["est_minutes"]
        item.est_minutes = int(em) if em not in (None, "", 0) else None
    if "due_date" in data:
        d = data["due_date"]
        try:
            item.due_date = date.fromisoformat(str(d)) if d else None
        except (ValueError, TypeError):
            pass
    if "status" in data:
        # 完成/取消逻辑与桌面悬浮清单共用（services/daily_ops.apply_item_status）
        apply_item_status(db, item, data["status"], today)
    if data:
        # 用户手动改过（内容/权重/时间/状态…）= 认领该条：AI 重新生成时不再平替/撤下它
        item.auto_landed = False
    db.commit()
    db.refresh(item)
    # 权重归一：改 weight 固定该项，其余缩放；状态/内容/其他字段普通归一
    if "weight" in data:
        _renorm_pending(db, item_id, item.weight)
    elif "status" in data or "scheduled_date" in data:
        _renorm_pending(db)
    db.refresh(item)
    return serialize_item(item, today)


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(DailyItem, item_id)
    if not item:
        raise HTTPException(404, "清单项不存在")
    db.delete(item)
    db.commit()
    _renorm_pending(db)
    return {"ok": True}