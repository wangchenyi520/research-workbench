"""考勤：实验室/工位在岗计时（与学习投入计时完全分离）。

- 状态机：idle（未打卡）→ working（在岗中）→ paused（休息中）→ working …→ closed（今日已结束）。
- 「离开」可记录原因（上课/吃饭/其他/自定义）；暂停时长不计入在岗时长。
- 后端权威计时：基于 attendance_segments 的 start_at / end_at，关页面/关工作台也继续累计。
- 跨天自动收口：未关闭的段若所属日期早于今天，自动截断到当日 23:59:59 并结束当日，
  避免挂机过夜把在岗时长算进今天。
"""

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from ..database import get_db
from ..models import AttendanceDay, AttendanceSegment, Setting

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

DEFAULT_REMIND_HOURS = 12.0
# 修正时间允许的客户端时钟容差：选到「当前分钟」时秒数可能略晚于 now
TIME_TOLERANCE = timedelta(minutes=2)


class LeaveBody(BaseModel):
    reason: str = ""


class SegmentUpdate(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    reason: str | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _reject_tz(cls, v: datetime | None) -> datetime | None:
        # 带时区的时间与库内 naive 时间不可比（曾致 500），直接拒绝
        if v is not None and v.tzinfo is not None:
            raise ValueError("时间不能带时区")
        return v


def remind_hours(db: Session) -> float:
    """超长在岗提醒阈值（小时，0=关闭）；读设置失败/NaN 按默认 12 小时。"""
    s = db.get(Setting, "attendance_remind_hours")
    try:
        v = float((s.value if s else "") or str(DEFAULT_REMIND_HOURS))
        if v != v:  # NaN
            v = DEFAULT_REMIND_HOURS
    except Exception:
        v = DEFAULT_REMIND_HOURS
    return max(0.0, min(48.0, v))


def _auto_close(db: Session, now: datetime) -> None:
    """跨天收口：过去遗留的未关闭段截断到当日 23:59:59 并结束当日。

    另外把过去「最后一段已结束但没点结束今日」的旧日子也视同已收工，
    否则它会被当成「休息中」，开放休息从最后一次离开一直累计到现在，
    污染「本月休息」统计（曾出现 9/16 一天贡献 330 小时的假数据）。
    """
    today = now.date()
    open_segs = db.query(AttendanceSegment).filter(AttendanceSegment.end_at.is_(None)).all()
    changed = False
    for seg in open_segs:
        d = db.get(AttendanceDay, seg.day_id)
        if d and d.date < today:
            end = datetime.combine(d.date, time(23, 59, 59))
            seg.end_at = max(end, seg.start_at)
            seg.auto_closed = True  # 截断时间不准确，标记供前端提示修正
            d.day_closed = True
            d.closed_at = seg.end_at
            changed = True
    stale = (
        db.query(AttendanceDay)
        .filter(AttendanceDay.date < today, AttendanceDay.day_closed.is_(False))
        .all()
    )
    for d in stale:
        segs = _sorted_segs(d)
        if segs and all(s.end_at for s in segs):
            d.day_closed = True
            d.closed_at = segs[-1].end_at
            changed = True
    if changed:
        db.commit()


def _today_day(db: Session, today: date, create: bool = False) -> AttendanceDay | None:
    day = db.query(AttendanceDay).filter(AttendanceDay.date == today).first()
    if day is None and create:
        day = AttendanceDay(date=today)
        db.add(day)
        db.flush()
    return day


def _seg_seconds(seg: AttendanceSegment, now: datetime) -> int:
    end = seg.end_at or now
    return max(0, int((end - seg.start_at).total_seconds()))


def _seg_dict(seg: AttendanceSegment, now: datetime) -> dict:
    return {
        "id": seg.id,
        "start_at": seg.start_at.isoformat(),
        "end_at": seg.end_at.isoformat() if seg.end_at else None,
        "seconds": _seg_seconds(seg, now),
        "reason": seg.leave_reason or "",
        "auto_closed": bool(seg.auto_closed),
    }


def _sorted_segs(day: AttendanceDay | None) -> list[AttendanceSegment]:
    return sorted(day.segments, key=lambda s: s.start_at) if day else []


def _pauses(segs: list[AttendanceSegment]) -> list[dict]:
    """已发生的休息段（相邻两段之间的间隔），reason 取离开段的备注。"""
    out = []
    for cur, nxt in zip(segs, segs[1:]):
        if cur.end_at and nxt.start_at > cur.end_at:
            out.append(
                {
                    "start_at": cur.end_at.isoformat(),
                    "end_at": nxt.start_at.isoformat(),
                    "seconds": int((nxt.start_at - cur.end_at).total_seconds()),
                    "reason": cur.leave_reason or "",
                }
            )
    return out


def _current_pause(segs: list[AttendanceSegment], day: AttendanceDay | None, now: datetime) -> dict | None:
    """当前进行中的休息（最后一次离开后到现在，且当日未结束）。"""
    if not segs or (day and day.day_closed):
        return None
    last = segs[-1]
    if last.end_at and last.end_at <= now:
        return {
            "start_at": last.end_at.isoformat(),
            "seconds": max(0, int((now - last.end_at).total_seconds())),
            "reason": last.leave_reason or "",
        }
    return None


def _serialize_today(db: Session, now: datetime) -> dict:
    today = now.date()
    day = _today_day(db, today)
    segs = _sorted_segs(day)
    open_seg = next((s for s in segs if s.end_at is None), None)
    closed = [s for s in segs if s.end_at]
    pauses = _pauses(segs)
    cur = _current_pause(segs, day, now) if not open_seg else None
    if open_seg:
        status = "working"
    elif not segs:
        status = "idle"
    elif day and day.day_closed:
        status = "closed"
    else:
        status = "paused"
    return {
        "date": today.isoformat(),
        "status": status,
        "today_seconds": sum(_seg_seconds(s, now) for s in segs),
        "first_in": segs[0].start_at.isoformat() if segs else None,
        "last_out": closed[-1].end_at.isoformat() if closed else None,
        "open_since": open_seg.start_at.isoformat() if open_seg else None,
        "day_closed": bool(day.day_closed) if day else False,
        "pause_total_seconds": sum(p["seconds"] for p in pauses) + (cur["seconds"] if cur else 0),
        "current_pause": cur,
        "long_stay_hours": remind_hours(db),
        "segments": [_seg_dict(s, now) for s in segs],
    }


@router.get("/today")
def today(db: Session = Depends(get_db)):
    now = datetime.now()
    _auto_close(db, now)
    return _serialize_today(db, now)


def do_check_in(db: Session, now: datetime) -> None:
    """到位核心逻辑（HTTP 端点与桌面考勤胶囊共用）。已在岗时抛 ValueError。"""
    _auto_close(db, now)
    day = _today_day(db, now.date(), create=True)
    if any(s.end_at is None for s in day.segments):
        raise ValueError("当前已在岗，无需重复到位")
    db.add(AttendanceSegment(day_id=day.id, start_at=now))
    if day.day_closed:
        day.day_closed = False
        day.closed_at = None
    db.commit()


def do_check_out(db: Session, now: datetime, reason: str = "") -> None:
    """离开核心逻辑（HTTP 端点与桌面考勤胶囊共用）。不在岗时抛 ValueError。"""
    _auto_close(db, now)
    day = _today_day(db, now.date())
    seg = next((s for s in (day.segments if day else []) if s.end_at is None), None)
    if not seg:
        raise ValueError("当前不在岗，无法离开")
    seg.end_at = now
    seg.leave_reason = (reason or "").strip()[:20]
    db.commit()


@router.post("/check-in")
def check_in(db: Session = Depends(get_db)):
    """到位：开始/继续今日在岗计时。"""
    now = datetime.now()
    try:
        do_check_in(db, now)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _serialize_today(db, now)


@router.post("/check-out")
def check_out(data: LeaveBody = LeaveBody(), db: Session = Depends(get_db)):
    """离开：结束当前在岗段（可带休息原因），暂停时间不计入在岗时长。"""
    now = datetime.now()
    try:
        do_check_out(db, now, data.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _serialize_today(db, now)


@router.post("/end-day")
def end_day(db: Session = Depends(get_db)):
    """结束今日：关闭当前段并标记当日收工（之后仍可重新「到位」）。"""
    now = datetime.now()
    _auto_close(db, now)
    day = _today_day(db, now.date())
    if not day or not day.segments:
        raise HTTPException(400, "今天还没有开始考勤")
    seg = next((s for s in day.segments if s.end_at is None), None)
    if seg:
        seg.end_at = now
    day.day_closed = True
    day.closed_at = now
    db.commit()
    return _serialize_today(db, now)


@router.put("/segments/{seg_id}")
def update_segment(seg_id: int, data: SegmentUpdate, db: Session = Depends(get_db)):
    """修正某条在岗记录（到岗/离开时间、离开原因）。

    忘记点「离开」时把当前段的结束时间改成实际离开时刻；自动收口
    （跨天截断到 23:59:59）的记录修正后清除标记。校验：不得晚于现在、
    结束晚于开始、不得与同一天其它时间段重叠、时间必须落在当天。
    """
    now = datetime.now()
    seg = db.get(AttendanceSegment, seg_id)
    if not seg:
        raise HTTPException(404, "该考勤记录不存在")
    day = db.get(AttendanceDay, seg.day_id)
    fields = data.model_fields_set
    start_given = "start_at" in fields and data.start_at is not None
    end_given = "end_at" in fields and data.end_at is not None
    time_touched = start_given or end_given
    new_start = data.start_at if start_given else seg.start_at
    new_end = data.end_at if end_given else seg.end_at
    # 只校验「本次传入」的时间：历史零时长段仅改原因、遗留跨天段仅改结束时间时不该被卡死
    if day:
        if start_given and data.start_at.date() != day.date:
            raise HTTPException(400, "开始时间必须在该考勤日当天")
        if end_given and data.end_at.date() != day.date:
            raise HTTPException(400, "结束时间必须在该考勤日当天")
    if start_given and new_start > now + TIME_TOLERANCE:
        raise HTTPException(400, "开始时间不能晚于现在")
    if end_given and new_end is not None and new_end > now + TIME_TOLERANCE:
        raise HTTPException(400, "结束时间不能晚于现在")
    if time_touched and new_end is not None and new_end <= new_start:
        raise HTTPException(400, "结束时间需晚于开始时间")
    if time_touched:
        others = (
            db.query(AttendanceSegment)
            .filter(AttendanceSegment.day_id == seg.day_id, AttendanceSegment.id != seg.id)
            .all()
        )
        new_end_eff = new_end or datetime.max
        for o in others:
            o_end_eff = o.end_at or datetime.max
            if new_start < o_end_eff and o.start_at < new_end_eff:
                raise HTTPException(400, "与同一天已有时间段重叠，请先修正相邻记录")
    if start_given:
        seg.start_at = data.start_at
    if end_given:
        seg.end_at = data.end_at
    if "reason" in fields and data.reason is not None:
        seg.leave_reason = data.reason.strip()[:20]
    seg.auto_closed = False
    try:
        db.commit()
    except StaleDataError:
        # 并发场景：提交前记录已被其它请求删除
        db.rollback()
        raise HTTPException(404, "该考勤记录已不存在（可能刚被删除）")
    return _seg_dict(seg, now)


@router.delete("/segments/{seg_id}")
def delete_segment(seg_id: int, db: Session = Depends(get_db)):
    """删除某条在岗记录（误建/完全无效的时间段）；删除后统计自动重算。"""
    seg = db.get(AttendanceSegment, seg_id)
    if not seg:
        raise HTTPException(404, "该考勤记录不存在")
    try:
        db.delete(seg)
        db.commit()
    except StaleDataError:
        db.rollback()
        raise HTTPException(404, "该考勤记录已不存在（可能刚被删除）")
    return {"ok": True, "deleted": seg_id}


@router.get("/stats")
def stats(days: int = 14, db: Session = Depends(get_db)):
    """统计：近 N 天每日在岗（柱状图）+ 今日/本周/本月累计 + 本月休息原因 + 本月休息时长。"""
    now = datetime.now()
    _auto_close(db, now)
    today = now.date()
    days = max(1, min(365, days))
    start = today - timedelta(days=days - 1)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    q_start = min(start, week_start, month_start)
    rows = db.query(AttendanceDay).filter(AttendanceDay.date >= q_start).all()
    by_date = {d.date: d for d in rows}

    def day_seconds(d: AttendanceDay | None) -> int:
        return sum(_seg_seconds(s, now) for s in d.segments) if d else 0

    series = []
    for i in range(days):
        dt = start + timedelta(days=i)
        d = by_date.get(dt)
        series.append(
            {
                "date": dt.isoformat(),
                "seconds": day_seconds(d),
                "segments": len(d.segments) if d else 0,
                "closed": bool(d.day_closed) if d else False,
            }
        )

    week_seconds = sum(day_seconds(d) for dt, d in by_date.items() if dt >= week_start)
    month_seconds = sum(day_seconds(d) for dt, d in by_date.items() if dt >= month_start)
    month_days = sum(1 for dt, d in by_date.items() if dt >= month_start and d.segments)

    month_pause = 0
    reasons: dict[str, dict] = {}
    for dt, d in by_date.items():
        if dt < month_start:
            continue
        segs = _sorted_segs(d)
        for p in _pauses(segs):
            month_pause += p["seconds"]
            if p["reason"]:
                g = reasons.setdefault(p["reason"], {"reason": p["reason"], "seconds": 0, "count": 0})
                g["seconds"] += p["seconds"]
                g["count"] += 1
        if dt == today:
            cur = _current_pause(segs, d, now)
            if cur:
                month_pause += cur["seconds"]

    return {
        "days": days,
        "series": series,
        "today_seconds": day_seconds(by_date.get(today)),
        "week_seconds": week_seconds,
        "month_seconds": month_seconds,
        "month_days": month_days,
        "month_pause_seconds": month_pause,
        "pause_reasons": sorted(reasons.values(), key=lambda x: -x["seconds"]),
    }


@router.get("/history")
def history(days: int = 30, db: Session = Depends(get_db)):
    """历史：每天签到/离开时间、在岗时长、休息次数/时长（倒序）。"""
    now = datetime.now()
    _auto_close(db, now)
    today = now.date()
    days = max(1, min(365, days))
    start = today - timedelta(days=days - 1)
    rows = (
        db.query(AttendanceDay)
        .filter(AttendanceDay.date >= start)
        .order_by(AttendanceDay.date.desc())
        .all()
    )
    items = []
    for d in rows:
        segs = _sorted_segs(d)
        if not segs:
            continue
        open_seg = next((s for s in segs if s.end_at is None), None)
        closed = [s for s in segs if s.end_at]
        pauses = _pauses(segs)
        if open_seg:
            status = "working"
        elif d.day_closed:
            status = "closed"
        else:
            status = "paused"
        items.append(
            {
                "date": d.date.isoformat(),
                "first_in": segs[0].start_at.isoformat(),
                "last_out": closed[-1].end_at.isoformat() if closed else None,
                "seconds": sum(_seg_seconds(s, now) for s in segs),
                "pause_seconds": sum(p["seconds"] for p in pauses),
                "pause_count": len(pauses),
                "status": status,
                "reasons": [p["reason"] for p in pauses if p["reason"]],
                "auto_closed": any(s.auto_closed for s in segs),
                "segments": [_seg_dict(s, now) for s in segs],
            }
        )
    return {"items": items}
