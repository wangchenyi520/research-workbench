"""任务流转：近期可执行判定 + 延后任务到期自动激活（收紧任务定义配套）。

- is_near_term：任务所属阶段已开始或将在 TASK_HORIZON_DAYS 天内开始 → 近期可执行；
  阶段无周期时退化为看任务自身 DDL；两者皆无 → 保留。
- reactivate_deferred_tasks：把 status='deferred'（远期延后）且阶段已临近的任务恢复为待办，
  与归档（archived，回收站语义）严格区分，可安全随阶段推进自动回归任务页。
"""
from datetime import date, timedelta

TASK_HORIZON_DAYS = 90


def is_near_term(period_start: date | None, due_date: date | None, today: date | None = None) -> bool:
    today = today or date.today()
    horizon = today + timedelta(days=TASK_HORIZON_DAYS)
    if period_start:
        return period_start <= horizon
    if due_date:
        return due_date <= horizon
    return True


def reactivate_deferred_tasks(db) -> int:
    """把「延后」任务中阶段已临近（≤ TASK_HORIZON_DAYS 天）的恢复为待办。返回恢复数量。"""
    from ..models import Goal, Task

    today = date.today()
    rows = db.query(Task).filter(Task.status == "deferred").all()
    if not rows:
        return 0
    goals = {g.id: g for g in db.query(Goal).all()}
    n = 0
    for t in rows:
        g = goals.get(t.goal_id) if t.goal_id else None
        ps = g.period_start if g else None
        if is_near_term(ps, t.due_date, today):
            t.status = "todo"
            n += 1
    if n:
        db.commit()
    return n
