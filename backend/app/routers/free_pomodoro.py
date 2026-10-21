"""自由番茄钟：不绑定具体任务的学习专注计时。

架构要点：
- 后端 session 是权威计时源（数据库 started_at / work_seconds），
  桌面窗口关闭、浏览器页面刷新都不影响计时；退出进程时 shutdown 保存。
- tomato 模式：每完成一个工作轮写一条 TimeLog（task_id=NULL, kind=pomodoro，
  note=学习状态）→ 完整计入现有统计（投入时长/番茄数/热力图/日历/报告）；
  暂停不计时；休息结束自动进入下一轮。
- free 模式：无轮次无休息，结束/退出时整段写一条 TimeLog（≥60 秒才计入）。
- abandon：不写任何 TimeLog（与任务番茄钟放弃语义一致）。
- 与任务番茄钟互斥：同一时间只能开一个（桌面悬浮钟全局唯一 + 未关账
  pomodoro timelog 检查）。
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import FreePomodoro, TimeLog
from ..services.notification import notify

router = APIRouter(prefix="/api/free-pomodoro", tags=["free-pomodoro"])


class StartBody(BaseModel):
    state: str = ""
    mode: str = "tomato"  # tomato / free
    work_min: int = 25
    break_min: int = 5


def _effective_seconds(s: FreePomodoro, now: datetime) -> int:
    """有效工作秒（含当前进行中阶段，暂停不计）。"""
    base = s.work_seconds
    if s.status == "running" and s.phase == "work" and s.phase_started_at:
        base += int(max(0, (now - s.phase_started_at).total_seconds()))
    return base


def _remaining(s: FreePomodoro, now: datetime):
    """当前阶段剩余秒；free 模式无倒计时返回 None。"""
    if s.mode == "free":
        return None
    if s.phase == "work":
        return max(0, s.work_min * 60 - (_effective_seconds(s, now) % (s.work_min * 60)))
    if s.phase_started_at:
        return max(0, s.break_min * 60 - int((now - s.phase_started_at).total_seconds()))
    return 0


def serialize(s: FreePomodoro | None, now: datetime | None = None):
    if not s:
        return None
    now = now or datetime.now()
    return {
        "id": s.id,
        "state": s.state or "",
        "mode": s.mode,
        "status": s.status,
        "phase": s.phase,
        "paused": s.status == "paused",
        "work_min": s.work_min,
        "break_min": s.break_min,
        "rounds": s.rounds,
        "work_seconds": _effective_seconds(s, now),
        "remaining": _remaining(s, now),
        "started_at": s.started_at.isoformat(),
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "created_at": s.created_at.isoformat(),
    }


def _running_task_pomodoro(db: Session) -> bool:
    """是否存在未关账的任务番茄钟（前端本地计时未结束也会留未关账 timelog）。"""
    return (
        db.query(TimeLog)
        .filter(
            TimeLog.kind == "pomodoro",
            TimeLog.task_id.isnot(None),
            TimeLog.end_time.is_(None),
        )
        .first()
        is not None
    )


def _latest(db: Session) -> FreePomodoro | None:
    return db.query(FreePomodoro).order_by(FreePomodoro.id.desc()).first()


def _close_running(db: Session, s: FreePomodoro, now: datetime):
    """结算当前进行中的自由番茄（start/shutdown 时用于清理残留 session）。"""
    if s.status not in ("running", "paused"):
        return
    eff = _effective_seconds(s, now)
    if eff >= 60:
        db.add(
            TimeLog(
                task_id=None,
                start_time=s.started_at,
                end_time=now,
                duration_seconds=eff,
                kind="pomodoro",
                note=s.state or "自由番茄",
            )
        )
    s.status = "done"
    s.ended_at = now
    s.work_seconds = eff
    s.phase_started_at = None


def settle_round(db: Session, s: FreePomodoro, now: datetime | None = None):
    """番茄轮次结算（幂等）：工作阶段已走满一轮 → 写 TimeLog + rounds+1 + 进休息。

    work_seconds 为累计工作秒（含已结算轮）；结算后把轮内溢出秒并入
    累计（成为新一轮已走秒），保证不丢秒。
    """
    now = now or datetime.now()
    if s.status != "running" or s.phase != "work" or s.mode != "tomato" or s.work_min <= 0:
        return
    eff = _effective_seconds(s, now)
    target = (s.rounds + 1) * s.work_min * 60
    if eff < target:
        return
    db.add(
        TimeLog(
            task_id=None,
            start_time=s.phase_started_at or s.started_at,
            end_time=now,
            duration_seconds=s.work_min * 60,
            kind="pomodoro",
            note=s.state or "自由番茄",
        )
    )
    s.rounds += 1
    s.work_seconds = eff
    s.phase = "break"
    s.phase_started_at = now
    db.commit()
    notify(
        "🍅 自由番茄完成",
        f"「{s.state or '学习'}」完成第 {s.rounds} 个番茄，休息 {s.break_min} 分钟" if s.break_min > 0 else f"「{s.state or '学习'}」完成第 {s.rounds} 个番茄",
    )


def _widget_event(evt: str, session_id: int):
    """桌面悬浮钟回调：round_done / skip_break / rest_done / finish / abandon。"""
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        s = db.get(FreePomodoro, session_id)
        if not s:
            return
        now = datetime.now()
        if evt == "round_done":
            settle_round(db, s, now)
        elif evt == "pause":
            if s.status == "running" and s.phase == "work":
                s.work_seconds = _effective_seconds(s, now)
                s.phase_started_at = None
                s.status = "paused"
                db.commit()
        elif evt == "resume":
            if s.status == "paused":
                s.status = "running"
                s.phase_started_at = now
                db.commit()
        elif evt == "skip_break":
            if s.phase == "break":
                s.phase = "work"
                s.phase_started_at = now
                db.commit()
        elif evt == "rest_done":
            if s.phase == "break":
                s.phase = "work"
                s.phase_started_at = now
                db.commit()
                notify("☕ 休息结束", "开始下一个番茄吧！")
        elif evt == "finish":
            _close_running(db, s, now)
            db.commit()
        elif evt == "abandon":
            s.status = "abandoned"
            s.ended_at = now
            s.phase_started_at = None
            db.commit()
    finally:
        db.close()


@router.post("/start")
def start(data: StartBody, db: Session = Depends(get_db)):
    if data.mode not in ("tomato", "free"):
        raise HTTPException(400, "mode 只能是 tomato 或 free")
    # 互斥：桌面悬浮钟在跑（任务番茄钟/自由番茄钟共用全局唯一悬浮窗）。
    # 注意：pomodoro_widget 已在模块底部模块级 import，此处直接使用；
    # 不可把 raise 包进 try/except Exception（会连 HTTPException 一起吞掉，互斥失效）。
    if pomodoro_widget.is_active():
        raise HTTPException(409, "桌面时钟正在运行，请先完成或放弃当前番茄钟")
    # 互斥：存在未关账的任务番茄计时
    if _running_task_pomodoro(db):
        raise HTTPException(409, "有任务番茄钟正在进行，请先结束它")
    now = datetime.now()
    # 残留的 running/paused session（异常未关闭）先结算保存，保证单实例
    old = _latest(db)
    if old and old.status in ("running", "paused"):
        _close_running(db, old, now)
    s = FreePomodoro(
        state=(data.state or "").strip()[:50],
        mode=data.mode,
        status="running",
        work_min=max(1, data.work_min) if data.mode == "tomato" else 0,
        break_min=max(0, data.break_min),
        phase="work",
        phase_started_at=now,
        started_at=now,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return serialize(s)


@router.get("/state")
def state(db: Session = Depends(get_db)):
    s = _latest(db)
    return {"session": serialize(s, datetime.now())}


@router.post("/pause")
def pause(db: Session = Depends(get_db)):
    s = _latest(db)
    if not s or s.status != "running":
        raise HTTPException(400, "没有正在进行的自由番茄钟")
    if s.phase == "break":
        raise HTTPException(400, "休息中无需暂停")
    now = datetime.now()
    s.work_seconds = _effective_seconds(s, now)
    s.phase_started_at = None
    s.status = "paused"
    db.commit()
    return serialize(s, now)


@router.post("/resume")
def resume(db: Session = Depends(get_db)):
    s = _latest(db)
    if not s or s.status != "paused":
        raise HTTPException(400, "没有已暂停的自由番茄钟")
    now = datetime.now()
    s.status = "running"
    s.phase_started_at = now
    db.commit()
    return serialize(s, now)


@router.post("/settle")
def settle(db: Session = Depends(get_db)):
    """前端页面到点调用：结算当前番茄轮（幂等，调度器/桌面钟也会触发）。"""
    s = _latest(db)
    if s:
        settle_round(db, s, datetime.now())
    return {"ok": True}


@router.post("/skip-break")
def skip_break(db: Session = Depends(get_db)):
    s = _latest(db)
    if not s or s.status != "running":
        raise HTTPException(400, "没有正在进行的自由番茄钟")
    if s.phase != "break":
        raise HTTPException(400, "当前不在休息阶段")
    now = datetime.now()
    s.phase = "work"
    s.phase_started_at = now
    db.commit()
    return serialize(s, now)


@router.post("/finish")
def finish(db: Session = Depends(get_db)):
    s = _latest(db)
    if not s or s.status not in ("running", "paused"):
        raise HTTPException(400, "没有进行中的自由番茄钟")
    now = datetime.now()
    _close_running(db, s, now)
    db.commit()
    return serialize(s, now)


@router.post("/abandon")
def abandon(db: Session = Depends(get_db)):
    s = _latest(db)
    if not s or s.status not in ("running", "paused"):
        raise HTTPException(400, "没有进行中的自由番茄钟")
    now = datetime.now()
    s.status = "abandoned"
    s.ended_at = now
    s.work_seconds = _effective_seconds(s, now)
    s.phase_started_at = None
    db.commit()
    return serialize(s, now)


@router.post("/shutdown")
def shutdown(db: Session = Depends(get_db)):
    """桌面应用退出时调用：保存当前计时并关闭（幂等）。"""
    s = _latest(db)
    if s and s.status in ("running", "paused"):
        _close_running(db, s, datetime.now())
        db.commit()
    return {"ok": True}


@router.get("/history")
def history(days: int = 7, db: Session = Depends(get_db)):
    days = max(1, min(90, days))
    start_dt = datetime.now() - timedelta(days=days)
    logs = (
        db.query(TimeLog)
        .filter(
            TimeLog.task_id.is_(None),
            TimeLog.kind == "pomodoro",
            TimeLog.start_time >= start_dt,
        )
        .order_by(TimeLog.start_time.desc())
        .all()
    )
    groups: dict = {}
    for lg in logs:
        k = lg.note or "自由番茄"
        g = groups.setdefault(k, {"state": k, "count": 0, "seconds": 0})
        g["count"] += 1
        g["seconds"] += lg.duration_seconds or 0
    sessions = (
        db.query(FreePomodoro)
        .filter(FreePomodoro.started_at >= start_dt)
        .order_by(FreePomodoro.started_at.desc())
        .limit(50)
        .all()
    )
    return {
        "groups": sorted(groups.values(), key=lambda g: -g["seconds"]),
        "sessions": [
            {
                "id": s.id,
                "state": s.state or "",
                "mode": s.mode,
                "status": s.status,
                "rounds": s.rounds,
                "work_seconds": _effective_seconds(s, datetime.now()),
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            }
            for s in sessions
        ],
    }


# 注册桌面悬浮钟回调（模块级 import 单向依赖，无循环；坑 #50：不可函数内 import）
from ..services import pomodoro_widget  # noqa: E402

pomodoro_widget.set_free_handler(_widget_event)