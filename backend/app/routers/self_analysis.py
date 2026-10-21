"""Self_analysis 联动路由。

- GET  /overview        计划结构化总览 + 工作台实时进度（作战计划页）
- GET/POST /weight      体重记录（生活数据）
- POST /import          一键导入（里程碑/周目标三主线/技能栈/逐日清单/提醒习惯），支持 dry_run 预览
- GET  /sync-preview    攒批回写：改动清单（勾选/字段/删除/新增/进度表）
- POST /sync            执行回写（写前自动备份；行级合并冲突跳过并报告）
- POST /export-review   周复盘导出到 plan/复盘/第X周.md（dry_run 预览；05 模板约定位置）

安全约束：所有写文件操作先备份到 data/sa_backups/；行级合并（找不到对应行即跳过）；
前端必须双重确认后才调用 /sync 与 /export-review。
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import DATA_DIR
from ..database import get_db
from ..models import (
    AttendanceSegment,
    Checkin,
    DailyItem,
    Goal,
    LiteratureItem,
    Milestone,
    OJSolve,
    Paper,
    Reminder,
    Review,
    SelfSyncLink,
    Setting,
    Skill,
    SkillStage,
    Task,
    TimeLog,
    WeightRecord,
)
from ..services import self_analysis as sa

router = APIRouter(prefix="/api/self-analysis", tags=["self-analysis"])


# ---------------------------------------------------------------- 基础
def _root(db: Session) -> Path | None:
    s = db.get(Setting, "self_analysis_path")
    path = (s.value if s else "") or ""
    if not path:
        return None
    p = Path(path)
    return p if p.exists() else None


def _require_root(db: Session) -> Path:
    root = _root(db)
    if not root:
        raise HTTPException(400, "未配置 Self_analysis 文件夹路径，或路径不存在（到设置页填写）")
    return root


def _backup_dir() -> Path:
    d = DATA_DIR / "sa_backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_file(root: Path, rel: str) -> str:
    src = root / rel
    if not src.exists():
        return ""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = _backup_dir()
    dst = d / f"{ts}_{Path(rel).name}"
    if dst.exists():  # 同一秒内二次写入：加微秒防覆盖上一份备份
        dst = d / f"{ts}_{datetime.now().strftime('%f')}_{Path(rel).name}"
    shutil.copy2(src, dst)
    # 同名文件最多保留最近 50 份（按时间戳命名，字典序即时间序）
    try:
        same = sorted(d.glob(f"*_{Path(rel).name}"), key=lambda p: p.name)
        for old in same[:-50]:
            old.unlink(missing_ok=True)
    except OSError:
        pass
    return str(dst)


def _find_named(root: Path, prefix: str) -> Path | None:
    for f in sa.scan(root):
        if f.name.startswith(prefix):
            return f
    return None


_INLINE_DATE_RE = re.compile(r"^\d{1,2}\.\d{1,2}[（(][^）)]*[）)]?[：:]\s*")


def _norm_line(s: str) -> str:
    s = str(s or "").strip()
    s = re.sub(r"^-\s*\[[ xX]\]\s*", "", s)
    s = re.sub(r"^-\s+", "", s)
    s = s.replace("**", "")
    s = _INLINE_DATE_RE.sub("", s)
    return re.sub(r"\s+", "", s)


def _target_line(item: DailyItem, current: str | None = None) -> str:
    """由清单项生成目标行（保留原行的行内日期前缀，避免丢信息）。"""
    prefix = ""
    if current:
        m = re.match(r"^-\s*\[[ xX]\]\s*(\d{1,2}\.\d{1,2}[（(][^）)]*[）)]?[：:]\s*)", current)
        if m:
            prefix = m.group(1)
    box = "x" if item.status == "done" else " "
    return f"- [{box}] {prefix}{item.content}"


def _toggle_line(cur: str, done: bool) -> str:
    """只切换 checkbox（保留原行其余内容，含加粗/链接/前缀）。"""
    box = "x" if done else " "
    if re.match(r"^-\s*\[[ xX]\]", cur):
        return re.sub(r"^(-\s*)\[[ xX]\]", lambda m: m.group(1) + f"[{box}]", cur, count=1)
    return f"- [{box}] {cur.lstrip('- ').strip()}"


def _find_line(lines: list[str], link: SelfSyncLink) -> int | None:
    start, end = 0, len(lines)
    if link.section:
        sec = link.section.lstrip("#").strip()
        for i, l in enumerate(lines):
            if l.lstrip("#").strip() == sec:
                start = i + 1
                break
        for j in range(start, len(lines)):
            if lines[j].startswith("#"):
                end = j
                break
    snap = _norm_line(link.line_text)
    for i in range(start, end):
        if _norm_line(lines[i]) == snap:
            return i
    return None


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []


# ---------------------------------------------------------------- 工作台任务块（任务 ↔ 06 文档双向）
TASK_BLOCK_START = "<!-- WB:TASKS:START -->"
TASK_BLOCK_END = "<!-- WB:TASKS:END -->"
TASK_BLOCK_SECTION = "工作台任务（自动同步）"
TASK_BLOCK_HEADING = f"## {TASK_BLOCK_SECTION}"
TASK_BLOCK_FILE_PREFIX = "06"
TASK_ACTIVE_STATUSES = ("todo", "doing", "done")


def _goal_titles(db: Session) -> dict[int, str]:
    return {g.id: g.title for g in db.query(Goal).all()}


def _task_line(t: Task, goal_title: str = "") -> str:
    """由任务生成块内行：`- [ ] 标题 ｜ 阶段 · 截止 YYYY-MM-DD`（元信息仅展示用）。"""
    meta = []
    if goal_title:
        meta.append(goal_title)
    if t.due_date:
        meta.append(f"截止 {t.due_date.isoformat()}")
    suffix = (" ｜ " + " · ".join(meta)) if meta else ""
    box = "x" if t.status == "done" else " "
    return f"- [{box}] {t.title}{suffix}"


def _line_done(line: str) -> bool:
    return bool(re.match(r"^-\s*\[[xX]\]", str(line or "").strip()))


def _line_title(line: str) -> str:
    s = re.sub(r"^-\s*\[[ xX]\]\s*", "", str(line or "").strip())
    s = s.split("｜")[0]
    return s.replace("**", "").strip()


def _norm_title(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "").replace("**", ""))


def _task_block_text(task_lines: list[str]) -> str:
    body = "\n".join(task_lines)
    return f"{TASK_BLOCK_START}\n{TASK_BLOCK_HEADING}\n\n{body}\n{TASK_BLOCK_END}"


def _task_candidates(db: Session) -> list[Task]:
    """进入任务块的任务：非习惯、非归档/延后的任务页任务（todo/doing/done）。"""
    return (
        db.query(Task)
        .filter(Task.status.in_(list(TASK_ACTIVE_STATUSES)), Task.task_type != "habit")
        .order_by(Task.created_at, Task.id)
        .all()
    )


# ---------------------------------------------------------------- 实时统计（作战计划页 / 进度块共用）
def _live_stats(db: Session) -> dict:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    week_dt = datetime.combine(monday, time.min)

    out: dict = {}

    skills = db.query(Skill).all()
    out["skills"] = []
    for s in skills:
        total = round(sum(x.progress for x in s.stages) / len(s.stages)) if s.stages else 0
        out["skills"].append({
            "id": s.id, "name": s.name, "progress": total,
            "stages": [{"name": x.name, "progress": x.progress} for x in s.stages],
        })

    solves = db.query(OJSolve).all()
    ac = len({p for p in (x.problem_id for x in solves if x.kind == "solve")})
    dates = {x.date for x in solves}
    streak = 0
    d = today
    if d not in dates:
        d = d - timedelta(days=1)
    while d in dates:
        streak += 1
        d -= timedelta(days=1)
    out["oj"] = {"ac": ac, "streak": streak, "week": sum(1 for x in solves if x.date >= monday)}

    papers = db.query(Paper).order_by(Paper.id.desc()).limit(10).all()
    out["papers"] = [{"id": p.id, "title": p.title, "status": p.status, "venue": p.venue} for p in papers]

    out["literature"] = {
        "read_week": db.query(LiteratureItem).filter(
            LiteratureItem.read_date.isnot(None), LiteratureItem.read_date >= monday
        ).count(),
        "reading": db.query(LiteratureItem).filter(LiteratureItem.read_status == "reading").count(),
        "total": db.query(LiteratureItem).count(),
    }

    logs = db.query(TimeLog).filter(TimeLog.start_time >= week_dt, TimeLog.duration_seconds > 0).all()
    out["week"] = {
        "focus_seconds": sum(l.duration_seconds or 0 for l in logs),
        "pomodoros": sum(1 for l in logs if l.kind == "pomodoro"),
        "tasks_done": db.query(Task).filter(
            Task.status == "done", Task.completed_at.isnot(None), Task.completed_at >= week_dt
        ).count(),
    }

    segs = db.query(AttendanceSegment).filter(AttendanceSegment.start_at >= week_dt).all()
    out["attendance_seconds"] = sum(
        max(0, int(((s.end_at or datetime.now()) - s.start_at).total_seconds())) for s in segs
    )

    wr = db.query(WeightRecord).order_by(WeightRecord.date.desc()).limit(14).all()
    out["weight"] = {
        "latest": ({"date": wr[0].date.isoformat(), "weight": wr[0].weight} if wr else None),
        "records": [{"date": r.date.isoformat(), "weight": r.weight} for r in reversed(wr)],
    }

    mss = db.query(Milestone).all()
    out["milestones"] = [
        {"id": m.id, "title": m.title, "due_date": m.due_date.isoformat() if m.due_date else None,
         "completed": m.completed}
        for m in sorted(mss, key=lambda x: (x.due_date or date.max))
    ]

    goals = db.query(Goal).all()
    out["goals"] = [
        {"id": g.id, "title": g.title, "level": g.level, "status": g.status,
         "progress": g.progress, "parent_id": g.parent_id,
         "period_start": g.period_start.isoformat() if g.period_start else None,
         "period_end": g.period_end.isoformat() if g.period_end else None}
        for g in goals
    ]

    # 连续有产出天数（完成过清单项 / 有计时的日期）
    dset = set()
    for (c,) in db.query(DailyItem.completed_at).filter(DailyItem.completed_at.isnot(None)).all():
        dset.add(c.date())
    for (t,) in db.query(TimeLog.start_time).filter(TimeLog.duration_seconds > 0).all():
        dset.add(t.date())
    rstreak = 0
    d = today
    if d not in dset:
        d = d - timedelta(days=1)
    while d in dset:
        rstreak += 1
        d -= timedelta(days=1)
    out["reward_streak"] = rstreak
    out["today_output"] = today in dset
    return out


def _fmt_dur(sec: int) -> str:
    sec = max(0, int(sec or 0))
    h, m = sec // 3600, (sec % 3600) // 60
    if h:
        return f"{h} 小时 {m} 分钟"
    return f"{m} 分钟"


# ---------------------------------------------------------------- 总览
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    root = _root(db)
    data: dict = {"configured": bool(root), "root": str(root) if root else "", "empty": True}
    if root:
        try:
            data.update(sa.load(root))
        except Exception as e:  # 解析失败不致命，页面仍可用
            data["error"] = f"解析失败：{e}"
    data["live"] = _live_stats(db)
    return data


# ---------------------------------------------------------------- 体重
@router.get("/weight")
def get_weight(days: int = 30, db: Session = Depends(get_db)):
    days = max(1, min(365, int(days or 30)))
    rows = db.query(WeightRecord).order_by(WeightRecord.date.desc()).limit(days).all()
    rows = list(reversed(rows))
    latest = rows[-1] if rows else None
    return {
        "records": [{"date": r.date.isoformat(), "weight": r.weight, "note": r.note} for r in rows],
        "latest": ({"date": latest.date.isoformat(), "weight": latest.weight} if latest else None),
    }


@router.post("/weight")
def add_weight(data: dict, db: Session = Depends(get_db)):
    try:
        w = round(float(data.get("weight") or 0), 1)
    except (TypeError, ValueError):
        raise HTTPException(400, "体重格式不正确")
    if not (20 <= w <= 500):
        raise HTTPException(400, "体重数值超出合理范围（20-500 斤）")
    try:
        d = date.fromisoformat(str(data.get("date") or date.today().isoformat()))
    except ValueError:
        raise HTTPException(400, "日期格式不正确")
    note = str(data.get("note") or "").strip()[:100]
    row = db.query(WeightRecord).filter(WeightRecord.date == d).first()
    if row:
        row.weight = w
        row.note = note
    else:
        db.add(WeightRecord(date=d, weight=w, note=note))
    db.commit()
    return {"ok": True, "date": d.isoformat(), "weight": w}


# ---------------------------------------------------------------- 一键导入
def _plan_import(db: Session, d: dict, parts: list[str], include_past: bool, apply: bool) -> dict:
    today = date.today()
    result: dict = {}
    checks = d.get("checkpoints", [])
    weeks = d.get("weeks", [])
    lines = d.get("lines", [])
    phases = d.get("phases", [])
    today_str = d.get("today", today.isoformat())

    # 学期起止（用于总目标 period）
    starts = [p["start"] for p in phases if p.get("start")]
    ends = [p["end"] for p in phases if p.get("end")]
    sem_start = min(starts).isoformat() if starts else today_str
    sem_end = max(ends).isoformat() if ends else (checks[-1]["date"].isoformat() if checks and checks[-1].get("date") else "")

    if "milestones" in parts:
        created, skipped = [], []
        for i, ck in enumerate(checks):
            title = f"{ck['id']}｜{ck['content']}"
            exists = db.query(Milestone).filter(Milestone.title == title).first()
            if exists:
                skipped.append(title)
                continue
            created.append({"title": title, "due_date": ck["date"].isoformat() if ck.get("date") else None})
            if apply:
                db.add(Milestone(title=title, due_date=ck.get("date"), color="#7C6CF0", sort_order=i))
        result["milestones"] = {"created": created, "skipped": skipped, "count": len(created)}

    if "goals" in parts:
        created, skipped = [], []
        semester = db.query(Goal).filter(Goal.title.like("研一上学期%")).first()
        if not semester:
            created.append({"title": f"研一上学期（{sem_start} ~ {sem_end}）", "note": "学期总目标"})
            if apply:
                semester = Goal(
                    title=f"研一上学期（{sem_start} ~ {sem_end}）", level="annual", status="active",
                    period_start=date.fromisoformat(sem_start),
                    period_end=date.fromisoformat(sem_end) if sem_end else None,
                    description="由 Self_analysis 作战计划导入：第一篇论文投稿 + 技术栈 + 期末",
                )
                db.add(semester)
                db.flush()
        # 三主线（quarter 级，挂学期目标）
        line_goals = []
        for ln in lines:
            title = ln["name"]
            g = db.query(Goal).filter(Goal.title == title).first()
            if g:
                skipped.append(title)
                line_goals.append(g)
                continue
            created.append({"title": title, "note": ln.get("desc", "")})
            if apply:
                g = Goal(title=title, level="quarter", status="active", description=ln.get("desc", ""),
                         parent_id=semester.id if semester else None,
                         period_start=date.fromisoformat(sem_start),
                         period_end=date.fromisoformat(sem_end) if sem_end else None)
                db.add(g)
                db.flush()
            line_goals.append(g)
        # 周目标（week 级，挂学期目标）
        for w in weeks:
            title = f"第{w['n']}周｜{w.get('range', '')}"
            g = db.query(Goal).filter(Goal.title == title).first()
            if g:
                skipped.append(title)
                continue
            created.append({"title": title, "note": f"论文线：{w.get('paper', '')}；技术线：{w.get('tech', '')}"})
            if apply:
                db.add(Goal(
                    title=title, level="week", status="active",
                    description=f"论文线：{w.get('paper', '')}\n技术线：{w.get('tech', '')}",
                    parent_id=semester.id if semester else None,
                    period_start=w.get("start"), period_end=w.get("end"),
                ))
        result["goals"] = {"created": created, "skipped": skipped, "count": len(created)}

    if "skills" in parts:
        specs = sa.parse_skill_specs(Path(d["root"])) if d.get("root") else []
        created, skipped = [], []
        for spec in specs:
            s = db.query(Skill).filter(Skill.name == spec["name"]).first()
            if s:
                skipped.append(spec["name"])
                continue
            created.append({"name": spec["name"], "stages": spec["stages"]})
            if apply:
                s = Skill(name=spec["name"], description=spec.get("source", ""))
                db.add(s)
                db.flush()
                for i, st in enumerate(spec["stages"]):
                    db.add(SkillStage(skill_id=s.id, name=st, order=i,
                                      progress=int((spec.get("initial") or {}).get(st, 0))))
        result["skills"] = {"created": created, "skipped": skipped, "count": len(created)}

    if "daily" in parts:
        tasks = sa.parse_daily_tasks(Path(d["root"]), today) if d.get("root") else []
        created, skipped = [], []
        for t in tasks:
            if t["date"] < today and not include_past:
                skipped.append({"content": t["content"], "date": t["date"].isoformat(), "reason": "日期已过（未勾选包含）"})
                continue
            exists = db.query(DailyItem).filter(
                DailyItem.content == t["content"], DailyItem.scheduled_date == t["date"]
            ).first()
            if exists:
                skipped.append({"content": t["content"], "date": t["date"].isoformat(), "reason": "已存在"})
                continue
            created.append({"content": t["content"], "date": t["date"].isoformat(),
                            "checked": t["checked"], "time_range": t.get("time_range", "")})
            if apply:
                item = DailyItem(
                    content=t["content"], kind="manual", scheduled_date=t["date"],
                    quadrant="important_not", weight=10,
                    time_range=t.get("time_range", ""),
                    status="done" if t["checked"] else "pending",
                    completed_at=datetime.combine(t["date"], time(12, 0)) if t["checked"] else None,
                )
                db.add(item)
                db.flush()
                db.add(SelfSyncLink(file=t["file"], section=t["section"], line_text=t["line"],
                                    entity="daily_item", entity_id=item.id))
        result["daily"] = {"created": created, "skipped": skipped, "count": len(created)}

    if "life" in parts:
        created, skipped = [], []
        # 健身习惯
        habit_title = "健身房锻炼（每周3-4次）"
        h = db.query(Task).filter(Task.title == habit_title).first()
        if h:
            skipped.append(habit_title)
        else:
            created.append({"title": habit_title, "note": "习惯打卡（每周3-4次）"})
            if apply:
                db.add(Task(title=habit_title, task_type="habit", status="todo"))
        # 周五导师周报提醒
        rem_title = "发导师周报（模板见 Self_analysis 05）"
        r = db.query(Reminder).filter(Reminder.title == rem_title).first()
        if r:
            skipped.append(rem_title)
        else:
            created.append({"title": rem_title, "note": "每周五 17:00 周期提醒"})
            if apply:
                days = (4 - today.weekday()) % 7  # 周五=4
                next_fri = today + timedelta(days=days)
                db.add(Reminder(
                    title=rem_title, repeat="weekly",
                    remind_at=datetime.combine(next_fri, time(17, 0)),
                    advance_minutes="[30]", note="内容：文献阅读+技术进展+课题想法+下周计划",
                ))
        result["life"] = {"created": created, "skipped": skipped, "count": len(created)}

    if apply:
        db.commit()
    return result


@router.post("/import")
def import_plan(data: dict | None = None, db: Session = Depends(get_db)):
    root = _require_root(db)
    body = data or {}
    parts = body.get("parts") or ["milestones", "goals", "skills", "daily", "life"]
    parts = [p for p in parts if p in ("milestones", "goals", "skills", "daily", "life")]
    if not parts:
        raise HTTPException(400, "未选择要导入的内容")
    apply = bool(body.get("apply"))
    include_past = bool(body.get("include_past"))
    try:
        d = sa.load(root)
    except Exception as e:
        raise HTTPException(500, f"解析 Self_analysis 失败：{e}")
    if d.get("empty"):
        raise HTTPException(400, "文件夹为空，没有可导入的内容")
    d["root"] = str(root)
    result = _plan_import(db, d, parts, include_past, apply)
    totals = {"created": 0, "skipped": 0}
    for v in result.values():
        totals["created"] += len(v.get("created", []))
        totals["skipped"] += len(v.get("skipped", []))
    return {"applied": apply, "parts": result, "totals": totals}


# ---------------------------------------------------------------- 进度块（00 回写）
def _progress_block(db: Session, d: dict) -> str:
    live = _live_stats(db)
    today = date.today()
    lines = [
        "<!-- WB:PROGRESS:START -->",
        f"> 以下「当前真实进度」由工作台自动同步（{today}）",
        "",
        "| 项目 | 状态 | 差距 |",
        "|---|---|---|",
    ]
    for s in live["skills"]:
        gap = "已完成" if s["progress"] >= 100 else "推进中"
        lines.append(f"| {s['name']} | {s['progress']}% | {gap} |")
    oj = live["oj"]
    lines.append(f"| LeetCode | 已 AC {oj['ac']} 题 | 研一上目标 60 题，还差 {max(0, 60 - oj['ac'])} 题 |")
    if live["papers"]:
        for p in live["papers"][:2]:
            lines.append(f"| 论文《{p['title']}》 | {p['status']} | — |")
    lit = live["literature"]
    lines.append(f"| 文献阅读 | 本周 {lit['read_week']} 篇（在读 {lit['reading']} 篇） | — |")
    w = live["week"]
    lines.append(f"| 本周投入 | {_fmt_dur(w['focus_seconds'])}（番茄 {w['pomodoros']} 个） | — |")
    wt = live["weight"]["latest"]
    if wt:
        lines.append(f"| 体重 | {wt['weight']} 斤（{wt['date']}） | — |")
    lines.append("<!-- WB:PROGRESS:END -->")
    return "\n".join(lines)


def _apply_progress(text: str, block: str) -> str:
    if "<!-- WB:PROGRESS:START -->" in text and "<!-- WB:PROGRESS:END -->" in text:
        return re.sub(
            r"<!-- WB:PROGRESS:START -->.*?<!-- WB:PROGRESS:END -->", block, text, flags=re.S
        )
    m = re.search(r"^##.*当前真实进度.*$", text, re.M)
    if m:
        return text[: m.end()] + "\n\n" + block + text[m.end():]
    return text.rstrip() + "\n\n" + block + "\n"


def _progress_change(db: Session, root: Path, d: dict) -> dict | None:
    pf = _find_named(root, "00")
    if not pf:
        return None
    text = pf.read_text(encoding="utf-8", errors="ignore")
    block = _progress_block(db, d)
    rel = str(pf.relative_to(root)).replace("\\", "/")
    cur = re.search(r"<!-- WB:PROGRESS:START -->.*?<!-- WB:PROGRESS:END -->", text, re.S)
    if cur:
        if cur.group(0).strip() == block.strip():
            return None
        return {"key": "progress", "kind": "progress", "file": rel, "title": "当前真实进度（自动同步）",
                "before": cur.group(0), "after": block}
    return {"key": "progress", "kind": "progress", "file": rel, "title": "当前真实进度（首次插入自动同步块）",
            "before": "（首次：将在「当前真实进度」标题下插入自动同步块，原手写表格保留）", "after": block}


# ---------------------------------------------------------------- 攒批回写
def _compute_sync(db: Session) -> dict:
    root = _require_root(db)
    try:
        d = sa.load(root)
    except Exception as e:
        raise HTTPException(500, f"解析 Self_analysis 失败：{e}")
    d["root"] = str(root)
    today = date.today()

    links = db.query(SelfSyncLink).all()
    # 每日清单回写只处理 daily_item 关联；task 关联走下方「工作台任务块」独立链路
    daily_links = [l for l in links if l.entity != "task"]
    cache: dict[str, list[str]] = {}
    changes: list[dict] = []
    skipped: list[dict] = []

    def lines_of(rel: str) -> list[str] | None:
        if rel not in cache:
            p = root / rel
            if not p.exists():
                return None
            cache[rel] = _read_lines(p)
        return cache[rel]

    for link in daily_links:
        lines = lines_of(link.file)
        if lines is None:
            skipped.append({"file": link.file, "title": link.line_text, "reason": "文件不存在"})
            continue
        idx = _find_line(lines, link)
        if idx is None:
            skipped.append({"file": link.file, "title": link.line_text, "reason": "找不到对应行（可能已手动修改）"})
            continue
        item = db.get(DailyItem, link.entity_id)
        cur = lines[idx]
        if item is None:
            changes.append({
                "key": f"{link.file}:{link.id}", "link_id": link.id, "entity_id": link.entity_id,
                "kind": "delete", "file": link.file, "section": link.section, "line_no": idx,
                "title": _norm_line(cur) or link.line_text, "before": cur, "after": None,
            })
            continue
        target = _target_line(item, cur)
        tgt_norm = _norm_line(target)
        cur_norm = _norm_line(cur)
        if tgt_norm == cur_norm:
            # 文本一致：仅勾选状态可能不同
            cur_done = bool(re.match(r"^-\s*\[[xX]\]", cur.strip()))
            tgt_done = item.status == "done"
            if cur_done != tgt_done and re.match(r"^-\s*\[[ xX]\]", cur.strip()):
                changes.append({
                    "key": f"{link.file}:{link.id}", "link_id": link.id, "entity_id": item.id,
                    "kind": "check", "file": link.file, "section": link.section, "line_no": idx,
                    "title": item.content, "before": cur, "after": _toggle_line(cur, tgt_done),
                })
            continue
        changes.append({
            "key": f"{link.file}:{link.id}", "link_id": link.id, "entity_id": item.id,
            "kind": "update", "file": link.file, "section": link.section, "line_no": idx,
            "title": item.content, "before": cur, "after": target,
        })

    # 新增追加：今天起 7 天内、未关联、非 AI 自动落地的清单项，若其日期存在小节 → 追加
    f02 = _find_named(root, "02")
    if f02:
        rel02 = str(f02.relative_to(root)).replace("\\", "/")
        text02 = f02.read_text(encoding="utf-8", errors="ignore")
        sections = sa._date_headings(text02, today)
        linked_ids = {l.entity_id for l in daily_links}
        file_contents = {_norm_line(l.strip()) for l in text02.splitlines() if l.strip().startswith("-")}
        candidates = (
            db.query(DailyItem)
            .filter(
                DailyItem.scheduled_date >= today,
                DailyItem.scheduled_date <= today + timedelta(days=7),
                DailyItem.kind != "ai",
                DailyItem.auto_landed.is_(False),
            )
            .all()
        )
        for item in candidates:
            if item.id in linked_ids:
                continue
            sec = None
            for s in sections:
                if s["first"] <= item.scheduled_date <= s["last"]:
                    sec = s
                    break
            if not sec:
                continue
            if _norm_line(item.content) in file_contents:
                continue
            new_line = _target_line(item)
            changes.append({
                "key": f"{rel02}:new:{item.id}", "entity_id": item.id, "kind": "append",
                "file": rel02, "section": sec["heading"], "line_no": None,
                "title": item.content, "before": None, "after": new_line,
            })

    # ---- 工作台任务块双向同步（任务页 ↔ 06 文档「工作台任务」块） ----
    # 规则：任务块由工作台维护；md 手改（勾选/标题）→ 回写工作台（文档为权威）；
    # md 未改 → 工作台变化写回（勾选/字段/删除/新增）；归档/延后/习惯任务不进入任务块。
    f06 = _find_named(root, TASK_BLOCK_FILE_PREFIX)
    if f06:
        rel06 = str(f06.relative_to(root)).replace("\\", "/")
        lines06 = lines_of(rel06)
        if lines06 is None:
            skipped.append({"file": rel06, "title": "工作台任务块", "reason": "06 文档读取失败"})
        else:
            gmap = _goal_titles(db)
            cand = _task_candidates(db)
            task_links = {l.entity_id: l for l in links if l.entity == "task"}
            start_i = next((i for i, l in enumerate(lines06) if l.strip() == TASK_BLOCK_START), None)
            end_i = next((i for i, l in enumerate(lines06) if l.strip() == TASK_BLOCK_END), None)

            def _block_idx(link: SelfSyncLink) -> int | None:
                idx = _find_line(lines06, link)
                if idx is None and link.line_no is not None and start_i is not None and end_i is not None:
                    # 行号兜底：md 手改过文字（勾选/标题）导致归一化匹配不中
                    if start_i < link.line_no < end_i and link.line_no < len(lines06):
                        idx = link.line_no
                return idx

            if start_i is None or end_i is None:
                if cand:
                    tlines = [_task_line(t, gmap.get(t.goal_id, "")) for t in cand]
                    changes.append({
                        "key": f"{rel06}:tasks:block", "kind": "task_block_create",
                        "file": rel06, "section": TASK_BLOCK_SECTION, "line_no": None,
                        "title": f"工作台任务（首次在 {Path(rel06).name} 创建同步块，{len(cand)} 项）",
                        "before": f"（首次：将在「{Path(rel06).name}」末尾插入「{TASK_BLOCK_SECTION}」块）",
                        "after": _task_block_text(tlines),
                        "lines": [{"entity_id": t.id, "line": ln} for t, ln in zip(cand, tlines)],
                    })
            else:
                handled: set[int] = set()
                for t in cand:
                    link = task_links.get(t.id)
                    if link is None:
                        continue
                    idx = _block_idx(link)
                    if idx is None or not (start_i < idx < end_i) or not re.match(r"^-\s*\[[ xX]\]", lines06[idx].strip()):
                        skipped.append({"file": link.file, "title": link.line_text,
                                        "reason": "任务块内找不到对应行（可能已手动删除或大幅改动）"})
                        continue
                    handled.add(t.id)
                    cur = lines06[idx]
                    base = link.line_text or ""
                    if _norm_line(cur) != _norm_line(base):
                        # md 被手改 → 文档为权威，同步回工作台
                        base_done, cur_done = _line_done(base), _line_done(cur)
                        base_title, cur_title = _line_title(base), _line_title(cur)
                        if cur_done != base_done or _norm_title(cur_title) != _norm_title(base_title):
                            acts = []
                            if cur_done != base_done:
                                acts.append("标记完成" if cur_done else "恢复待办")
                            if _norm_title(cur_title) != _norm_title(base_title):
                                acts.append(f"改名为「{cur_title}」")
                            changes.append({
                                "key": f"{link.file}:{link.id}", "link_id": link.id, "entity_id": t.id,
                                "kind": "task_md", "file": link.file, "section": link.section, "line_no": idx,
                                "title": t.title, "before": cur, "after": f"（工作台任务将{'、'.join(acts)}）",
                                "md_line": cur,
                            })
                        else:
                            # 仅元信息被改 → 用工作台规范行覆盖回 md
                            changes.append({
                                "key": f"{link.file}:{link.id}", "link_id": link.id, "entity_id": t.id,
                                "kind": "task_update", "file": link.file, "section": link.section, "line_no": idx,
                                "title": t.title, "before": cur, "after": _task_line(t, gmap.get(t.goal_id, "")),
                            })
                        continue
                    # md 未变 → 工作台变化写回
                    target = _task_line(t, gmap.get(t.goal_id, ""))
                    if _norm_line(target) != _norm_line(cur):
                        changes.append({
                            "key": f"{link.file}:{link.id}", "link_id": link.id, "entity_id": t.id,
                            "kind": "task_update", "file": link.file, "section": link.section, "line_no": idx,
                            "title": t.title, "before": cur, "after": target,
                        })
                    elif _line_done(target) != _line_done(cur):
                        changes.append({
                            "key": f"{link.file}:{link.id}", "link_id": link.id, "entity_id": t.id,
                            "kind": "task_check", "file": link.file, "section": link.section, "line_no": idx,
                            "title": t.title, "before": cur,
                            "after": _toggle_line(cur, t.status == "done"),
                        })

                # 链接失效（任务被删除/归档/延后/改为习惯）→ 删除块内行
                for tid, link in task_links.items():
                    t = db.get(Task, tid)
                    if t is not None and t.status in TASK_ACTIVE_STATUSES and t.task_type != "habit":
                        continue
                    idx = _block_idx(link)
                    if idx is None or not (start_i < idx < end_i):
                        skipped.append({"file": link.file, "title": link.line_text,
                                        "reason": "任务块内找不到对应行（可能已手动删除）"})
                        continue
                    changes.append({
                        "key": f"{link.file}:{link.id}", "link_id": link.id, "entity_id": tid,
                        "kind": "task_delete", "file": link.file, "section": link.section, "line_no": idx,
                        "title": getattr(t, "title", "") or link.line_text, "before": lines06[idx], "after": None,
                    })

                # 未关联任务 → 追加到任务块末尾
                block_norm = {_norm_line(x) for x in lines06[start_i:end_i + 1]}
                for t in cand:
                    if t.id in task_links or t.id in handled:
                        continue
                    line = _task_line(t, gmap.get(t.goal_id, ""))
                    if _norm_line(line) in block_norm:
                        continue
                    changes.append({
                        "key": f"{rel06}:task:new:{t.id}", "entity_id": t.id, "kind": "task_append",
                        "file": rel06, "section": TASK_BLOCK_SECTION, "line_no": None,
                        "title": t.title, "before": None, "after": line,
                    })

    pc = _progress_change(db, root, d)
    if pc:
        changes.append(pc)

    return {"root": str(root), "changes": changes, "skipped": skipped}


@router.get("/sync-preview")
def sync_preview(db: Session = Depends(get_db)):
    return _compute_sync(db)


@router.post("/sync")
def sync_apply(data: dict | None = None, db: Session = Depends(get_db)):
    root = _require_root(db)
    exclude = set((data or {}).get("exclude") or [])
    preview = _compute_sync(db)
    changes = [c for c in preview["changes"] if c["key"] not in exclude]
    if not changes:
        return {"applied": 0, "skipped": preview["skipped"], "backups": [], "changed_files": []}

    by_file: dict[str, list[dict]] = {}
    for c in changes:
        by_file.setdefault(c["file"], []).append(c)

    applied: list[dict] = []
    skipped: list[dict] = list(preview["skipped"])
    backups: list[str] = []
    changed_files: list[str] = []

    for rel, ops in by_file.items():
        fpath = root / rel
        if not fpath.exists():
            skipped.extend({**c, "reason": "文件不存在"} for c in ops)
            continue
        file_mod = [c for c in ops if c["kind"] != "task_md"]
        text = fpath.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()

        if file_mod:
            bk = _backup_file(root, rel)
            if bk:
                backups.append(bk)

            # 先处理行级操作（从下往上避免索引漂移）
            line_ops = sorted(
                [c for c in file_mod if c["kind"] in ("check", "update", "delete", "task_check", "task_update", "task_delete")],
                key=lambda x: x["line_no"], reverse=True,
            )
            for c in line_ops:
                idx = c["line_no"]
                if idx >= len(lines) or _norm_line(lines[idx]) != _norm_line(c["before"]):
                    skipped.append({**c, "reason": "写入时该行内容已变化，已跳过"})
                    continue
                if c["kind"] in ("delete", "task_delete"):
                    del lines[idx]
                else:
                    lines[idx] = c["after"]
                applied.append(c)

            # 再处理清单追加（插入到小节末尾）
            for c in [x for x in file_mod if x["kind"] == "append"]:
                sec = c["section"]
                insert_at = None
                for i, l in enumerate(lines):
                    if l.lstrip("#").strip() == sec.lstrip("#").strip() or sec in l:
                        insert_at = i + 1
                        break
                if insert_at is None:
                    skipped.append({**c, "reason": "找不到对应小节，已跳过"})
                    continue
                while insert_at < len(lines) and lines[insert_at].strip() and not lines[insert_at].startswith("#"):
                    insert_at += 1
                lines.insert(insert_at, c["after"])
                applied.append(c)

            # 任务追加：插入到任务块末尾（END 标记前）
            for c in [x for x in file_mod if x["kind"] == "task_append"]:
                end_idx = next((i for i, l in enumerate(lines) if l.strip() == TASK_BLOCK_END), None)
                if end_idx is None:
                    skipped.append({**c, "reason": "找不到任务块结束标记，已跳过"})
                    continue
                insert_at = end_idx
                while insert_at > 0 and not lines[insert_at - 1].strip():
                    insert_at -= 1
                lines.insert(insert_at, c["after"])
                applied.append(c)
            # 多次插入会让先前位置偏移，按内容重新定位
            for c in [x for x in file_mod if x["kind"] == "task_append"]:
                if c in applied:
                    c["inserted_at"] = next(
                        (i for i, l in enumerate(lines) if _norm_line(l) == _norm_line(c["after"])),
                        c.get("inserted_at"),
                    )

            # 任务块首次创建：整体追加到文件末尾
            for c in [x for x in file_mod if x["kind"] == "task_block_create"]:
                if any(l.strip() == TASK_BLOCK_START for l in lines):
                    skipped.append({**c, "reason": "任务块已存在，已跳过"})
                    continue
                joined = "\n".join(lines).rstrip() + "\n\n" + c["after"] + "\n"
                lines = joined.splitlines()
                start_i = next((i for i, l in enumerate(lines) if l.strip() == TASK_BLOCK_START), 0)
                first_task = next(
                    (i for i in range(start_i + 1, len(lines)) if re.match(r"^-\s*\[[ xX]\]", lines[i].strip())), None
                )
                for k, item in enumerate(c.get("lines") or []):
                    item["line_no"] = (first_task + k) if first_task is not None else None
                applied.append(c)

            text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
            # 进度块
            for c in [x for x in file_mod if x["kind"] == "progress"]:
                text = _apply_progress(text, c["after"])
                applied.append(c)

            fpath.write_text(text, encoding="utf-8")
            changed_files.append(rel)

            # 行号重定位（删除/插入对上方行无影响，但统一校正更稳）
            for c in [x for x in file_mod if x["kind"] in ("check", "update", "task_check", "task_update")]:
                if any(c is ap for ap in applied):
                    c["final_idx"] = next(
                        (i for i, l in enumerate(lines) if _norm_line(l) == _norm_line(c["after"])),
                        c["line_no"],
                    )

        # 更新关联记录 / 工作台侧数据（含 db 专属的 task_md）
        for c in ops:
            if c["kind"] == "delete" and c.get("link_id"):
                link = db.get(SelfSyncLink, c["link_id"])
                if link:
                    db.delete(link)
            elif c["kind"] in ("check", "update") and c.get("link_id"):
                link = db.get(SelfSyncLink, c["link_id"])
                if link:
                    link.line_text = c["after"]
                    link.line_no = c.get("final_idx", c["line_no"])
            elif c["kind"] == "append" and c.get("entity_id"):
                db.add(SelfSyncLink(file=rel, section=c["section"], line_text=c["after"],
                                    entity="daily_item", entity_id=c["entity_id"]))
            elif c["kind"] == "task_md" and c.get("link_id"):
                link = db.get(SelfSyncLink, c["link_id"])
                t = db.get(Task, c["entity_id"])
                md_line = c.get("md_line") or ""
                if t is not None:
                    md_done = _line_done(md_line)
                    if md_done != (t.status == "done"):
                        from .tasks import _apply_status_change

                        _apply_status_change(db, t, "done" if md_done else "todo", t.status)
                    md_title = _line_title(md_line)
                    if md_title and _norm_title(md_title) != _norm_title(t.title):
                        t.title = md_title
                if link:
                    link.line_text = md_line
                    link.line_no = c["line_no"]
                applied.append(c)
            elif c["kind"] in ("task_check", "task_update") and c.get("link_id"):
                link = db.get(SelfSyncLink, c["link_id"])
                if link:
                    link.line_text = c["after"]
                    link.line_no = c.get("final_idx", c["line_no"])
            elif c["kind"] == "task_delete" and c.get("link_id"):
                link = db.get(SelfSyncLink, c["link_id"])
                if link:
                    db.delete(link)
            elif c["kind"] == "task_append" and c.get("entity_id"):
                db.add(SelfSyncLink(file=rel, section=c["section"], line_text=c["after"],
                                    entity="task", entity_id=c["entity_id"], line_no=c.get("inserted_at")))
            elif c["kind"] == "task_block_create":
                for item in c.get("lines") or []:
                    db.add(SelfSyncLink(file=rel, section=c["section"], line_text=item["line"],
                                        entity="task", entity_id=item["entity_id"], line_no=item.get("line_no")))
    db.commit()
    return {"applied": len(applied), "skipped": skipped, "backups": backups,
            "changed_files": changed_files, "changes": applied}


# ---------------------------------------------------------------- 周复盘导出
def _review_stats(db: Session, ws: date, we: date) -> dict:
    start_dt = datetime.combine(ws, time.min)
    end_dt = datetime.combine(we + timedelta(days=1), time.min)
    items = db.query(DailyItem).filter(
        DailyItem.scheduled_date >= ws, DailyItem.scheduled_date <= we
    ).all()
    done_items = [i for i in items if i.status == "done"]
    logs = db.query(TimeLog).filter(TimeLog.start_time >= start_dt, TimeLog.start_time < end_dt,
                                    TimeLog.duration_seconds > 0).all()
    focus_sec = sum(l.duration_seconds or 0 for l in logs)
    ck_days = len({c.date for c in db.query(Checkin).filter(Checkin.date >= ws, Checkin.date <= we).all()})
    lit_read = db.query(LiteratureItem).filter(
        LiteratureItem.read_date.isnot(None), LiteratureItem.read_date >= ws, LiteratureItem.read_date <= we
    ).count()
    oj_week = db.query(OJSolve).filter(OJSolve.date >= ws, OJSolve.date <= we).count()
    oj_total = db.query(OJSolve).count()
    segs = db.query(AttendanceSegment).filter(
        AttendanceSegment.start_at >= start_dt, AttendanceSegment.start_at < end_dt
    ).all()
    att = sum(max(0, int(((s.end_at or datetime.now()) - s.start_at).total_seconds())) for s in segs)
    # 刷题累计按已 AC 去重
    solves = db.query(OJSolve).all()
    ac = len({x.problem_id for x in solves if x.kind == "solve"})
    return {
        "planned": len(items),
        "done_count": len(done_items),
        "percent": round(len(done_items) / len(items) * 100) if items else 0,
        "focus_text": _fmt_dur(focus_sec),
        "pomodoros": sum(1 for l in logs if l.kind == "pomodoro"),
        "checkin_days": ck_days,
        "lit_read": lit_read,
        "oj_week": oj_week,
        "oj_total": ac,
        "attendance_text": _fmt_dur(att),
    }


@router.post("/export-review")
def export_review(data: dict | None = None, db: Session = Depends(get_db)):
    root = _require_root(db)
    body = data or {}
    try:
        d = sa.load(root)
    except Exception as e:
        raise HTTPException(500, f"解析 Self_analysis 失败：{e}")

    review = None
    ws_str = body.get("week_start")
    if ws_str:
        try:
            ws = date.fromisoformat(str(ws_str))
            review = db.query(Review).filter(Review.week_start == ws).first()
        except ValueError:
            raise HTTPException(400, "week_start 格式不正确")
    if review is None:
        review = db.query(Review).order_by(Review.week_start.desc()).first()
    if review is None:
        raise HTTPException(400, "还没有周复盘记录，请先在「周复盘」页填写")

    ws = review.week_start
    we = review.week_end or (ws + timedelta(days=6))
    try:
        content = json.loads(review.content or "{}")
    except Exception:
        content = {}
    stats = _review_stats(db, ws, we)
    week_no = sa.plan_week_number(ws, d.get("weeks", []))
    md = sa.render_review_md(ws, we, week_no, content, stats)
    filename = f"第{week_no}周.md" if week_no else f"复盘_{ws.isoformat()}.md"
    # 与用户 05 模板一致：导出到 plan/复盘/（读取端两种位置都兼容，见 services/self_analysis.py）
    rel = f"plan/复盘/{filename}"
    target = root / rel
    out = {"filename": rel, "content": md, "exists": target.exists(), "week_start": ws.isoformat()}
    if body.get("apply"):
        if target.exists():
            out["backup"] = _backup_file(root, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(md, encoding="utf-8")
        out["written"] = True
    return out


# ---------------------------------------------------------------- 计划文档（查看/编辑）
def _safe_doc_path(root: Path, rel: str) -> Path:
    """把相对路径解析为 root 下的 .md 文件；拒绝路径遍历/绝对路径/非 md 文件。"""
    rel = str(rel or "").replace("\\", "/").strip()
    if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise HTTPException(400, "非法文件路径")
    try:
        p = (root / rel).resolve()
        p.relative_to(root.resolve())
    except (ValueError, OSError):
        raise HTTPException(400, "非法文件路径")
    if p.suffix.lower() != ".md":
        raise HTTPException(400, "只允许查看/编辑 Markdown 文件")
    return p


@router.get("/docs")
def list_docs(db: Session = Depends(get_db)):
    """列出 Self_analysis 下的所有 md 文件（含子目录复盘）。"""
    root = _require_root(db)
    files = []
    for f in sa.scan(root):
        try:
            st = f.stat()
            files.append({
                "path": f.relative_to(root).as_posix(),
                "name": f.name,
                "dir": "" if f.parent.resolve() == root.resolve() else f.parent.relative_to(root).as_posix(),
                "size": st.st_size,
                "mtime": st.st_mtime,
            })
        except OSError:
            continue
    files.sort(key=lambda x: x["path"])
    return {"root": str(root), "files": files}


@router.get("/docs/content")
def read_doc(path: str, db: Session = Depends(get_db)):
    """读取单个 md 文件全文（含 mtime，供保存时冲突检测）。"""
    root = _require_root(db)
    p = _safe_doc_path(root, path)
    if not p.exists():
        raise HTTPException(404, "文件不存在")
    st = p.stat()
    return {
        "path": p.relative_to(root.resolve()).as_posix(),
        "content": p.read_text(encoding="utf-8", errors="ignore"),
        "mtime": st.st_mtime,
        "size": st.st_size,
    }


@router.put("/docs/content")
def save_doc(data: dict, db: Session = Depends(get_db)):
    """保存 md 全文：写前自动备份；默认按 base_mtime 检测外部修改（409），force=true 强制覆盖。"""
    root = _require_root(db)
    p = _safe_doc_path(root, str(data.get("path") or ""))
    if not p.exists():
        raise HTTPException(404, "文件不存在（可能已被移动或删除）")
    content = data.get("content")
    if not isinstance(content, str):
        raise HTTPException(400, "缺少 content 内容")
    if not bool(data.get("force")):
        base_mtime = data.get("base_mtime")
        if base_mtime is not None:
            try:
                changed = abs(p.stat().st_mtime - float(base_mtime)) > 2
            except (OSError, TypeError, ValueError):
                changed = False
            if changed:
                raise HTTPException(409, "文件已被其他程序修改（编辑期间内容已变化），请重新打开确认，或选择强制覆盖")
    rel = p.relative_to(root.resolve()).as_posix()
    backup = _backup_file(root, rel)
    # 保持原文件行尾风格（CRLF 文件保存后仍是 CRLF），避免整文件 diff
    raw = p.read_bytes()
    text = content.replace("\r\n", "\n")
    if b"\r\n" in raw:
        text = text.replace("\n", "\r\n")
    p.write_bytes(text.encode("utf-8"))
    st = p.stat()
    return {"ok": True, "path": rel, "backup": backup, "mtime": st.st_mtime, "size": st.st_size}
