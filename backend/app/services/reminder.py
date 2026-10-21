import threading
import time
from datetime import date, datetime, timedelta

from ..database import SessionLocal
from ..models import (
    AttendanceDay,
    AttendanceSegment,
    DailyPaper,
    FreePomodoro,
    Reminder,
    ReminderLog,
    ReminderSendLog,
    Setting,
    Task,
)
from ..routers.attendance import _auto_close, remind_hours
from ..routers.daily_paper import _do_generate
from ..routers.free_pomodoro import settle_round
from ..routers.reminders import current_index, instance_at, parse_advance
from .active_sessions import snapshot_active_pomodoro, touch_last_seen
from .notification import notify
from .task_flow import reactivate_deferred_tasks


def _check_attendance(db):
    """超长在岗提醒：单次在岗超过设置阈值（小时，0=关闭）→ 弹桌面提醒一次。

    只对「今天」仍在计时的段提醒（过去未关闭的段由 _auto_close 收口）；
    同一条段只提醒一次（Setting attendance_reminded_segment 记录段 id）。
    """
    try:
        hours = remind_hours(db)
        now = datetime.now()
        _auto_close(db, now)  # 跨天未关闭段先收口，避免陈旧段参与判断
        if hours <= 0:
            return
        seg = (
            db.query(AttendanceSegment)
            .filter(AttendanceSegment.end_at.is_(None))
            .order_by(AttendanceSegment.id.desc())
            .first()
        )
        if not seg:
            return
        day = db.get(AttendanceDay, seg.day_id)
        if not day or day.date != now.date():
            return
        elapsed = (now - seg.start_at).total_seconds()
        if elapsed < hours * 3600:
            return
        # 去重键含开始时间（微秒）：SQLite 删除最高 id 后新插入会复用该 id，仅按 id 去重会漏提醒
        key = f"{seg.id}:{seg.start_at.isoformat()}"
        last = db.get(Setting, "attendance_reminded_segment")
        if last and last.value == key:
            return
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        notify(
            "⏰ 在岗提醒",
            f"你已连续在岗 {h}小时{m}分。如果已经离开，记得去考勤页点「离开」或修正记录。",
            target="#/attendance",
        )
        if last:
            last.value = key
        else:
            db.add(Setting(key="attendance_reminded_segment", value=key))
        db.commit()
    except Exception as e:
        print(f"[reminder] attendance check failed: {e}")


def _check_free_pomodoro(db):
    """自由番茄钟后台兜底：番茄轮次结算 + 休息结束自动下一轮。

    桌面悬浮钟/页面开着时由它们精确触发，这里 60s 粒度兜底保证
    关掉页面后计时与流转不中断（后端 session 是权威计时源）。
    """
    try:
        s = (
            db.query(FreePomodoro)
            .filter(FreePomodoro.status == "running")
            .order_by(FreePomodoro.id.desc())
            .first()
        )
        if not s:
            return
        now = datetime.now()
        if s.phase == "work":
            settle_round(db, s, now)
        elif s.phase == "break" and s.phase_started_at:
            rest = int((now - s.phase_started_at).total_seconds())
            if rest >= s.break_min * 60:
                s.phase = "work"
                s.phase_started_at = now
                db.commit()
                notify("☕ 休息结束", f"「{s.state or '学习'}」开始下一个番茄吧！")
    except Exception as e:
        print(f"[reminder] free pomodoro check failed: {e}")


def _enabled(db) -> bool:
    s = db.get(Setting, "reminder_enabled")
    return (s.value if s else "true") == "true"


def _notify(title: str, msg: str):
    try:
        from winotify import Notification

        toast = Notification(app_id="研究生工作台", title=title, msg=msg)
        toast.show()
    except Exception as e:
        print(f"[reminder] notify failed: {e}")


def _check_review_reminder(db):
    """按设置的时间点提醒做周复盘（周几 + 几点，同一天只提醒一次）。"""
    try:
        s_day = db.get(Setting, "review_reminder_day")
        s_time = db.get(Setting, "review_reminder_time")
        day = int((s_day.value if s_day else "6") or "6")
        tstr = (s_time.value if s_time else "20:00") or "20:00"
        now = datetime.now()
        # 设置中 0=周一 ... 6=周日，与 datetime.weekday() 一致
        if now.weekday() != day:
            return
        try:
            h, m = map(int, str(tstr).split(":"))
        except Exception:
            return
        if (now.hour, now.minute) != (h, m):
            return
        last = db.get(Setting, "last_review_remind")
        if last and last.value == now.date().isoformat():
            return
        _notify("周复盘提醒", "本周就要结束了，去「周复盘」页做一次总结吧")
        if last:
            last.value = now.date().isoformat()
        else:
            db.add(Setting(key="last_review_remind", value=now.date().isoformat()))
        db.commit()
    except Exception as e:
        print(f"[reminder] review check failed: {e}")


def _generate_repeat_tasks(db):
    """循环任务：今天在 repeat_weekdays 内且今天还没有生成实例 → 复制模板生成（幂等）。"""
    today = date.today()
    templates = (
        db.query(Task)
        .filter(
            Task.repeat_weekdays.isnot(None),
            Task.repeat_weekdays != "",
            Task.status.notin_(["done", "archived", "deferred"]),
        )
        .all()
    )
    for t in templates:
        try:
            wds = {int(x) for x in t.repeat_weekdays.split(",") if x.strip().isdigit()}
        except Exception:
            continue
        if today.weekday() not in wds:
            continue
        exists = (
            db.query(Task)
            .filter(
                Task.repeat_source_id == t.id,
                Task.created_at >= datetime.combine(today, datetime.min.time()),
            )
            .first()
        )
        if exists:
            continue
        nt = Task(
            title=t.title,
            description=t.description,
            task_type=t.task_type,
            priority=t.priority,
            goal_id=t.goal_id,
            tags=t.tags,
            pomodoro_minutes=t.pomodoro_minutes,
            break_minutes=t.break_minutes,
            est_minutes=t.est_minutes,
            due_date=today,
            repeat_weekdays="",
            repeat_source_id=t.id,
        )
        db.add(nt)
        db.commit()


def _check_daily_brief(db):
    """每日晨报：设置的时间点发一次桌面通知，汇总今日待办/顺延/到期任务/本周目标。"""
    try:
        s_on = db.get(Setting, "daily_brief_enabled")
        if (s_on.value if s_on else "false") != "true":
            return
        s_time = db.get(Setting, "daily_brief_time")
        tstr = (s_time.value if s_time else "08:00") or "08:00"
        now = datetime.now()
        try:
            h, m = map(int, str(tstr).split(":"))
        except Exception:
            return
        if (now.hour, now.minute) != (h, m):
            return
        last = db.get(Setting, "last_daily_brief")
        if last and last.value == now.date().isoformat():
            return
        from ..models import DailyItem, Goal

        today = date.today()
        pending = (
            db.query(DailyItem)
            .filter(DailyItem.status == "pending", DailyItem.scheduled_date <= today)
            .count()
        )
        carry = (
            db.query(DailyItem)
            .filter(DailyItem.status == "pending", DailyItem.scheduled_date < today)
            .count()
        )
        due = (
            db.query(Task)
            .filter(Task.due_date == today, Task.status.notin_(["done", "archived", "deferred"]))
            .count()
        )
        wd = db.query(Goal).filter(Goal.level == "week", Goal.status == "active").count()
        _notify(
            "今日简报",
            f"今日待办 {pending} 项（含顺延欠账 {carry}）· 今天到期任务 {due} 项 · 本周目标 {wd} 个",
        )
        if last:
            last.value = now.date().isoformat()
        else:
            db.add(Setting(key="last_daily_brief", value=now.date().isoformat()))
        db.commit()
    except Exception as e:
        print(f"[reminder] daily brief failed: {e}")


def _check_reminders(db):
    """琐事提醒：一次性/每日/每周/每月循环，到点 + 提前提醒（最多 5 次）弹自定义通知。

    去重：每个 (reminder_id, trigger_time) 只发一次（ReminderSendLog）。
    主触发只检查当前实例（宕机恢复不补弹过期主触发），提前触发检查当前与前一实例；
    超过 10 分钟时效的触发点静默记日志不弹窗（过期只标红不补弹）。
    """
    try:
        now = datetime.now()
        reminders = db.query(Reminder).filter(Reminder.status == "pending").all()
        for r in reminders:
            idx = current_index(r, now)
            # 评估当前实例 + 下一实例的触发点（含提前点）：
            # - 一次性提醒主时间未到时也要能评估其提前点（instance_at(none) 恒为 remind_at）；
            # - 周期提醒下一个实例的提前点可能今天/现在就到（如「明天 9 点，提前 1 天」= 今天 9 点）。
            instances = [instance_at(r, idx)]
            if r.repeat != "none":
                instances.append(instance_at(r, idx + 1))
            pts = [(inst, None) for inst in instances]
            for inst in instances:
                for a in parse_advance(r):
                    pts.append((inst - timedelta(minutes=a), a))
            for t, adv in pts:
                if t > now:
                    continue
                if r.last_done_at and t <= r.last_done_at:
                    # 周期提醒「本次已处理」之前的触发点不再补发
                    continue
                exists = (
                    db.query(ReminderSendLog)
                    .filter(ReminderSendLog.reminder_id == r.id, ReminderSendLog.trigger_time == t)
                    .first()
                )
                if exists:
                    continue
                if now - t > timedelta(minutes=10):
                    # 已过时效（宕机恢复/应用关闭期间错过/创建即已过期）：静默记日志不弹窗，
                    # 与「过期只标红不补弹」设计一致——否则打开工作台会补弹一堆历史提醒
                    db.add(ReminderSendLog(reminder_id=r.id, trigger_time=t))
                    db.commit()
                    continue
                if adv:
                    msg = f"「{r.title}」将在 {adv} 分钟后开始（{t:%H:%M} 提醒）"
                else:
                    msg = f"「{r.title}」时间到了，别忘了！"
                notify("⏰ 提醒事项", msg)
                db.add(ReminderSendLog(reminder_id=r.id, trigger_time=t))
                db.commit()
    except Exception as e:
        print(f"[reminder] reminders check failed: {e}")


def _check_daily_paper(db):
    """每日论文兜底：跨天挂机（页面没刷新/没重挂载）时自动生成当天的推荐论文。

    前端懒生成（Today 页挂载）为主触发；这里 60s 粒度兜底保证即使工作台
    一直开着跨天，当天的论文也会生成并弹桌面通知（_do_generate 幂等：
    真正生成才弹一次，当天已有直接返回）。
    """
    try:
        s = db.get(Setting, "daily_paper_enabled")
        if (s.value if s else "true") == "false":
            return
        if db.query(DailyPaper).filter(DailyPaper.paper_date == date.today()).first():
            return
        _do_generate(db)
    except Exception as e:
        print(f"[reminder] daily paper check failed: {e}")


def check_and_remind():
    db = SessionLocal()
    try:
        # 心跳：记录工作台存活时刻，异常退出后启动自愈以此为截止时间
        touch_last_seen(db)
        # 周期快照：悬浮钟工作中 → 刷新退出快照（关机/强杀后也能恢复为已暂停）
        snapshot_active_pomodoro(db)
        # 延后任务到期回归：阶段进入 90 天窗口的 deferred 任务恢复为待办
        reactivate_deferred_tasks(db)
        _generate_repeat_tasks(db)
        _check_free_pomodoro(db)
        _check_attendance(db)
        _check_daily_paper(db)
        if not _enabled(db):
            return
        _check_review_reminder(db)
        _check_daily_brief(db)
        _check_reminders(db)
        today = date.today()
        tasks = (
            db.query(Task)
            .filter(
                Task.due_date.isnot(None),
                Task.status.notin_(["done", "archived", "deferred"]),
            )
            .all()
        )
        levels = [
            (3, "还有 3 天到期"),
            (1, "还有 1 天到期"),
            (0, "今天到期"),
        ]
        for t in tasks:
            days = (t.due_date - today).days
            for level, text in levels:
                if days != level:
                    continue
                exists = (
                    db.query(ReminderLog)
                    .filter(
                        ReminderLog.task_id == t.id,
                        ReminderLog.due_date == t.due_date,
                        ReminderLog.level == level,
                    )
                    .first()
                )
                if exists:
                    continue
                _notify("任务提醒", f"{t.title} {text}")
                db.add(ReminderLog(task_id=t.id, due_date=t.due_date, level=level))
                db.commit()
    except Exception as e:
        print(f"[reminder] check failed: {e}")
    finally:
        db.close()


def start_scheduler():
    def loop():
        while True:
            try:
                check_and_remind()
            except Exception as e:
                print(f"[reminder] loop error: {e}")
            try:
                from .backups import auto_backup

                auto_backup()
            except Exception as e:
                print(f"[reminder] backup error: {e}")
            time.sleep(60)

    t = threading.Thread(target=loop, daemon=True, name="reminder-scheduler")
    t.start()
