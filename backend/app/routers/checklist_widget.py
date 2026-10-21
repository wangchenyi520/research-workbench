from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import checklist_widget

router = APIRouter(prefix="/api/checklist-widget", tags=["checklist-widget"])


class WidgetCmd(BaseModel):
    action: str  # hide / topmost
    value: bool | None = None


@router.post("/start")
def widget_start():
    """显示桌面悬浮清单（恢复上次位置/大小/置顶）。"""
    ok, msg = checklist_widget.start()
    if not ok:
        raise HTTPException(409, msg)
    return {"ok": True, "msg": msg}


@router.get("/state")
def widget_state():
    return checklist_widget.public_state()


@router.post("/control")
def widget_control(data: WidgetCmd):
    ok, msg = checklist_widget.control(data.action, data.value)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True}
