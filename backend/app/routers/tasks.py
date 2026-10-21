from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Checkin, Task, TaskSubtask, TimeLog
from ..schemas import (
    CheckinCreate,
    SubtaskCreate,
    SubtaskUpdate,
    TaskCreate,
    TaskUpdate,
    TimeLogCreate,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _apply_status_change(db, t: Task, new_status: str, old_status: str):
    """任务状态变更：维护完成时间 + 反向联动今日清单（done 勾选/恢复，不误伤手动完成）。"""
    t.status = new_status
    if new_status == "done":
        t.completed_at = datetime.now()
    elif new_status == "todo":
        t.completed_at = None
    from ..models import DailyItem
    from ..routers.daily import _renorm_pending

    today = date.today()
    linked = (
        db.query(DailyItem)
        .filter(
            DailyItem.kind == "task",
            DailyItem.source_id == t.id,
            DailyItem.scheduled_date <= today,
        )
        .all()
    )
    if new_status == "done":
        for d in linked:
            if d.status == "pending":
                d.status = "done"
                d.completed_at = datetime.now()
                d.auto_done_at = datetime.now()
        _renorm_pending(db)
    elif old_status == "done":
        for d in linked:
            if d.status == "done" and d.completed_at and d.completed_at.date() == date.today():
                d.status = "pending"
                d.completed_at = None
                d.auto_done_at = None
        _renorm_pending(db)
    db.commit()


def _next_repeat_date(t: Task):
    """循环任务的下一生成日：从今天（含）起第一个匹配 weekday，最多找 15 天。"""
    wds = {int(x) for x in (t.repeat_weekdays or "").split(",") if x.strip().isdigit()}
    if not wds:
        return None
    d = date.today()
    for _ in range(15):
        if d.weekday() in wds:
            return d
        d += timedelta(days=1)
    return None


def serialize_task(t: Task):
    today = date.today()
    checkins = t.checkins
    total_duration = sum(ts.duration_seconds for ts in t.time_logs)
    checked_today = any(c.date == today for c in checkins)
    last_checkin = max((c.date for c in checkins), default=None)
    # 习惯连续打卡天数：今天或昨天已打卡则从那天起往回数（与仪表盘统计语义一致）
    streak = 0
    if t.task_type == "habit" and checkins:
        dates = {c.date for c in checkins}
        d = today
        if d not in dates and (d - timedelta(days=1)) in dates:
            d -= timedelta(days=1)
        while d in dates:
            streak += 1
            d -= timedelta(days=1)
    next_repeat = _next_repeat_date(t)
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "task_type": t.task_type,
        "status": t.status,
        "priority": t.priority,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "goal_id": t.goal_id,
        "goal_title": t.goal.title if t.goal else None,
        "tags": t.tags,
        "pomodoro_minutes": t.pomodoro_minutes,
        "break_minutes": t.break_minutes,
        "sort_order": t.sort_order,
        "checked_today": checked_today,
        "last_checkin": last_checkin.isoformat() if last_checkin else None,
        "streak": streak,
        "total_seconds": total_duration,
        "created_at": t.created_at.isoformat(),
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "repeat_weekdays": t.repeat_weekdays or "",
        "repeat_source_id": t.repeat_source_id,
        "next_repeat": next_repeat.isoformat() if next_repeat else None,
        "est_minutes": t.est_minutes,
        "actual_minutes": t.actual_minutes,
        "subtasks": [
            {"id": s.id, "title": s.title, "done": s.done, "sort_order": s.sort_order}
            for s in t.subtasks
        ],
    }


@router.post("/{task_id}/subtasks")
def create_subtask(task_id: int, data: SubtaskCreate, db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    max_order = (
        db.query(func.coalesce(func.max(TaskSubtask.sort_order), -1))
        .filter(TaskSubtask.task_id == task_id)
        .scalar()
    )
    s = TaskSubtask(task_id=task_id, title=data.title, sort_order=int(max_order or -1) + 1)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "title": s.title, "done": s.done}


@router.put("/subtasks/{subtask_id}")
def update_subtask(subtask_id: int, data: SubtaskUpdate, db: Session = Depends(get_db)):
    s = db.get(TaskSubtask, subtask_id)
    if not s:
        raise HTTPException(404, "子任务不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    # 子任务全部勾选完成 → 自动完成任务（含今日清单联动）；取消勾选 → 父任务恢复为待办（双向联动）
    task = db.get(Task, s.task_id)
    if task and task.status not in ("archived", "deferred"):
        undone = (
            db.query(TaskSubtask)
            .filter(TaskSubtask.task_id == task.id, TaskSubtask.done == False)  # noqa: E712
            .count()
        )
        if undone == 0 and task.status != "done":
            _apply_status_change(db, task, "done", task.status)
            db.commit()
        elif undone > 0 and task.status == "done":
            # 取消勾选：有未完成子任务 → 撤销自动完成（恢复待办，清空完成时间）
            _apply_status_change(db, task, "todo", task.status)
            db.commit()
    db.refresh(s)
    return {"id": s.id, "title": s.title, "done": s.done}


@router.delete("/subtasks/{subtask_id}")
def delete_subtask(subtask_id: int, db: Session = Depends(get_db)):
    s = db.get(TaskSubtask, subtask_id)
    if not s:
        raise HTTPException(404, "子任务不存在")
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.get("/active")
def active_tasks(db: Session = Depends(get_db)):
    """进行中的任务（doing，不含习惯）：供全局「进行中」悬浮胶囊展示（最多 5 个）。"""
    rows = (
        db.query(Task)
        .filter(Task.status == "doing", Task.task_type != "habit")
        .order_by(Task.sort_order, Task.created_at.desc())
        .limit(5)
        .all()
    )
    return {
        "items": [
            {"id": t.id, "title": t.title, "est_minutes": t.est_minutes}
            for t in rows
        ]
    }


@router.get("")
def list_tasks(db: Session = Depends(get_db), task_type: str | None = None):
    q = db.query(Task).options(
        selectinload(Task.checkins),
        selectinload(Task.time_logs),
        selectinload(Task.subtasks),
    ).filter(Task.status.notin_(["archived", "deferred"]))
    if task_type:
        q = q.filter(Task.task_type == task_type)
    # 排序：用户拖拽过的按 sort_order；未拖拽(0)的默认按急迫度
    # （有截止日期在前按 DDL 近→远，无截止按创建时间新→旧）
    return [
        serialize_task(t)
        for t in q.order_by(
            Task.sort_order,
            Task.due_date.is_(None),
            Task.due_date,
            Task.created_at.desc(),
        ).all()
    ]


@router.post("")
def create_task(data: TaskCreate, db: Session = Depends(get_db)):
    # 未显式指定番茄时长时，使用设置里的默认值
    from ..models import Setting

    payload = data.model_dump()
    s_pomo = db.get(Setting, "pomodoro_minutes")
    s_break = db.get(Setting, "break_minutes")
    # B4：只在前端未显式传时长时才用设置默认值（显式填 25/5 不再被覆盖）
    if "pomodoro_minutes" not in data.model_fields_set:
        try:
            payload["pomodoro_minutes"] = int((s_pomo.value if s_pomo else "") or 25)
        except ValueError:
            payload["pomodoro_minutes"] = 25
    if "break_minutes" not in data.model_fields_set:
        try:
            payload["break_minutes"] = int((s_break.value if s_break else "") or 5)
        except ValueError:
            payload["break_minutes"] = 5
    t = Task(**payload)
    db.add(t)
    db.commit()
    db.refresh(t)
    return serialize_task(t)


@router.put("/{task_id}")
def update_task(task_id: int, data: TaskUpdate, db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    old_status = t.status
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(t, k, v)
    # 状态变更时维护完成时间与今日清单联动
    if "status" in update_data and update_data["status"] != old_status:
        _apply_status_change(db, t, update_data["status"], old_status)
    db.commit()
    db.refresh(t)
    return serialize_task(t)


@router.post("/{task_id}/duplicate")
def duplicate_task(task_id: int, db: Session = Depends(get_db)):
    """复制任务为新的待办（复制字段，不复制打卡/计时记录，DDL 置空）。"""
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    nt = Task(
        title=t.title,
        description=t.description,
        task_type=t.task_type,
        priority=t.priority,
        goal_id=t.goal_id,
        tags=t.tags,
        pomodoro_minutes=t.pomodoro_minutes,
        break_minutes=t.break_minutes,
    )
    db.add(nt)
    db.commit()
    db.refresh(nt)
    return serialize_task(nt)


@router.delete("/trash")
def purge_all_trash(db: Session = Depends(get_db)):
    """清空回收站：彻底删除所有已归档（archived）任务。"""
    count = db.query(Task).filter(Task.status == "archived").delete()
    db.commit()
    return {"ok": True, "purged": count}


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    t.status = "archived"
    db.commit()
    return {"ok": True}


# ---------- 回收站 ----------
@router.get("/trash")
def list_trash(db: Session = Depends(get_db)):
    rows = (
        db.query(Task)
        .filter(Task.status == "archived")
        .order_by(Task.created_at.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "title": t.title,
            "task_type": t.task_type,
            "created_at": t.created_at.isoformat(),
            "archived_at": (t.updated_at or t.created_at).isoformat(),
        }
        for t in rows
    ]


@router.post("/{task_id}/restore")
def restore_task(task_id: int, db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    t.status = "todo"
    t.completed_at = None
    db.commit()
    return {"ok": True}


@router.delete("/{task_id}/purge")
def purge_task(task_id: int, db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    db.delete(t)
    db.commit()
    return {"ok": True}


# ---------- 子任务 ----------
@router.get("/{task_id}/subtasks")
def list_subtasks(task_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(TaskSubtask)
        .filter(TaskSubtask.task_id == task_id)
        .order_by(TaskSubtask.sort_order, TaskSubtask.id)
        .all()
    )
    return [{"id": s.id, "title": s.title, "done": s.done} for s in rows]


# ---------- Checkin (打卡) ----------
@router.post("/{task_id}/checkins")
def checkin(task_id: int, data: CheckinCreate, db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.task_type != "habit":
        raise HTTPException(400, "只有习惯类任务可以打卡")
    existing = (
        db.query(Checkin)
        .filter(Checkin.task_id == task_id, Checkin.date == data.date)
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()
        return {"ok": True, "checked": False}
    db.add(Checkin(task_id=task_id, date=data.date, note=data.note))
    db.commit()
    return {"ok": True, "checked": True}


@router.get("/{task_id}/checkins")
def list_checkins(task_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(Checkin.date)
        .filter(Checkin.task_id == task_id)
        .order_by(Checkin.date.desc())
        .all()
    )
    return [r[0].isoformat() for r in rows]


# ---------- Time log (计时/番茄钟) ----------
@router.post("/{task_id}/timelogs")
def start_time_log(task_id: int, data: TimeLogCreate, db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    log = TimeLog(task_id=task_id, kind=data.kind, note=data.note)
    if data.start_time:
        log.start_time = data.start_time
    else:
        log.start_time = datetime.now()
    if data.duration_seconds and data.duration_seconds > 0:
        # 带显式时长的记录（手动补录）属于已完成记录：立刻写 end_time 标记已关账，
        # 否则会被退出收尾/启动自愈当成进行中的计时，按墙钟重新计算成几天的假时长
        log.duration_seconds = data.duration_seconds
        log.end_time = log.start_time + timedelta(seconds=data.duration_seconds)
    if data.end_time:
        log.end_time = data.end_time
    db.add(log)
    db.commit()
    db.refresh(log)
    return {
        "id": log.id,
        "start_time": log.start_time.isoformat(),
        "end_time": log.end_time.isoformat() if log.end_time else None,
    }


@router.put("/timelogs/{log_id}")
def end_time_log(log_id: int, data: dict | None = None, db: Session = Depends(get_db)):
    """结束计时。可传 duration_seconds 显式指定实际计秒数（暂停过的时间不计）。"""
    log = db.get(TimeLog, log_id)
    if not log:
        raise HTTPException(404, "记录不存在")
    if not log.end_time:
        log.end_time = datetime.now()
        counted = (data or {}).get("duration_seconds")
        if counted is not None and int(counted) >= 0:
            # 前端/桌面时钟本地计秒（支持暂停），显式写入
            log.duration_seconds = int(counted)
        else:
            log.duration_seconds = int((log.end_time - log.start_time).total_seconds())
        # B10：番茄钟不足 60 秒视为无效（开始即完成不算一个番茄），删除不计入统计/🍅
        if log.kind == "pomodoro" and log.duration_seconds < 60:
            db.delete(log)
            db.commit()
            return {"id": log_id, "duration_seconds": 0, "end_time": None, "ignored": True}
        # 番茄钟完成 → 今日清单关联项累计 🍅
        if log.kind == "pomodoro":
            from ..models import DailyItem

            item = (
                db.query(DailyItem)
                .filter(DailyItem.kind == "task", DailyItem.source_id == log.task_id, DailyItem.status == "pending")
                .first()
            )
            if item:
                item.pomodoros += 1
    db.commit()
    return {
        "id": log.id,
        "duration_seconds": log.duration_seconds,
        "end_time": log.end_time.isoformat(),
    }


@router.delete("/timelogs/{log_id}")
def delete_time_log(log_id: int, db: Session = Depends(get_db)):
    log = db.get(TimeLog, log_id)
    if not log:
        raise HTTPException(404, "记录不存在")
    db.delete(log)
    db.commit()
    return {"ok": True}


@router.get("/stats/today")
def today_stats(db: Session = Depends(get_db)):
    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    total = (
        db.query(func.coalesce(func.sum(TimeLog.duration_seconds), 0))
        .filter(TimeLog.start_time >= start)
        .scalar()
    )
    pomodoros = (
        db.query(func.count(TimeLog.id))
        .filter(
            TimeLog.kind == "pomodoro",
            TimeLog.start_time >= start,
            TimeLog.end_time.isnot(None),
        )
        .scalar()
    )
    return {"total_seconds": int(total or 0), "pomodoros": int(pomodoros or 0)}


@router.get("/stats/heatmap")
def heatmap(db: Session = Depends(get_db), days: int = 90):
    """返回最近 N 天每天的有效投入秒数（含打卡任务标记）。"""
    from_date = date.today() - timedelta(days=days)
    rows = (
        db.query(TimeLog.task_id, TimeLog.start_time, TimeLog.duration_seconds)
        .filter(TimeLog.start_time >= datetime.combine(from_date, datetime.min.time()))
        .all()
    )
    day_map: dict[str, int] = {}
    for _, st, dur in rows:
        key = st.date().isoformat()
        day_map[key] = day_map.get(key, 0) + (dur or 0)
    checkin_dates = (
        db.query(Checkin.date).filter(Checkin.date >= from_date).all()
    )
    for (d,) in checkin_dates:
        day_map.setdefault(d.isoformat(), day_map.get(d.isoformat(), 0))
    return {"days": days, "data": day_map}
