"""活动计时的统一收尾与恢复（v2.11）。

桌面托盘「退出」/ 正常关停时调用 suspend_all：把所有进行中的计时自动
暂停/结算保存——工作台未运行期间的时间不计入任何统计：

- 考勤：在岗段自动「离开」（原因「工作台退出」），下次打开需手动「到位」；
- 任务番茄钟（桌面悬浮钟）：存快照并隐藏，下次启动恢复为「已暂停」状态，
  点「继续」接着计时（离线时间不限入）；
- 页面内本地计时（未关账 timelog）：按已流逝时间关账（<60 秒的番茄按 B10 删除）；
- 自由番茄钟：保持现状——结算入账并结束（与 /free-pomodoro/shutdown 一致）。

异常退出（关机 / 杀进程 / 崩溃）来不及调用：调度器每 60s 写 last_seen_at
心跳；下次启动 startup_recovery 以最后心跳为截止时间自愈（未关账计时关账、
在岗段截断到心跳时刻、自由番茄钟结算），误差不超过 1 分钟。
"""

import json
import logging
from datetime import datetime, timedelta

from ..database import SessionLocal
from ..models import (
    AttendanceDay,
    AttendanceSegment,
    DailyItem,
    FreePomodoro,
    Setting,
    TimeLog,
)
from . import pomodoro_widget

log = logging.getLogger("workbench")

LAST_SEEN_KEY = "last_seen_at"       # 调度器心跳：工作台最后一次存活时刻
SNAPSHOT_KEY = "pomodoro_snapshot"   # 任务番茄钟退出快照（恢复用）

EXIT_REASON = "工作台退出"            # 正常退出时考勤的离开原因
HEAL_REASON = "异常退出自动保存"      # 异常退出后启动自愈写入的离开原因


def _set_setting(db, key: str, value: str) -> None:
    s = db.get(Setting, key)
    if s:
        s.value = value
    else:
        db.add(Setting(key=key, value=value))


def touch_last_seen(db, now: datetime | None = None) -> None:
    """记录工作台最后一次存活时刻（调度器每 60s 调用）。"""
    now = now or datetime.now()
    _set_setting(db, LAST_SEEN_KEY, now.isoformat(timespec="seconds"))
    db.commit()


def get_last_seen(db) -> datetime | None:
    s = db.get(Setting, LAST_SEEN_KEY)
    if not s or not s.value:
        return None
    try:
        return datetime.fromisoformat(s.value)
    except (TypeError, ValueError):
        return None


def clear_pomodoro_snapshot(db) -> None:
    """新开桌面悬浮钟时清理旧快照（防止退出未真正发生时的陈旧恢复）。"""
    s = db.get(Setting, SNAPSHOT_KEY)
    if s:
        db.delete(s)
        db.commit()


def _save_snapshot(db, st: dict) -> None:
    snap = {
        "log_id": st.get("log_id"),
        "task_id": st.get("task_id"),
        "title": st.get("title") or "",
        "phase": st.get("phase") or "work",
        "remaining": int(st.get("remaining") or 0),
        "work_total": int(st.get("work_total") or 0),
        "break_total": int(st.get("break_total") or 0),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    _set_setting(db, SNAPSHOT_KEY, json.dumps(snap, ensure_ascii=False))


def _close_log(db, lg: TimeLog, end_dt: datetime) -> bool:
    """按截止时间关账一条未结束的计时（<60 秒的番茄按 B10 删除）。返回是否保留。"""
    if lg.duration_seconds and lg.duration_seconds > 0:
        # 已显式记录过时长的记录（手动补录）不是进行中的计时：
        # 只补结束时间（开始 + 时长），绝不按墙钟重算——否则 25 天的墙钟会变成「610 小时」
        lg.end_time = lg.start_time + timedelta(seconds=lg.duration_seconds)
        return True
    end_dt = max(lg.start_time, end_dt)
    lg.end_time = end_dt
    lg.duration_seconds = max(0, int((end_dt - lg.start_time).total_seconds()))
    if lg.kind == "pomodoro":
        if lg.duration_seconds < 60:
            db.delete(lg)
            return False
        item = (
            db.query(DailyItem)
            .filter(
                DailyItem.kind == "task",
                DailyItem.source_id == lg.task_id,
                DailyItem.status == "pending",
            )
            .first()
        )
        if item:
            item.pomodoros += 1
    return True


def suspend_all(db, now: datetime | None = None) -> dict:
    """工作台退出时统一收尾所有进行中的计时（幂等）。"""
    now = now or datetime.now()
    out = {"attendance": False, "pomodoro_snapshot": False, "free_pomodoro": False, "timelogs": 0}

    # 1) 任务番茄钟：存快照（自由番茄钟 session 由第 4 步结算，不存快照）
    st = pomodoro_widget.public_state()
    protected: set[int] = set()
    if st.get("active") and not st.get("session_id"):
        if st.get("log_id") or st.get("phase") == "break":
            _save_snapshot(db, st)
            out["pomodoro_snapshot"] = True
            if st.get("log_id"):
                protected.add(int(st["log_id"]))
    if st.get("active"):
        pomodoro_widget.control("quit")

    # 2) 考勤：在岗段自动「离开」，离线时间不计入在岗
    for seg in db.query(AttendanceSegment).filter(AttendanceSegment.end_at.is_(None)).all():
        seg.end_at = max(seg.start_at, now)
        seg.leave_reason = EXIT_REASON
        out["attendance"] = True

    # 3) 页面内本地计时：按已流逝时间关账保存（悬浮钟番茄钟除外——待恢复）
    for lg in db.query(TimeLog).filter(TimeLog.end_time.is_(None)).all():
        if lg.id in protected:
            continue
        _close_log(db, lg, now)
        out["timelogs"] += 1

    # 4) 自由番茄钟：结算入账并结束（用户拍板「保持现状」）
    s = (
        db.query(FreePomodoro)
        .filter(FreePomodoro.status.in_(("running", "paused")))
        .order_by(FreePomodoro.id.desc())
        .first()
    )
    if s:
        from ..routers.free_pomodoro import _close_running

        _close_running(db, s, now)
        out["free_pomodoro"] = True

    db.commit()
    touch_last_seen(db, now)
    out["at"] = now.isoformat(timespec="seconds")
    log.info("suspend-active: %s", out)
    return out


def snapshot_active_pomodoro(db) -> bool:
    """调度器周期快照：悬浮钟工作中 → 刷新退出快照。

    关机/强杀来不及调用 suspend_all，进程内存里的剩余时长会丢——每 60s
    落一次盘后，下次启动也能恢复为「已暂停」（误差 ≤60s）。
    """
    st = pomodoro_widget.public_state()
    if st.get("active") and st.get("log_id") and not st.get("session_id"):
        _save_snapshot(db, st)
        db.commit()
        return True
    return False


def restore_pomodoro_snapshot(db) -> int | None:
    """启动时恢复任务番茄钟快照（恢复为「已暂停」）。返回被保护的 log_id。"""
    s = db.get(Setting, SNAPSHOT_KEY)
    if not s or not s.value:
        return None
    raw = s.value
    db.delete(s)
    db.commit()
    try:
        snap = json.loads(raw)
    except (TypeError, ValueError):
        log.warning("pomodoro snapshot 解析失败，已丢弃")
        return None
    log_id = snap.get("log_id")
    phase = snap.get("phase") or "work"
    if log_id:
        lg = db.get(TimeLog, int(log_id))
        if not lg or lg.end_time:
            log.info("pomodoro snapshot 对应的计时已关账，跳过恢复 (log_id=%s)", log_id)
            return None
    elif phase != "break":
        return None
    work_total = int(snap.get("work_total") or 0)
    break_total = int(snap.get("break_total") or 0)
    ok, msg = pomodoro_widget.start(
        snap.get("task_id"),
        int(log_id) if log_id else None,
        snap.get("title") or "",
        max(1, round(work_total / 60)) if work_total else 25,
        max(0, round(break_total / 60)),
        None,
        "tomato",
        0,
        remaining=int(snap.get("remaining") or 0),
        phase=phase,
        paused=True,
    )
    if not ok:
        log.warning("pomodoro snapshot 恢复失败：%s", msg)
        return None
    log.info("已恢复上次暂停的任务番茄钟 (log_id=%s, phase=%s, remaining=%s)", log_id, phase, snap.get("remaining"))
    return int(log_id) if log_id else None


def heal_stale_sessions(db, now: datetime | None = None, protect_log_ids: set[int] | None = None) -> dict:
    """启动自愈：把上次异常退出遗留的进行中计时按最后心跳时刻收尾。"""
    now = now or datetime.now()
    last_seen = get_last_seen(db)
    cutoff = min(now, last_seen) if last_seen else now
    protect = {int(x) for x in (protect_log_ids or [])}
    out = {"attendance": False, "free_pomodoro": False, "timelogs": 0, "cutoff": cutoff.isoformat(timespec="seconds")}

    # 1) 考勤：跨天段先截断到当日 23:59:59，今天的未关闭段截断到心跳时刻
    from ..routers.attendance import _auto_close

    _auto_close(db, now)
    for seg in db.query(AttendanceSegment).filter(AttendanceSegment.end_at.is_(None)).all():
        seg.end_at = max(seg.start_at, cutoff)
        seg.leave_reason = HEAL_REASON
        out["attendance"] = True

    # 2) 自由番茄钟：结算到心跳时刻（离线时间不计入）
    s = db.query(FreePomodoro).filter(FreePomodoro.status == "running").first()
    if s:
        from ..routers.free_pomodoro import _close_running

        _close_running(db, s, cutoff)
        out["free_pomodoro"] = True

    # 3) 未关账的计时记录：关账到心跳时刻
    for lg in db.query(TimeLog).filter(TimeLog.end_time.is_(None)).all():
        if lg.id in protect:
            continue
        _close_log(db, lg, cutoff)
        out["timelogs"] += 1

    db.commit()
    log.info("startup heal: %s", out)
    return out


def startup_recovery(now: datetime | None = None) -> dict:
    """后端启动时调用：恢复番茄钟快照 + 自愈异常退出的残留计时 + 刷新心跳。"""
    now = now or datetime.now()
    db = SessionLocal()
    out = {"restored_log_id": None, "heal": None}
    try:
        protected: set[int] = set()
        log_id = restore_pomodoro_snapshot(db)
        if log_id:
            protected.add(log_id)
            out["restored_log_id"] = log_id
        out["heal"] = heal_stale_sessions(db, now, protect_log_ids=protected)
        touch_last_seen(db, now)
    except Exception as e:
        log.warning("startup recovery failed: %s", e)
    finally:
        db.close()
    return out
