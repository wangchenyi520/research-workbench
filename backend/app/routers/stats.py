from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    AttendanceDay,
    AttendanceSegment,
    Checkin,
    DailyItem,
    Experiment,
    Goal,
    LiteratureItem,
    Note,
    Paper,
    Reminder,
    Setting,
    Task,
    TimeLog,
)

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _week_range(ref: date):
    start = ref - timedelta(days=ref.weekday())
    end = start + timedelta(days=6)
    return start, end


def _attendance_range(db: Session, start: date, end: date) -> tuple[int, int]:
    """[start, end] 区间在岗秒数（含进行中段）与有考勤记录的天数。"""
    now = datetime.now()
    segs = (
        db.query(AttendanceSegment)
        .join(AttendanceDay, AttendanceSegment.day_id == AttendanceDay.id)
        .filter(AttendanceDay.date >= start, AttendanceDay.date <= end)
        .all()
    )
    total, day_ids = 0, set()
    for s in segs:
        total += max(0, int(((s.end_at or now) - s.start_at).total_seconds()))
        day_ids.add(s.day_id)
    return total, len(day_ids)


@router.get("/reward-streak")
def reward_streak(db: Session = Depends(get_db)):
    """连续「有产出」天数：完成过清单项或有过计时/番茄记录的日期连续 streak（今天/昨天起算）。

    供「物质奖励提示」使用——连续完成到阈值就值得奖励自己。
    """
    dates: set[date] = set()
    for (d,) in db.query(DailyItem.completed_at).filter(DailyItem.completed_at.isnot(None)).all():
        dates.add(d.date())
    for (st,) in db.query(TimeLog.start_time).all():
        dates.add(st.date())
    today = date.today()
    cursor = today
    if cursor not in dates and (cursor - timedelta(days=1)) in dates:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    s = db.get(Setting, "reward_streak_threshold")
    try:
        threshold = int((s.value if s else "") or 7)
    except ValueError:
        threshold = 7
    return {"streak": streak, "threshold": threshold, "today_done": today in dates}


@router.get("/reading-goal")
def reading_goal(db: Session = Depends(get_db)):
    """阅读计划：本周已读篇数（按 read_date）与每周目标（设置 reading_goal_per_week）。"""
    s = db.get(Setting, "reading_goal_per_week")
    try:
        goal = int((s.value if s else "") or 0)
    except ValueError:
        goal = 0
    monday, _ = _week_range(date.today())
    count = (
        db.query(LiteratureItem)
        .filter(LiteratureItem.read_date.isnot(None), LiteratureItem.read_date >= monday)
        .count()
    )
    return {"count": count, "goal": goal}


@router.get("/week")
def week_summary(db: Session = Depends(get_db)):
    """本周汇总（供周复盘页自动填充）。"""
    start, end = _week_range(date.today())
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())

    done_tasks = (
        db.query(Task)
        .filter(Task.status == "done", Task.completed_at >= start_dt, Task.completed_at < end_dt)
        .order_by(Task.completed_at.desc())
        .all()
    )
    total_seconds = (
        db.query(func.coalesce(func.sum(TimeLog.duration_seconds), 0))
        .filter(TimeLog.start_time >= start_dt, TimeLog.start_time < end_dt)
        .scalar()
    )
    pomodoros = (
        db.query(func.count(TimeLog.id))
        .filter(
            TimeLog.kind == "pomodoro",
            TimeLog.start_time >= start_dt,
            TimeLog.start_time < end_dt,
            TimeLog.end_time.isnot(None),
        )
        .scalar()
    )
    checkin_days = (
        db.query(Checkin.date)
        .filter(Checkin.date >= start, Checkin.date <= end)
        .distinct()
        .count()
    )
    new_notes = (
        db.query(func.count(Note.id))
        .filter(Note.created_at >= start_dt, Note.created_at < end_dt)
        .scalar()
    )
    attendance_seconds, attendance_days = _attendance_range(db, start, end)
    # 本周周目标（level=week，周期与本周重叠或无周期）及其未完成任务，供周复盘带入
    week_goals = []
    for g in db.query(Goal).filter(Goal.level == "week").all():
        ps, pe = g.period_start, g.period_end
        if (ps and pe) and not (ps <= end and pe >= start):
            continue
        undone = [
            {"id": t.id, "title": t.title, "due_date": t.due_date.isoformat() if t.due_date else None}
            for t in g.tasks
            if t.status != "done"
        ]
        week_goals.append({"id": g.id, "title": g.title, "progress": g.progress, "undone_tasks": undone})
    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "done_tasks": [t.title for t in done_tasks],
        "done_count": len(done_tasks),
        "total_seconds": int(total_seconds or 0),
        "pomodoros": int(pomodoros or 0),
        "checkin_days": int(checkin_days or 0),
        "new_notes": int(new_notes or 0),
        "week_goals": week_goals,
        "attendance_seconds": attendance_seconds,
        "attendance_days": attendance_days,
    }


@router.get("/monthly")
def monthly_trend(db: Session = Depends(get_db), days: int = 30):
    """近 N 天每日投入时长趋势。"""
    from_date = date.today() - timedelta(days=days - 1)
    start_dt = datetime.combine(from_date, datetime.min.time())
    rows = (
        db.query(TimeLog.start_time, TimeLog.duration_seconds)
        .filter(TimeLog.start_time >= start_dt)
        .all()
    )
    day_map: dict[str, int] = {}
    for st, dur in rows:
        key = st.date().isoformat()
        day_map[key] = day_map.get(key, 0) + (dur or 0)
    out = []
    for i in range(days):
        d = from_date + timedelta(days=i)
        key = d.isoformat()
        out.append({"date": key, "label": f"{d.month}/{d.day}", "seconds": day_map.get(key, 0)})
    return {"data": out}


@router.get("/distribution")
def task_distribution(db: Session = Depends(get_db), days: int = 30):
    """近 N 天各任务投入时长占比。"""
    from_date = date.today() - timedelta(days=days - 1)
    start_dt = datetime.combine(from_date, datetime.min.time())
    rows = (
        db.query(Task.id, Task.title, func.coalesce(func.sum(TimeLog.duration_seconds), 0))
        .join(TimeLog, TimeLog.task_id == Task.id)
        .filter(TimeLog.start_time >= start_dt, Task.status.notin_(["archived", "deferred"]))  # B8：删除(归档)任务不计入分布
        .group_by(Task.id)
        .order_by(func.sum(TimeLog.duration_seconds).desc())
        .all()
    )
    return [
        {"task_id": tid, "title": title, "seconds": int(sec or 0)}
        for tid, title, sec in rows
    ]


@router.get("/pomodoro")
def pomodoro_stats(db: Session = Depends(get_db), days: int = 30):
    """近 N 天番茄钟统计：每日个数 + 总完成番茄数。"""
    from_date = date.today() - timedelta(days=days - 1)
    start_dt = datetime.combine(from_date, datetime.min.time())
    rows = (
        db.query(TimeLog.start_time)
        .filter(
            TimeLog.kind == "pomodoro",
            TimeLog.start_time >= start_dt,
            TimeLog.end_time.isnot(None),
        )
        .all()
    )
    day_map: dict[str, int] = {}
    for (st,) in rows:
        key = st.date().isoformat()
        day_map[key] = day_map.get(key, 0) + 1
    out = []
    for i in range(days):
        d = from_date + timedelta(days=i)
        out.append({"date": d.isoformat(), "label": f"{d.month}/{d.day}", "count": day_map.get(d.isoformat(), 0)})
    total = sum(x["count"] for x in out)
    avg = round(total / days, 1) if days else 0
    return {"data": out, "total": total, "avg_per_day": avg}


@router.get("/habits")
def habits_stats(db: Session = Depends(get_db)):
    """习惯连续天数 + 成就系统。"""
    from collections import defaultdict

    # 各习惯任务的打卡日期
    task_dates: dict[int, set] = defaultdict(set)
    for task_id, d in db.query(Checkin.task_id, Checkin.date).all():
        task_dates[task_id].add(d)

    habits = []
    for t in db.query(Task).filter(Task.task_type == "habit", Task.status.notin_(["archived", "deferred"])).all():
        dates = sorted(task_dates.get(t.id, set()))
        # 当前连续天数（从今天或昨天往前）
        streak = 0
        cursor = date.today()
        if cursor not in dates and (cursor - timedelta(days=1)) in dates:
            cursor = cursor - timedelta(days=1)
        while cursor in dates:
            streak += 1
            cursor -= timedelta(days=1)
        habits.append({
            "task_id": t.id,
            "title": t.title,
            "streak": streak,
            "total": len(dates),
            "last_date": (max(dates).isoformat() if dates else None),
        })

    # 成就
    total_checkins = db.query(func.count(Checkin.id)).scalar() or 0
    total_pomos = db.query(func.count(TimeLog.id)).filter(TimeLog.kind == "pomodoro", TimeLog.end_time.isnot(None)).scalar() or 0
    total_done = db.query(func.count(Task.id)).filter(Task.status == "done").scalar() or 0
    total_notes = db.query(func.count(Note.id)).scalar() or 0
    max_streak = max((h["streak"] for h in habits), default=0)

    ach_defs = [
        ("首次打卡", "✅", 1, total_checkins, "累计打卡 1 天"),
        ("坚持一周", "🔥", 7, max_streak, "连续打卡 7 天"),
        ("月度坚持", "🏆", 30, max_streak, "连续打卡 30 天"),
        ("习惯达人", "🌟", 100, total_checkins, "累计打卡 100 天"),
        ("专注起步", "🍅", 10, total_pomos, "完成 10 个番茄钟"),
        ("专注达人", "⏱", 100, total_pomos, "完成 100 个番茄钟"),
        ("任务先锋", "🎯", 50, total_done, "完成 50 个任务"),
        ("笔记能手", "📝", 50, total_notes, "写 50 篇笔记"),
    ]
    achievements = [
        {"key": k, "icon": icon, "achieved": progress >= target, "label": label, "progress": progress, "target": target}
        for k, icon, target, progress, label in ach_defs
    ]

    return {"habits": habits, "achievements": achievements}


@router.get("/calendar")
def calendar(month: str = "", db: Session = Depends(get_db)):
    """月历聚合：每天投入/番茄/打卡/DDL任务。month=YYYY-MM。"""
    from collections import defaultdict

    if not month:
        t = date.today()
        month = f"{t.year}-{t.month:02d}"
    try:
        y, m = map(int, month.split("-"))
    except Exception:
        y, m = date.today().year, date.today().month
    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, m + 1, 1)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())

    sec_map = defaultdict(int)
    for st, dur in db.query(TimeLog.start_time, TimeLog.duration_seconds).filter(TimeLog.start_time >= start_dt, TimeLog.start_time < end_dt).all():
        sec_map[st.date().isoformat()] += dur or 0
    pomo_map = defaultdict(int)
    for (st,) in db.query(TimeLog.start_time).filter(TimeLog.kind == "pomodoro", TimeLog.start_time >= start_dt, TimeLog.start_time < end_dt, TimeLog.end_time.isnot(None)).all():
        pomo_map[st.date().isoformat()] += 1
    checkin_map = defaultdict(int)
    for (d,) in db.query(Checkin.date).filter(Checkin.date >= start, Checkin.date < end).all():
        checkin_map[d.isoformat()] += 1

    due_map = defaultdict(list)
    for title, d in db.query(Task.title, Task.due_date).filter(Task.due_date.isnot(None), Task.due_date >= start, Task.due_date < end, Task.status.notin_(["done", "archived", "deferred"])).all():  # B8：归档/延后任务不出现在日历
        due_map[d.isoformat()].append(title)

    remind_map = _reminders_by_day(db, start, end)

    days = (end - start).days
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        key = d.isoformat()
        out.append({
            "date": key,
            "day": d.day,
            "weekday": d.weekday(),
            "seconds": sec_map.get(key, 0),
            "pomodoros": pomo_map.get(key, 0),
            "checkins": checkin_map.get(key, 0),
            "due_tasks": due_map.get(key, []),
            "reminders": remind_map.get(key, []),
        })
    # 补齐首日前的空位（月历起始周）
    first_weekday = start.weekday()
    return {"month": month, "first_weekday": first_weekday, "days": out}


def _reminders_by_day(db: Session, start: date, end: date) -> dict:
    """待提醒事项按天聚合：一次性按 remind_at 日期；周期提醒展开到区间内每个实例日。"""
    from collections import defaultdict
    from .reminders import instance_at

    out = defaultdict(list)
    for r in db.query(Reminder).filter(Reminder.status == "pending").all():
        titles = []
        if r.repeat == "none":
            d = r.remind_at.date()
            if start <= d < end:
                titles.append((d, r.title))
        else:
            n = 0
            while True:
                inst = instance_at(r, n)
                d = inst.date()
                if d >= end:
                    break
                if d >= start:
                    titles.append((d, r.title))
                n += 1
                if n > 4000:  # 防呆（月度区间最多 31 个实例，正常远小于此）
                    break
        for d, t in titles:
            out[d.isoformat()].append(t)
    return out


@router.get("/calendar-week")
def calendar_week(start: str = "", db: Session = Depends(get_db)):
    """周视图聚合：某周（周一起）每天投入/番茄/打卡/DDL任务/当日清单项。start=YYYY-MM-DD（周一）。"""
    from collections import defaultdict

    if not start:
        t = date.today()
        start = (t - timedelta(days=t.weekday())).isoformat()
    try:
        monday = date.fromisoformat(start)
    except ValueError:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD")
    monday = monday - timedelta(days=monday.weekday())  # 归一化到周一
    end = monday + timedelta(days=7)
    start_dt = datetime.combine(monday, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())

    sec_map = defaultdict(int)
    for st, dur in db.query(TimeLog.start_time, TimeLog.duration_seconds).filter(TimeLog.start_time >= start_dt, TimeLog.start_time < end_dt).all():
        sec_map[st.date().isoformat()] += dur or 0
    pomo_map = defaultdict(int)
    for (st,) in db.query(TimeLog.start_time).filter(TimeLog.kind == "pomodoro", TimeLog.start_time >= start_dt, TimeLog.start_time < end_dt, TimeLog.end_time.isnot(None)).all():
        pomo_map[st.date().isoformat()] += 1
    checkin_map = defaultdict(int)
    for (d,) in db.query(Checkin.date).filter(Checkin.date >= monday, Checkin.date < end).all():
        checkin_map[d.isoformat()] += 1
    due_map = defaultdict(list)
    for title, d in db.query(Task.title, Task.due_date).filter(Task.due_date.isnot(None), Task.due_date >= monday, Task.due_date < end, Task.status.notin_(["done", "archived", "deferred"])).all():
        due_map[d.isoformat()].append(title)
    item_map = defaultdict(list)
    for i in db.query(DailyItem).filter(DailyItem.scheduled_date >= monday, DailyItem.scheduled_date < end).all():
        item_map[i.scheduled_date.isoformat()].append(
            {"content": i.content, "time_range": i.time_range, "status": i.status, "kind": i.kind}
        )
    remind_map = _reminders_by_day(db, monday, end)

    days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        key = d.isoformat()
        days.append(
            {
                "date": key,
                "weekday": d.weekday(),
                "seconds": sec_map.get(key, 0),
                "pomodoros": pomo_map.get(key, 0),
                "checkins": checkin_map.get(key, 0),
                "due_tasks": due_map.get(key, []),
                "daily_items": item_map.get(key, []),
                "reminders": remind_map.get(key, []),
            }
        )
    return {"start": monday.isoformat(), "days": days}


@router.get("/compare")
def compare(months: int = 6, db: Session = Depends(get_db)):
    """近 N 个月的投入/完成任务趋势对比。"""
    today = date.today()
    out = []
    for i in range(months - 1, -1, -1):
        # 目标月份
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        start = date(y, m, 1)
        if m == 12:
            end = date(y + 1, 1, 1)
        else:
            end = date(y, m + 1, 1)
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.min.time())
        sec = (
            db.query(func.coalesce(func.sum(TimeLog.duration_seconds), 0))
            .filter(TimeLog.start_time >= start_dt, TimeLog.start_time < end_dt)
            .scalar()
        )
        done = (
            db.query(func.count(Task.id))
            .filter(Task.status == "done", Task.completed_at >= start_dt, Task.completed_at < end_dt)
            .scalar()
        )
        out.append({"month": f"{y}-{m:02d}", "label": f"{y}年{m}月", "seconds": int(sec or 0), "done": int(done or 0)})
    return {"data": out}


@router.get("/goal-progress")
def goal_progress(db: Session = Depends(get_db)):
    """所有目标的进度与状态汇总。"""
    goals = db.query(Goal).all()
    return [
        {
            "id": g.id,
            "title": g.title,
            "level": g.level,
            "progress": g.progress,
            "status": g.status,
            "task_count": sum(1 for t in g.tasks if t.status not in ("archived", "deferred")),
            "done_task_count": sum(1 for t in g.tasks if t.status == "done"),
        }
        for g in goals
    ]


@router.get("/search")
def search(q: str = "", db: Session = Depends(get_db)):
    """全局搜索：任务 / 笔记 / 文献 / 目标。"""
    q = q.strip()
    if not q:
        return {"tasks": [], "notes": [], "literature": [], "goals": []}
    like = f"%{q}%"
    tasks = (
        db.query(Task)
        .filter(Task.status.notin_(["archived", "deferred"]), (Task.title.like(like)) | (Task.description.like(like)))
        .limit(10)
        .all()
    )
    notes = (
        db.query(Note)
        .filter((Note.title.like(like)) | (Note.content.like(like)))
        .limit(10)
        .all()
    )
    lits = (
        db.query(LiteratureItem)
        .filter(
            (LiteratureItem.title.like(like))
            | (LiteratureItem.abstract.like(like))
            | (LiteratureItem.authors.like(like))
        )
        .limit(10)
        .all()
    )
    goals = db.query(Goal).filter(Goal.title.like(like)).limit(10).all()
    return {
        "tasks": [
            {"id": t.id, "title": t.title, "task_type": t.task_type, "status": t.status}
            for t in tasks
        ],
        "notes": [{"id": n.id, "title": n.title, "pinned": n.pinned} for n in notes],
        "literature": [{"id": l.id, "title": l.title} for l in lits],
        "goals": [{"id": g.id, "title": g.title, "level": g.level} for g in goals],
    }


@router.get("/monthly-report")
def monthly_report(month: str = "", db: Session = Depends(get_db)):
    """月度报告：聚合当月科研与学习数据。month 格式 YYYY-MM，默认当月。"""
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    try:
        y, m = map(int, month.split("-"))
    except Exception:
        y, m = date.today().year, date.today().month
    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, m + 1, 1)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())

    done_tasks = (
        db.query(Task)
        .filter(Task.status == "done", Task.completed_at >= start_dt, Task.completed_at < end_dt)
        .order_by(Task.completed_at.desc())
        .all()
    )
    total_seconds = (
        db.query(func.coalesce(func.sum(TimeLog.duration_seconds), 0))
        .filter(TimeLog.start_time >= start_dt, TimeLog.start_time < end_dt)
        .scalar()
    )
    pomodoros = (
        db.query(func.count(TimeLog.id))
        .filter(TimeLog.kind == "pomodoro", TimeLog.start_time >= start_dt, TimeLog.start_time < end_dt, TimeLog.end_time.isnot(None))
        .scalar()
    )
    checkin_days = (
        db.query(Checkin.date).filter(Checkin.date >= start, Checkin.date < end).distinct().count()
    )
    new_notes = db.query(func.count(Note.id)).filter(Note.created_at >= start_dt, Note.created_at < end_dt).scalar()
    new_lits = db.query(func.count(LiteratureItem.id)).filter(LiteratureItem.created_at >= start_dt, LiteratureItem.created_at < end_dt).scalar()
    new_exps = db.query(func.count(Experiment.id)).filter(Experiment.created_at >= start_dt, Experiment.created_at < end_dt).scalar()
    new_papers = db.query(func.count(Paper.id)).filter(Paper.created_at >= start_dt, Paper.created_at < end_dt).scalar()
    attendance_seconds, attendance_days = _attendance_range(db, start, end - timedelta(days=1))

    # 每日投入分布（当月，补全所有日期含0）
    day_rows = (
        db.query(TimeLog.start_time, TimeLog.duration_seconds)
        .filter(TimeLog.start_time >= start_dt, TimeLog.start_time < end_dt)
        .all()
    )
    daily: dict[str, int] = {}
    for st, dur in day_rows:
        key = st.date().isoformat()
        daily[key] = daily.get(key, 0) + (dur or 0)

    # 补全当月每一天（含无数据的日期为 0）
    days_in_month = (end - start).days
    daily_series = []
    for i in range(days_in_month):
        d = start + timedelta(days=i)
        key = d.isoformat()
        daily_series.append({"date": key, "day": d.day, "seconds": daily.get(key, 0)})

    return {
        "month": month,
        "start": start.isoformat(),
        "end": (end - timedelta(days=1)).isoformat(),
        "done_count": len(done_tasks),
        "done_tasks": [t.title for t in done_tasks],
        "total_seconds": int(total_seconds or 0),
        "pomodoros": int(pomodoros or 0),
        "checkin_days": int(checkin_days or 0),
        "new_notes": int(new_notes or 0),
        "new_literature": int(new_lits or 0),
        "new_experiments": int(new_exps or 0),
        "new_papers": int(new_papers or 0),
        "attendance_seconds": attendance_seconds,
        "attendance_days": attendance_days,
        "daily": daily_series,
    }
