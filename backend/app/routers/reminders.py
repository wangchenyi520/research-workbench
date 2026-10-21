"""琐事提醒：一次性/每日/每周/每月循环 + 多次提前提醒（最多 5 次）。"""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Reminder
from ..schemas import ReminderCreate, ReminderUpdate

router = APIRouter(prefix="/api/reminders", tags=["reminders"])

REPEAT_LABEL = {"none": "一次性", "daily": "每天", "weekly": "每周", "monthly": "每月"}


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (datetime(year, month + 1, 1) - timedelta(days=1)).day


def _add_months(dt: datetime, n: int) -> datetime:
    """月份进位，日超限取月末（如 1/31 +1月 → 2/28）。"""
    m = dt.month - 1 + n
    year = dt.year + m // 12
    month = m % 12 + 1
    day = min(dt.day, _days_in_month(year, month))
    return dt.replace(year=year, month=month, day=day)


def instance_at(r: Reminder, n: int) -> datetime:
    """第 n 个循环实例（n>=0；none 只有 0）。"""
    if r.repeat == "daily":
        return r.remind_at + timedelta(days=n)
    if r.repeat == "weekly":
        return r.remind_at + timedelta(weeks=n)
    if r.repeat == "monthly":
        return _add_months(r.remind_at, n)
    return r.remind_at


def current_index(r: Reminder, now: datetime) -> int:
    """最大的 n 使 instance_at(n) <= now（none 返回 0）。"""
    if r.repeat == "none":
        return 0
    if r.repeat == "daily":
        return max(0, (now - r.remind_at).days)
    if r.repeat == "weekly":
        return max(0, (now - r.remind_at).days // 7)
    # monthly：先按月差估算再收敛（月末 clamp 最多差 1 天）
    n = (now.year - r.remind_at.year) * 12 + (now.month - r.remind_at.month)
    n = max(0, n)
    while n > 0 and instance_at(r, n) > now:
        n -= 1
    while instance_at(r, n + 1) <= now:
        n += 1
    return n


def parse_advance(r: Reminder) -> list[int]:
    try:
        v = json.loads(r.advance_minutes or "[]")
        return [int(x) for x in v if isinstance(x, (int, float, str)) and int(x) > 0][:5]
    except Exception:
        return []


def serialize(r: Reminder, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    idx = current_index(r, now)
    last_instance = instance_at(r, idx)
    # 过期：一次性=提醒时刻已过；周期=最近一次实例已到但还没处理（last_done_at 早于该实例）
    if r.status != "pending":
        overdue = False
    elif r.repeat == "none":
        overdue = last_instance < now
    else:
        overdue = last_instance <= now and (
            (r.last_done_at is None) or (r.last_done_at < last_instance)
        )
    return {
        "id": r.id,
        "title": r.title,
        "remind_at": r.remind_at.isoformat(),
        "repeat": r.repeat,
        "repeat_label": REPEAT_LABEL.get(r.repeat, r.repeat),
        "advance_minutes": parse_advance(r),
        "note": r.note,
        "status": r.status,
        "overdue": overdue,
        "last_done_at": r.last_done_at.isoformat() if r.last_done_at else None,
        "next_trigger": None if r.status != "pending" else instance_at(r, idx + 1).isoformat(),
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat(),
    }


@router.get("")
def list_reminders(db: Session = Depends(get_db), scope: str = "all"):
    """scope: all / pending / done（pending 按提醒时间倒序，done 按完成时间倒序）。"""
    now = datetime.now()
    q = db.query(Reminder)
    if scope == "pending":
        q = q.filter(Reminder.status == "pending").order_by(Reminder.remind_at)
    elif scope == "done":
        q = q.filter(Reminder.status == "done").order_by(Reminder.completed_at.desc())
    else:
        q = q.order_by(
            Reminder.status == "done",  # pending 在前
            Reminder.remind_at,
        )
    items = [serialize(r, now) for r in q.all()]
    if scope == "all":
        # 过期置顶（同 pending 内按 remind_at 正序，过期自然在前）
        items.sort(key=lambda x: (x["status"] == "done", not x["overdue"], x["remind_at"]))
    return {
        "items": items,
        "stats": {
            "pending": sum(1 for x in items if x["status"] == "pending"),
            "today": sum(
                1
                for x in items
                if x["status"] == "pending" and x["remind_at"][:10] == now.date().isoformat()
            ),
            "overdue": sum(1 for x in items if x["overdue"]),
            "done": sum(1 for x in items if x["status"] == "done"),
        },
    }


@router.post("")
def create_reminder(data: ReminderCreate, db: Session = Depends(get_db)):
    r = Reminder(
        title=data.title.strip(),
        remind_at=data.remind_at.replace(second=0, microsecond=0),
        repeat=data.repeat if data.repeat in ("none", "daily", "weekly", "monthly") else "none",
        advance_minutes=json.dumps(data.advance_minutes),
        note=data.note,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return serialize(r)


@router.put("/{rid}")
def update_reminder(rid: int, data: ReminderUpdate, db: Session = Depends(get_db)):
    r = db.get(Reminder, rid)
    if not r:
        raise HTTPException(404, "提醒不存在")
    upd = data.model_dump(exclude_unset=True)
    if "title" in upd and upd["title"] is not None:
        r.title = upd["title"].strip()
    if "remind_at" in upd and upd["remind_at"] is not None:
        r.remind_at = upd["remind_at"].replace(second=0, microsecond=0)
    if "repeat" in upd and upd["repeat"] in ("none", "daily", "weekly", "monthly"):
        r.repeat = upd["repeat"]
    if "advance_minutes" in upd and upd["advance_minutes"] is not None:
        r.advance_minutes = json.dumps([int(x) for x in upd["advance_minutes"] if int(x) > 0][:5])
    if "note" in upd and upd["note"] is not None:
        r.note = upd["note"]
    if "status" in upd:
        if upd["status"] == "done" and r.status != "done":
            r.status = "done"
            r.completed_at = datetime.now()
        elif upd["status"] == "pending" and r.status == "done":
            r.status = "pending"
            r.completed_at = None
    db.commit()
    db.refresh(r)
    return serialize(r)


@router.post("/{rid}/done")
def done_reminder(rid: int, db: Session = Depends(get_db)):
    """完成提醒：一次性→归档；周期提醒→只标记本次已处理（下周/月继续提醒）。"""
    r = db.get(Reminder, rid)
    if not r:
        raise HTTPException(404, "提醒不存在")
    now = datetime.now()
    if r.repeat == "none":
        r.status = "done"
        r.completed_at = now
    else:
        r.last_done_at = now
        r.status = "pending"
    db.commit()
    db.refresh(r)
    return serialize(r)


@router.delete("/{rid}")
def delete_reminder(rid: int, db: Session = Depends(get_db)):
    r = db.get(Reminder, rid)
    if not r:
        raise HTTPException(404, "提醒不存在")
    db.delete(r)
    db.commit()
    return {"ok": True}