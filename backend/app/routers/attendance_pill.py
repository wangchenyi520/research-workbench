from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import attendance_pill

router = APIRouter(prefix="/api/attendance-pill", tags=["attendance-pill"])


class PillCmd(BaseModel):
    action: str  # hide / show / topmost(bool)
    value: bool | None = None


@router.post("/start")
def pill_start():
    """显示桌面考勤胶囊（恢复上次位置）。"""
    ok, msg = attendance_pill.PILL.start()
    if not ok:
        raise HTTPException(409, msg)
    return {"ok": True, "msg": msg}


@router.get("/state")
def pill_state():
    return attendance_pill.PILL.public_state()


@router.post("/control")
def pill_control(data: PillCmd):
    ok, msg = attendance_pill.PILL.control(data.action, data.value)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True}
