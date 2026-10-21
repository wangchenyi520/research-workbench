"""今日清单共享操作层（HTTP 路由与桌面悬浮清单共用，保证两边行为完全一致）。

从 routers/daily.py 抽出的核心逻辑：两套圆环体系的权重归一、清单项完成/取消
（含任务联动与目标进度）、快速添加、悬浮清单数据读取。
"""

from datetime import date, datetime

from ..models import DailyItem


def _split_rings(db, today):
    """把清单项按「今日 / 顺延」两套体系分类（详见「五.17」）。

    返回 (today_done, today_pending, carry_done, carry_pending)。
    """
    today_done, today_pending = [], []
    carry_done, carry_pending = [], []
    rows = db.query(DailyItem).all()
    for i in rows:
        if i.status == "done":
            if i.completed_at and i.completed_at.date() > i.scheduled_date:
                carry_done.append(i)
            elif i.scheduled_date == today:
                today_done.append(i)
        elif i.status == "pending":
            if i.scheduled_date < today:
                carry_pending.append(i)
            elif i.scheduled_date == today:
                today_pending.append(i)
    return today_done, today_pending, carry_done, carry_pending


def renorm_pending(db, fixed_id=None, fixed_weight=None):
    """两套体系各自归一，保证各自「已完成权重 + 剩余权重」恒 = 100。"""
    today = date.today()
    today_done, today_pending, carry_done, carry_pending = _split_rings(db, today)

    fixed = None
    if fixed_id is not None:
        fixed = next((i for i in (today_pending + carry_pending) if i.id == fixed_id), None)
        if fixed and fixed_weight is not None:
            fixed.weight = max(1, min(99, int(fixed_weight or 0)))

    def _norm(done_items, pending_items):
        done_w = sum(i.weight for i in done_items)
        has_fixed = any(i.id == fixed_id for i in pending_items)
        fixed_w = fixed.weight if (fixed and has_fixed) else 0
        target = max(0, 100 - done_w - fixed_w)
        others = [i for i in pending_items if i.id != fixed_id]
        if not others:
            if pending_items and not has_fixed:
                pending_items[0].weight = target  # 单任务体系：权重即占全部
            return
        total = sum(i.weight for i in others)
        if total <= 0 or target <= 0:
            for i in others:
                i.weight = 1
            return
        scaled = [int(i.weight / total * target) for i in others]
        diff = target - sum(scaled)
        frac = sorted(((i.weight / total * target - scaled[k], k) for k, i in enumerate(others)), reverse=True)
        for k in range(abs(diff)):
            idx = frac[k % len(frac)][1]
            scaled[idx] += 1 if diff > 0 else -1
        for i, s in zip(others, scaled):
            i.weight = max(1, s)

    _norm(today_done, today_pending)
    _norm(carry_done, carry_pending)
    db.commit()


def sync_goal_progress(db, goal_id):
    """按目标下任务完成比例刷新目标进度。"""
    if not goal_id:
        return
    from ..models import Goal, Task

    g = db.get(Goal, goal_id)
    if not g:
        return
    goal_tasks = db.query(Task).filter(Task.goal_id == goal_id).all()
    if goal_tasks:
        dcount = sum(1 for t in goal_tasks if t.status == "done")
        g.progress = round(dcount / len(goal_tasks) * 100, 1)


def apply_item_status(db, item: DailyItem, status: str, today: date | None = None) -> bool:
    """设置清单项状态（done/pending）并联动任务/文献。

    与今日页勾选走同一逻辑：勾选完成一次性/学习任务 → 任务完成 + 目标进度更新；
    取消勾选 → 仅恢复「清单侧勾选联动」标成 done 的任务（auto_done_at 来源标记）。
    """
    if status not in ("pending", "done"):
        return False
    if today is None:
        today = date.today()
    was_auto_done = item.auto_done_at is not None  # 取消勾选前先读旧来源标记
    item.status = status
    item.completed_at = datetime.now() if status == "done" else None
    item.auto_done_at = None
    # 用户勾选/取消过 = 认领该条（AI 自动落地的项重新生成时不再被平替/撤下）
    item.auto_landed = False
    if item.kind == "task" and item.source_id:
        from ..models import Task

        task = db.get(Task, item.source_id)
        if task and task.status not in ("archived", "deferred"):
            if status == "done":
                # once 与 study 都联动
                if task.task_type in ("once", "study") and task.status != "done":
                    task.status = "done"
                    task.completed_at = datetime.now()
                sync_goal_progress(db, task.goal_id)
            else:
                restored_today = task.completed_at is not None and task.completed_at.date() == today
                if (
                    not was_auto_done
                    and task.task_type in ("once", "study")
                    and task.status == "done"
                    and restored_today
                ):
                    task.status = "todo"
                    task.completed_at = None
                sync_goal_progress(db, task.goal_id)
    elif item.kind == "literature" and item.source_id:
        from ..models import LiteratureItem

        lit = db.get(LiteratureItem, item.source_id)
        if lit and status == "done" and lit.read_status != "read":
            lit.read_status = "read"
    return True


def set_item_status(db, item_id: int, status: str) -> bool:
    """按 id 设置清单项状态（悬浮清单勾选/取消用），含权重归一。"""
    item = db.get(DailyItem, item_id)
    if not item:
        return False
    if not apply_item_status(db, item, status):
        return False
    db.commit()
    renorm_pending(db)
    db.refresh(item)
    return True


def quick_add(db, content: str) -> DailyItem | None:
    """悬浮清单内快速添加：手动项、四象限默认「重要紧急」、权重 10、计划日=今天。"""
    content = (content or "").strip()
    if not content:
        return None
    item = DailyItem(
        content=content,
        kind="manual",
        scheduled_date=date.today(),
        quadrant="important_urgent",
        weight=10,
        status="pending",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    renorm_pending(db)
    db.refresh(item)
    return item


def fetch_checklist(db):
    """悬浮清单数据：未完成（含顺延）+ 今日已完成。

    返回 {"pending": [{id, content}], "done": [{id, content}]}。
    """
    today = date.today()
    pending = (
        db.query(DailyItem)
        .filter(DailyItem.status == "pending", DailyItem.scheduled_date <= today)
        .order_by(DailyItem.due_date, DailyItem.created_at)
        .all()
    )
    done = (
        db.query(DailyItem)
        .filter(DailyItem.status == "done", DailyItem.completed_at >= datetime.combine(today, datetime.min.time()))
        .order_by(DailyItem.completed_at)
        .all()
    )
    return {
        "pending": [{"id": i.id, "content": i.content} for i in pending],
        "done": [{"id": i.id, "content": i.content} for i in done],
    }
