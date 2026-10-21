from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import pomodoro_widget
from ..services.active_sessions import clear_pomodoro_snapshot

router = APIRouter(prefix="/api/pomodoro", tags=["pomodoro"])


class WidgetStart(BaseModel):
    task_id: int | None = None
    log_id: int | None = None
    title: str = ""
    work_min: int = 25
    break_min: int = 5
    session_id: int | None = None  # 自由番茄钟 session（不绑定任务）
    mode: str = "tomato"  # tomato 倒计时 / free 秒表累计
    elapsed_init: int = 0  # free 秒表接管前已有秒数（时间不倒退）
    remaining: int | None = None  # 打开桌面时钟时的剩余秒（不传=满钟）
    phase: str = "work"  # 打开桌面时钟时同步当前阶段（work/break）
    paused: bool = False  # 页面已暂停时以暂停态打开（不自动继续计时）


class WidgetCmd(BaseModel):
    action: str  # pause / resume / complete / abandon / topmost / close
    value: bool | None = None


@router.post("/widget/start")
def widget_start(data: WidgetStart, db: Session = Depends(get_db)):
    # 新会话开始 → 丢弃可能残留的退出快照（防止陈旧恢复）
    clear_pomodoro_snapshot(db)
    ok, msg = pomodoro_widget.start(
        data.task_id, data.log_id, data.title,
        max(0, min(180, data.work_min)),  # free 模式 work_min=0 合法（秒表无倒计时）
        max(0, min(60, data.break_min)),
        data.session_id,
        data.mode,
        data.elapsed_init,
        data.remaining,
        data.phase,
        data.paused,
    )
    if not ok:
        raise HTTPException(409, msg)
    return {"ok": True, "msg": msg}


@router.get("/widget/state")
def widget_state():
    return pomodoro_widget.public_state()


@router.post("/widget/control")
def widget_control(data: WidgetCmd):
    ok, msg = pomodoro_widget.control(data.action, data.value)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True}
