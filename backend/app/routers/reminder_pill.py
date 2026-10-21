from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import reminder_pill

router = APIRouter(prefix="/api/reminder-pill", tags=["reminder-pill"])


class PillCmd(BaseModel):
    action: str  # hide / show / topmost(bool)
    value: bool | None = None


@router.post("/start")
def pill_start():
    """显示桌面提醒胶囊（恢复上次位置）。"""
    ok, msg = reminder_pill.PILL.start()
    if not ok:
        raise HTTPException(409, msg)
    return {"ok": True, "msg": msg}


@router.get("/state")
def pill_state():
    return reminder_pill.PILL.public_state()


@router.post("/control")
def pill_control(data: PillCmd):
    ok, msg = reminder_pill.PILL.control(data.action, data.value)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True}
