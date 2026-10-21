import difflib
import json
import re
import threading
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models import AiRecord, Checkin, DailyItem, Experiment, Goal, LiteratureItem, Milestone, Note, Setting, Skill, Task
from ..services import deepseek
from ..services.deepseek import AIError
from ..services.task_flow import is_near_term
from .daily import _renorm_pending, serialize_item

router = APIRouter(prefix="/api/ai", tags=["ai"])

FEATURE_LABEL = {
    "summarize": "文献/内容总结",
    "writing": "笔记润色",
    "organize-note": "笔记整理",
    "review-advice": "复盘点评",
    "literature-qa": "文献问答",
    "meeting-notes": "组会纪要",
    "tag-literature": "AI 打标",
    "daily-plan": "每日整理",
    "recommend-literature": "推荐文献",
    "plan": "AI 规划",
    "batch-tag": "批量打标",
    "batch-summarize": "批量总结",
    "kb-qa": "知识库问答",
    "paper-outline": "论文大纲",
    "paper-chapter": "论文章节写作",
    "paper-polish": "论文润色",
    "note-tags": "笔记打标",
    "chat": "AI 对话",
    "estimate-tasks": "任务时长预估",
    "advisor-report": "导师周报",
}


def _profile_block(db: Session) -> str:
    """读取用户科研画像（设置里的 research_profile JSON），返回可注入 prompt 的段落。"""
    s = db.get(Setting, "research_profile")
    raw = (s.value if s else "") or ""
    try:
        p = json.loads(raw) if raw else {}
    except Exception:
        p = {}
    parts = []
    for k, label in (
        ("direction", "研究方向"),
        ("methods", "常用方法/工具"),
        ("stage", "当前阶段"),
        ("goal", "毕业/近期目标"),
        ("writing_style", "写作偏好"),
    ):
        if str(p.get(k) or "").strip():
            parts.append(f"{label}：{p.get(k)}")
    if not parts:
        return ""
    return "用户科研画像（所有建议与输出都应贴合这些背景）：\n" + "\n".join(parts)


def _record_ai(feature: str, summary: str, result: str):
    try:
        db = SessionLocal()
        db.add(AiRecord(feature=feature, summary=(summary or "")[:200], result=(result or "")[:3000]))
        db.commit()
        db.close()
    except Exception:
        pass


def _guard():
    if not deepseek.is_configured():
        raise HTTPException(400, "未配置 DeepSeek API Key，请先到设置页填写。")


def _call(feature: str, fn, *args, **kwargs):
    """统一调用 AI：记录历史，将 AIError 转为友好 HTTP 错误。"""
    try:
        result = fn(*args, **kwargs)
        _record_ai(feature, str(args[0])[:200] if args else "", str(result)[:3000])
        return result
    except AIError as e:
        raise HTTPException(e.status_code, str(e))
    except Exception as e:
        raise HTTPException(500, f"AI 调用异常：{e}")


# ---------- AI 历史 ----------
@router.get("/history")
def ai_history(db: Session = Depends(get_db)):
    rows = db.query(AiRecord).order_by(AiRecord.created_at.desc()).limit(60).all()
    return [
        {
            "id": r.id,
            "feature": r.feature,
            "feature_label": FEATURE_LABEL.get(r.feature, r.feature),
            "summary": r.summary,
            "result": r.result,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.delete("/history")
def ai_history_clear(db: Session = Depends(get_db)):
    db.query(AiRecord).delete()
    db.commit()
    return {"ok": True}


@router.post("/summarize")
def ai_summarize(data: dict):
    _guard()
    text = data.get("text", "")
    if not text.strip():
        raise HTTPException(400, "内容为空")
    return {"result": _call("summarize", deepseek.summarize_text, text)}


@router.post("/writing")
def ai_writing(data: dict):
    _guard()
    prompt = data.get("prompt", "")
    context = data.get("context", "")
    if not prompt.strip():
        raise HTTPException(400, "指令为空")
    return {"result": _call("writing", deepseek.assist_writing, prompt, context)}


def _read_latest_sa_review(db: Session) -> str:
    """读 Self_analysis 下最近修改的一份手写复盘（供 AI 点评参考）。

    兼容两种位置：根目录 复盘/（工作台导出）与 plan/复盘/（05 模板手写），
    按递归相对路径中是否含「复盘」目录识别，避免误把普通文档当复盘。
    """
    from pathlib import Path

    s = db.get(Setting, "self_analysis_path")
    path = (s.value if s else "") or ""
    if not path:
        return ""
    root = Path(path)
    if not root.exists():
        return ""
    files: list[Path] = []
    for f in root.rglob("*.md"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue
        if "复盘" in rel.parts:
            files.append(f)
    if not files:
        return ""
    latest = max(files, key=lambda f: f.stat().st_mtime)
    try:
        txt = latest.read_text(encoding="utf-8", errors="ignore")[:3000]
    except Exception:
        return ""
    return f"{latest.name}（手写复盘，供点评参考）：\n{txt}"


@router.post("/review-advice")
def ai_review_advice(data: dict, db: Session = Depends(get_db)):
    _guard()
    week = data.get("week", "")
    content = data.get("content", "")
    if not week.strip():
        raise HTTPException(400, "统计信息为空")
    manual = _read_latest_sa_review(db)
    if manual:
        content = (content + "\n\n" + manual).strip()
    return {"result": _call("review-advice", deepseek.review_advice, week, content)}


@router.post("/literature-qa")
def ai_literature_qa(data: dict, db: Session = Depends(get_db)):
    _guard()
    question = data.get("question", "").strip()
    history = data.get("history") or []
    if not question:
        raise HTTPException(400, "问题为空")
    items = db.query(LiteratureItem).limit(50).all()
    context = "\n\n".join(
        f"标题：{i.title}\n摘要：{(i.abstract or '')[:300]}\nAI总结：{(i.ai_summary or '')[:200]}"
        for i in items
    )
    if not context.strip():
        raise HTTPException(400, "文献库为空，请先从 Zotero 同步或添加文献")
    profile = _profile_block(db)
    if profile:
        context = profile + "\n\n" + context
    history_text = "\n".join(
        f"问：{h.get('q', '')}\n答：{(h.get('a') or '')[:200]}" for h in history[-5:]
    )
    if history_text:
        context += f"\n\n对话历史：\n{history_text}"
    return {"result": _call("literature-qa", deepseek.literature_qa, question, context)}


# ---------- 本地知识库问答（RAG）----------
_KB_STOP = {
    "我们", "你们", "他们", "什么", "怎么", "为什么", "可以", "一下", "这篇", "那篇",
    "我的", "你的", "记录", "写过", "哪些", "如何", "对于", "一个", "相关", "内容",
    "笔记", "文献", "里面", "里写", "帮我", "总结", "一下", "请问", "知道", "介绍",
    "这个", "那个", "以及", "还有", "没有", "自己",
}


def _kb_keywords(question: str) -> list[str]:
    import re

    q = question.lower()
    words = [w for w in re.findall(r"[a-z][a-z0-9\-]{1,}", q) if w not in ("the", "and", "for", "with", "about", "what", "how", "does", "did")]
    grams = set()
    for b in re.findall(r"[\u4e00-\u9fa5]{2,}", q):
        for i in range(len(b) - 1):
            g = b[i : i + 2]
            if g not in _KB_STOP:
                grams.add(g)
    return list(grams) + words


def _score(text: str, title: str, kws: list[str]) -> int:
    tl, tc = (title or "").lower(), (text or "").lower()
    s = 0
    for k in kws:
        if k in tl:
            s += 3
        elif k in tc:
            s += 1
    return s


def _search_kb(db: Session, question: str, top: int = 8):
    """在笔记 + 文献 + 实验中检索与问题最相关的片段（简单关键词打分，数据量小足够快）。"""
    kws = _kb_keywords(question)
    if not kws:
        return [], []
    notes = []
    for n in db.query(Note).all():
        sc = _score(n.content, n.title, kws)
        if sc > 0:
            notes.append((sc, {"type": "note", "id": n.id, "title": n.title, "snippet": (n.content or "")[:400]}))
    lits = []
    for it in db.query(LiteratureItem).all():
        sc = _score(f"{it.abstract or ''} {it.ai_summary or ''} {it.tags or ''}", it.title, kws)
        if sc > 0:
            lits.append((sc, {"type": "literature", "id": it.id, "title": it.title, "snippet": (it.ai_summary or it.abstract or "")[:400]}))
    exps = []
    for e in db.query(Experiment).all():
        sc = _score(e.notes, e.title, kws)
        if sc > 0:
            exps.append((sc, {"type": "experiment", "id": e.id, "title": e.title, "snippet": (e.notes or "")[:400]}))
    merged = sorted(notes + lits + exps, key=lambda x: x[0], reverse=True)[:top]
    return merged, [m[1] for m in merged]


@router.post("/kb-qa")
def ai_kb_qa(data: dict, db: Session = Depends(get_db)):
    _guard()
    question = (data.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "问题为空")
    scored, sources = _search_kb(db, question)
    if not sources:
        raise HTTPException(400, "本地知识库里没有检索到相关内容，换个问法试试")
    context = "\n\n".join(
        f"【来源{idx}｜{s['type']}｜{s['title']}】\n{s['snippet']}" for idx, s in enumerate(sources, 1)
    )
    profile = _profile_block(db)
    if profile:
        context = profile + "\n\n" + context
    result = _call("kb-qa", deepseek.kb_qa, question, context)
    return {"result": result, "sources": sources}


@router.post("/organize-note")
def ai_organize_note(data: dict):
    _guard()
    content = data.get("content", "").strip()
    if not content:
        raise HTTPException(400, "内容为空")
    return {"result": _call("organize-note", deepseek.organize_note, content)}


@router.post("/meeting-notes")
def ai_meeting_notes(data: dict):
    _guard()
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(400, "内容为空")
    return {"result": _call("meeting-notes", deepseek.meeting_notes, text)}


@router.post("/tag-literature")
def ai_tag_literature(data: dict, db: Session = Depends(get_db)):
    import re

    _guard()
    item_id = data.get("item_id")
    preview = bool(data.get("preview", False))
    item = db.get(LiteratureItem, item_id)
    if not item:
        raise HTTPException(404, "文献不存在")
    tags = _call("tag-literature", deepseek.tag_literature, item.title, item.abstract)
    # AI 标签可能用逗号/顿号/空格/换行分隔，统一拆分并规范合并
    raw = re.split(r"[,，、;；\s]+", tags)
    raw_existing = [t.strip() for t in item.tags.split(",") if t.strip()]
    existing_norm = {_norm_tag(t) for t in raw_existing}
    new = sorted({_norm_tag(t) for t in raw if t.strip()} - existing_norm)
    if preview:
        # 预览模式：不写入，返回建议标签与已有标签对比（已有标签保留原始写法）
        return {"suggested": new, "existing": raw_existing, "result": tags}
    merged = raw_existing + new
    item.tags = ",".join(dict.fromkeys(merged))
    db.commit()
    return {"result": tags, "tags": item.tags, "suggested": new}


# ---------- AI 规划助手 ----------
def _collect_context(db: Session, goal_ids: list[int]) -> str:
    """汇总现有目标/文献/实验/习惯，作为 AI 规划参考。"""
    parts = []
    profile = _profile_block(db)
    if profile:
        parts.append(profile)
    gq = (
        db.query(Goal).filter(Goal.id.in_(goal_ids)).all()
        if goal_ids
        else db.query(Goal).order_by(Goal.created_at).all()
    )
    if gq:
        lines = []
        for g in gq[:30]:
            line = f"- {g.title}（{g.level} 目标，进度 {g.progress}%）"
            if g.description:
                line += f"：{g.description}"
            lines.append(line)
            for t in g.tasks:
                state = "已完成" if t.status == "done" else ("进行中" if t.status == "doing" else "待办")
                line = f"    ├ 任务：{t.title}（{state}，DDL {t.due_date or '无'}）"
                if t.tags:
                    line += f" 标签：{t.tags}"
                lines.append(line)
        parts.append("现有目标：\n" + "\n".join(lines))
    lit = db.query(LiteratureItem).order_by(LiteratureItem.created_at.desc()).limit(10).all()
    if lit:
        parts.append(
            "文献库（最近 10 篇）：\n"
            + "\n".join(f"- {i.title}" + (f"（{i.year}）" if i.year else "") for i in lit)
        )
    exp = db.query(Experiment).order_by(Experiment.created_at.desc()).limit(10).all()
    if exp:
        parts.append(
            "实验记录（最近 10 条）：\n"
            + "\n".join(f"- {e.title}（{e.status}，{e.dataset} / {e.model}）" for e in exp)
        )
    habits = db.query(Task).filter(Task.task_type == "habit").all()
    if habits:
        parts.append(
            "习惯打卡：\n"
            + "\n".join(f"- {h.title}（已打卡 {len(h.checkins)} 天）" for h in habits)
        )
    return "\n\n".join(parts)


@router.post("/plan")
def ai_plan(data: dict, db: Session = Depends(get_db)):
    _guard()
    mode = data.get("mode", "generate")
    text = (data.get("text") or "").strip()
    goal_ids = data.get("goal_ids") or []
    if mode not in ("generate", "parse", "optimize"):
        raise HTTPException(400, "mode 无效")
    context = ""
    if mode == "optimize":
        context = _collect_context(db, goal_ids)
    elif not text:
        raise HTTPException(400, "请输入描述或粘贴规划文本")
    try:
        if mode == "parse":
            plan = deepseek.parse_plan(text, context)
        elif mode == "optimize":
            plan = deepseek.optimize_plan(context, text)
        else:
            plan = deepseek.generate_plan(text, context)
    except AIError as e:
        raise HTTPException(e.status_code, str(e))
    except Exception as e:
        raise HTTPException(500, f"AI 调用异常：{e}")
    _record_ai("plan", text[:200] or f"优化已有规划（{len(goal_ids)} 个目标）", json.dumps(plan, ensure_ascii=False)[:3000])
    return {"plan": plan}


@router.post("/plan/save")
def ai_plan_save(data: dict, db: Session = Depends(get_db)):
    from datetime import date

    plan = data.get("plan") or data
    if not isinstance(plan, dict):
        raise HTTPException(400, "规划数据无效")

    def _d(v):
        if not v:
            return None
        try:
            return date.fromisoformat(str(v))
        except ValueError:
            return None

    def _prio(v):
        try:
            return max(1, min(5, int(v)))
        except (TypeError, ValueError):
            return 2

    counts = {"goals": 0, "tasks": 0, "milestones": 0, "skipped_far_tasks": 0}
    title_id: dict[str, int] = {}

    annual = plan.get("annual") or {}
    if (annual.get("title") or "").strip():
        g = Goal(
            title=annual["title"].strip(),
            description=(annual.get("description") or "").strip(),
            level="annual",
            period_end=_d(annual.get("deadline")),
        )
        db.add(g)
        db.flush()
        title_id[g.title] = g.id
        title_id["annual"] = g.id
        counts["goals"] += 1

    goal_objs = []
    for item in plan.get("goals") or []:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        g = Goal(
            title=title,
            description=(item.get("description") or "").strip(),
            level=item.get("level", "quarter"),
            period_start=_d(item.get("period_start")),
            period_end=_d(item.get("period_end")),
        )
        db.add(g)
        db.flush()
        goal_objs.append((item, g))
        title_id[title] = g.id
        counts["goals"] += 1

    for item, g in goal_objs:
        parent = item.get("parent") or "annual"
        if parent in title_id:
            g.parent_id = title_id[parent]

    today = date.today()
    for item, g in goal_objs:
        for t in item.get("tasks") or []:
            ttitle = (t.get("title") or "").strip()
            if not ttitle:
                continue
            due = _d(t.get("due_date"))
            if not is_near_term(g.period_start, due, today):
                counts["skipped_far_tasks"] += 1
                continue
            db.add(
                Task(
                    title=ttitle,
                    task_type="once",
                    goal_id=g.id,
                    due_date=due,
                    priority=_prio(t.get("priority")),
                )
            )
            counts["tasks"] += 1

    for m in plan.get("milestones") or []:
        mtitle = (m.get("title") or "").strip()
        if not mtitle:
            continue
        db.add(Milestone(title=mtitle, due_date=_d(m.get("due_date"))))
        counts["milestones"] += 1

    db.commit()
    return {"ok": True, **counts}


# ---------- 每日清单 / 文献推荐 / Self_analysis ----------
def _read_self_analysis(db: Session) -> str:
    """读取 Self_analysis 规划文件夹（递归 + 结构化解析：当前阶段/本周目标/检查点/节奏）。

    解析失败时由服务层降级为全文截取；文件夹不存在时返回空串。
    """
    from pathlib import Path

    from ..services import self_analysis as sa_service

    s = db.get(Setting, "self_analysis_path")
    path = (s.value if s else "") or ""
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    try:
        return sa_service.build_prompt(p)
    except Exception:
        return ""


# 文献候选相关性关键词（本项目研究方向=红外小目标检测；离题条目如「水下目标检测」不进候选）
_LIT_RELEVANT_KEYS = ("红外", "infrared", "irstd", "小目标", "small target")


def _lit_relevant(item) -> bool:
    text = f"{item.title or ''} {item.tags or ''}".lower()
    return any(k in text for k in _LIT_RELEVANT_KEYS)


def _daily_context(db: Session, focus: str = "") -> str:
    from datetime import date, datetime

    today = date.today()
    parts = []
    profile = _profile_block(db)
    if profile:
        parts.append(profile)
    if focus:
        parts.append("用户今日侧重方向（最高优先级，所有推荐都要围绕它，不要跑题）：\n" + focus)
    tasks = db.query(Task).filter(Task.status.notin_(["done", "archived", "deferred"]), Task.due_date == today).all()
    if tasks:
        parts.append("今日到期任务：\n" + "\n".join(f"- {t.title}（DDL {t.due_date}）" for t in tasks))
    habits = db.query(Task).filter(Task.task_type == "habit", Task.status.notin_(["done", "archived", "deferred"])).all()
    if habits:
        lines = []
        for h in habits:
            checked = db.query(Checkin).filter(Checkin.task_id == h.id, Checkin.date == today).first()
            if not checked:
                lines.append(f"- {h.title}（今天未打卡）")
        if lines:
            parts.append("待打卡习惯：\n" + "\n".join(lines))
    lit = (
        db.query(LiteratureItem)
        .filter(LiteratureItem.read_status.in_(["unread", "reading"]))
        .order_by(LiteratureItem.created_at.desc())
        .limit(16)
        .all()
    )
    # 研究方向相关性过滤：库里的离题条目（如「水下目标检测」）不进候选，
    # 避免 AI 推荐与红外小目标无关的文献（2026-10-08 用户反馈「不知道从哪冒出来的文献」）。
    relevant = [i for i in lit if _lit_relevant(i)]
    lit = (relevant or lit)[:8]
    if lit:
        parts.append(
            "待读文献：\n"
            + "\n".join(f"- [{i.id}] {i.title}（{i.year or '?年'}，标签：{i.tags or '无'}）" for i in lit)
        )
    skills = db.query(Skill).all()
    if skills:
        lines = []
        for s in skills:
            total = round(sum(x.progress for x in s.stages) / len(s.stages)) if s.stages else 0
            if total < 100:
                stg = " / ".join(f"{x.name}{x.progress}%" for x in s.stages)
                lines.append(f"- {s.name}（总进度{total}%，阶段：{stg}）")
        if lines:
            parts.append(
                "待推进技能（工作台技能表，可能滞后于作战计划手记；两边冲突时以作战计划为准）：\n"
                + "\n".join(lines)
            )
    # 已有待办（含顺延）合并为一个列表：原先「昨日未完成」与「今日已有项」重复列两遍，
    # 浪费上下文且 AI 仍会漏掉判重（2026-10-08 合并）。
    pend = (
        db.query(DailyItem)
        .filter(DailyItem.status == "pending", DailyItem.scheduled_date <= today)
        .order_by(DailyItem.scheduled_date)
        .all()
    )
    if pend:
        lines = [f"- {i.content}" + ("（顺延）" if i.scheduled_date < today else "") for i in pend[:40]]
        parts.append("今日清单已有项（含顺延，不要重复推荐；与它们「同一件事、换个说法」的也不要推荐）：\n" + "\n".join(lines))
    done_items = (
        db.query(DailyItem)
        .filter(
            DailyItem.status == "done",
            DailyItem.completed_at >= datetime.combine(today, datetime.min.time()),
        )
        .all()
    )
    if done_items:
        parts.append("今天已完成（不要重复推荐；含今天补完的旧账）：\n" + "\n".join(f"- {i.content}" for i in done_items[:20]))
    sa = _read_self_analysis(db)
    if sa:
        parts.append(sa)
    # 当前阶段目标：优先取期间覆盖今天的层级目标（周>月>季>年）+ 其未完成任务，让推荐聚焦
    level_w = {"week": 4, "month": 3, "quarter": 2, "annual": 1}
    goals = (
        db.query(Goal)
        .filter(Goal.status != "done")
        .filter(
            (Goal.period_start.is_(None)) | (Goal.period_start <= today),
            (Goal.period_end.is_(None)) | (Goal.period_end >= today),
        )
        .all()
    )
    if goals:
        goals.sort(key=lambda g: level_w.get(g.level, 0), reverse=True)
        lines = []
        for g in goals[:3]:
            undone = [t.title for t in g.tasks if t.status != "done"]
            suffix = f" → 未完成任务：{'、'.join(undone[:5])}" if undone else ""
            lines.append(f"- 【{g.level}】{g.title}{suffix}")
        if lines:
            parts.append("当前阶段目标（优先级高，推荐必须服务于这些目标）：\n" + "\n".join(lines))
    return "\n\n".join(parts)


def _norm_tag(t: str) -> str:
    t = t.strip()
    for suf in ("算法", "方法", "技术", "研究", "方向", "综述", "框架", "模型"):
        if t.endswith(suf) and len(t) > len(suf) + 1:
            t = t[: -len(suf)]
    return t


def _int_or(v, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _date_or_none(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v).strip())
    except (TypeError, ValueError):
        return None


# AI 重新生成时的措辞常有差异（换词、加细节、多/少空格），纯 exact 匹配会漏过 → 重复堆积。
# 判重规则（2026-10-01 初版 0.85；2026-10-08 实测大量「换说法」漏网后升级，见坑 #107）：
#   1) 归一化（去空白+标点+小写）后完全相同 → 同一件；
#   2) 相似度 ≥ 0.8 → 同一件；
#   3) 相似度 ≥ 0.6 且共享 4-gram ≥ 3 → 同一件（中文换措辞/补细节，如「完成矩阵理论的作业，10.08截至」
#      vs「完成矩阵理论作业（10.08截止），用AI辅助推导+手写关键步骤」）；
#   4) 豁免：短内容（<8 字）只认归一化相同（「读论文」≠「读论文A」）；课时区间（21~41 vs 41~60）
#      或章节号（第4章 vs 第5章）不同 → 判为不同任务，防误伤同课程的不同章节。
_STRONG_DUP_RATIO = 0.8
_WEAK_DUP_RATIO = 0.6
_MIN_FUZZY_LEN = 8
_PUNCT_RE = re.compile(r"[\s，。、（）()【】《》〈〉:：,.!！?？+＋~～\-—–_;；'\"“”‘’]+")
_RANGE_RE = re.compile(r"\d+\s*[~～\-–]\s*\d+")
_CHAPTER_RE = re.compile(r"第\s*(\d+)\s*[章节課课]")


def _norm_core(s: str) -> str:
    return _PUNCT_RE.sub("", str(s or "").lower())


def _shared_4grams(a: str, b: str) -> int:
    if len(a) < 4 or len(b) < 4:
        return 0
    ga = {a[i:i + 4] for i in range(len(a) - 3)}
    gb = {b[i:i + 4] for i in range(len(b) - 3)}
    return len(ga & gb)


def _content_duplicate(a: str, b: str) -> bool:
    """两条内容是否「同一件事」（容忍 AI 换措辞/加细节；防误伤不同章节/课时）。"""
    ra, rb = set(_RANGE_RE.findall(str(a or ""))), set(_RANGE_RE.findall(str(b or "")))
    if ra and rb and ra != rb:
        return False
    ca, cb = set(_CHAPTER_RE.findall(str(a or ""))), set(_CHAPTER_RE.findall(str(b or "")))
    if ca and cb and ca != cb:
        return False
    na, nb = _norm_core(a), _norm_core(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if min(len(na), len(nb)) < _MIN_FUZZY_LEN:
        return False
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    if ratio >= _STRONG_DUP_RATIO:
        return True
    return ratio >= _WEAK_DUP_RATIO and _shared_4grams(na, nb) >= 3


_TR_RE = re.compile(r"^\s*(\d{1,2}:\d{2})\s*[-–~]\s*(\d{1,2}:\d{2})\s*$")


def _time_range_or_empty(v) -> str:
    m = _TR_RE.match(str(v or ""))
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def _auto_land_enabled(db: Session) -> bool:
    """AI 任务自动落今日清单开关（设置 daily_ai_auto_land，默认开）。"""
    s = db.get(Setting, "daily_ai_auto_land")
    val = ((s.value if s else "") or "true").strip().lower()
    return val not in ("false", "0", "no")


# 并发保护：同一后端可能同时收到多个页面的「生成今日任务」请求（双开窗口/多标签页），
# 若「撤下旧自动项 → 写入新项」不加锁，两批任务会同时落地造成重复（2026-09-30 实测踩坑，见坑 #77）。
_land_lock = threading.Lock()


def _plan_and_land(db: Session, items: list, auto_land: bool) -> tuple[list[dict], list[DailyItem]]:
    """去重 + 权重缩放 + （可选）自动落今日清单。全程持锁，保证并发请求串行执行。"""
    today = date.today()
    landed: list[DailyItem] = []
    with _land_lock:
        # 重新生成时先撤下今天此前自动落地的未完成项（防堆积；已完成的历史保留）
        if auto_land:
            db.query(DailyItem).filter(
                DailyItem.scheduled_date == today,
                DailyItem.status == "pending",
                DailyItem.auto_landed.is_(True),
            ).delete(synchronize_session=False)
            db.commit()

        # AI 原始候选内容（用于旧自动项平替判定，先于 exist 查询执行）
        raw_contents = [
            (it.get("content") or "").strip()
            for it in items[:7]
            if isinstance(it, dict) and (it.get("content") or "").strip()
        ]

        # 撤下更早日期与新批次「近似重复」的自动项：AI 重新生成时措辞可能略有变化，
        # 只靠 exact 内容去重会漏过 → 旧批次（顺延红标）与今天新批次并存，看上去「同一件事一红一白」。
        # 只删「未完成 + 自动落地 + 计划日早于今天 + 与新批次内容近似」的旧项；
        # 用户手动项与已完成的历史一律不动（2026-10-01 修，见「十、待办」）。
        if auto_land and raw_contents:
            old_autos = (
                db.query(DailyItem)
                .filter(
                    DailyItem.scheduled_date < today,
                    DailyItem.status == "pending",
                    DailyItem.auto_landed.is_(True),
                )
                .all()
            )
            for row in old_autos:
                if any(_content_duplicate(row.content, c) for c in raw_contents):
                    db.delete(row)
            db.commit()

        exist = db.query(DailyItem).filter(DailyItem.status == "pending").all()
        exist_contents = {i.content.strip() for i in exist}
        exist_sources = {(i.kind, i.source_id) for i in exist if i.source_id}
        done_today = {
            i.content.strip()
            for i in db.query(DailyItem).filter(
                DailyItem.status == "done",
                DailyItem.completed_at >= datetime.combine(today, datetime.min.time()),
            ).all()
        }
        # AI 建议 vs 已有待办/今日已完成 的近似查重池：用户手动项绝不被删，但 AI 也不得再落一条
        # 换措辞的重复（2026-10-08 修：AI 把 10/7 未完成的手动项换个说法又落了一遍，见坑 #107）。
        ref_contents = [i.content for i in exist] + list(done_today)
        quadrants = ("important_urgent", "important_not", "not_urgent_important", "not_important_not")
        kinds = ("task", "habit", "literature", "manual")

        valid = []
        seen = set()
        for it in items[:7]:
            if not isinstance(it, dict):
                continue
            content = (it.get("content") or "").strip()
            if not content or content in exist_contents or content in done_today or content in seen:
                continue
            # 近似查重：与已有待办/今日已完成是「换措辞的同一件事」→ 不落（用户手动项保持原样）
            if any(_content_duplicate(content, c) for c in ref_contents):
                continue
            seen.add(content)
            src = it.get("source_id")
            kind = it.get("kind") if it.get("kind") in kinds else "manual"
            if src and (kind, src) in exist_sources:
                continue
            if kind == "literature":
                # 上下文只给过文献 id；校验存在性，防 AI 编造绑定
                if not src or not db.get(LiteratureItem, src):
                    kind, src = "manual", None
            elif src:
                src = None  # 任务/习惯 id 未提供过，AI 编造的绑定一律丢弃
            due = _date_or_none(it.get("due_date"))
            if due and due < today:
                # AI 偶发返回过期截止日（甚至年份幻觉，如 2024-10-01）→ 不落库，
                # 避免今日清单出现「截止已过」灰标（2026-10-01 实测）
                due = None
            valid.append(
                {
                    "content": content,
                    "kind": kind,
                    "source_id": src,
                    "quadrant": it.get("quadrant") if it.get("quadrant") in quadrants else "important_urgent",
                    "pomodoros": max(0, _int_or(it.get("pomodoros"), 0)),
                    "weight": max(1, min(100, _int_or(it.get("weight"), 10))),
                    "due_date": due,
                    "time_range": _time_range_or_empty(it.get("time_range")),
                    "reason": (it.get("reason") or "").strip(),
                }
            )
        total = sum(x["weight"] for x in valid)
        if valid and total > 0:
            # 按比例缩放 + 余数分配，保证总和恒为 100
            scaled = [int(x["weight"] / total * 100) for x in valid]
            diff = 100 - sum(scaled)
            frac = sorted(
                ((x["weight"] / total * 100 - scaled[i], i) for i, x in enumerate(valid)),
                reverse=True,
            )
            for k in range(abs(diff)):
                idx = frac[k % len(frac)][1]
                scaled[idx] += 1 if diff > 0 else -1
            for i, x in enumerate(valid):
                x["weight"] = max(1, scaled[i])
        # 自动落地：写入今日清单（可删改）。文献建议保留绑定（勾选完成自动置已读，与手动采纳一致）；
        # 其余落为 kind=ai 不绑任务，避免误联动任务状态。
        if auto_land and valid:
            for x in valid:
                linked_lit = x["kind"] == "literature" and x["source_id"]
                row = DailyItem(
                    content=x["content"],
                    kind="literature" if linked_lit else "ai",
                    source_id=x["source_id"] if linked_lit else None,
                    scheduled_date=today,
                    due_date=x["due_date"],
                    quadrant=x["quadrant"],
                    weight=x["weight"],
                    pomodoros=x["pomodoros"],
                    time_range=x["time_range"],
                    status="pending",
                    auto_landed=True,
                )
                db.add(row)
                landed.append(row)
            db.commit()
            _renorm_pending(db)
            for row in landed:
                db.refresh(row)
    return valid, landed


@router.post("/daily-plan")
def ai_daily_plan(data: dict | None = None, db: Session = Depends(get_db)):
    _guard()
    focus = ((data or {}).get("focus") or "").strip()
    context = _daily_context(db, focus)
    if not context.strip():
        raise HTTPException(400, "当前没有可安排的内容（任务/习惯/文献/技能都为空）")
    items = _call("daily-plan", deepseek.generate_daily_plan, context)
    if not isinstance(items, list):
        raise HTTPException(400, "AI 返回格式异常")

    today = date.today()
    auto_land = _auto_land_enabled(db)
    valid, landed = _plan_and_land(db, items, auto_land)
    return {
        "items": valid,
        "count": len(valid),
        "auto_land": auto_land,
        "landed": [serialize_item(i, today) for i in landed],
        "landed_count": len(landed),
    }


def _advisor_context(db: Session) -> str:
    """导师周报草稿上下文：本周工作台产出 + 作战计划（当前阶段/周目标/铁律）。"""
    from ..models import AttendanceDay, AttendanceSegment, OJSolve, StudyLog, TimeLog

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    week_dt = datetime.combine(monday, datetime.min.time())
    parts: list[str] = []

    sa = _read_self_analysis(db)
    if sa:
        parts.append(sa)

    done_tasks = (
        db.query(Task)
        .filter(Task.status == "done", Task.completed_at.isnot(None), Task.completed_at >= week_dt)
        .order_by(Task.completed_at.desc())
        .all()
    )
    if done_tasks:
        parts.append("本周完成任务（工作台记录）：\n" + "\n".join(f"- {t.title}" for t in done_tasks[:20]))

    logs = db.query(TimeLog).filter(TimeLog.start_time >= week_dt, TimeLog.duration_seconds > 0).all()
    focus_sec = sum(l.duration_seconds or 0 for l in logs)
    pomos = sum(1 for l in logs if l.kind == "pomodoro")
    if focus_sec:
        parts.append(f"本周投入：约 {focus_sec // 3600} 小时（番茄 {pomos} 个）")

    lit = db.query(LiteratureItem).filter(LiteratureItem.read_date.isnot(None), LiteratureItem.read_date >= monday).all()
    if lit:
        parts.append("本周读过的文献：\n" + "\n".join(f"- {i.title}（{i.year or '?'}）" for i in lit[:10]))

    exp = db.query(Experiment).order_by(Experiment.updated_at.desc()).limit(5).all()
    if exp:
        parts.append("实验记录（近期）：\n" + "\n".join(f"- {e.title}（{e.status}）" for e in exp))

    sl = db.query(StudyLog).filter(StudyLog.date >= monday).order_by(StudyLog.date.desc()).all()
    if sl:
        parts.append("本周学习轨迹：\n" + "\n".join(f"- {s.date} {s.content}" for s in sl[:10]))

    solves = db.query(OJSolve).filter(OJSolve.date >= monday).all()
    total_solves = db.query(OJSolve).count()
    if solves or total_solves:
        parts.append(f"本周刷题：{len(solves)} 题（累计记录 {total_solves} 题）")

    skills = db.query(Skill).all()
    if skills:
        lines = []
        for s in skills:
            total = round(sum(x.progress for x in s.stages) / len(s.stages)) if s.stages else 0
            stg = " / ".join(f"{x.name}{x.progress}%" for x in s.stages)
            lines.append(f"- {s.name}：{total}%（{stg}）")
        parts.append("技能进度：\n" + "\n".join(lines))

    days = db.query(AttendanceDay).filter(AttendanceDay.date >= monday).all()
    if days:
        parts.append(f"本周到岗：{len(days)} 天")

    return "\n\n".join(parts)


@router.post("/advisor-report")
def ai_advisor_report(db: Session = Depends(get_db)):
    """一键生成导师周报草稿（周五用，复制后发给导师）。"""
    _guard()
    context = _advisor_context(db)
    if not context.strip():
        raise HTTPException(400, "本周暂无数据可汇总")
    draft = _call("advisor-report", deepseek.generate_advisor_report, context)
    if not isinstance(draft, str) or not draft.strip():
        raise HTTPException(400, "AI 返回格式异常")
    return {"draft": draft.strip()}


@router.post("/recommend-literature")
def ai_recommend_literature(db: Session = Depends(get_db)):
    _guard()
    items = (
        db.query(LiteratureItem)
        .filter(LiteratureItem.read_status.in_(["unread", "reading"]))
        .order_by(LiteratureItem.created_at.desc())
        .limit(15)
        .all()
    )
    if not items:
        raise HTTPException(400, "没有待读文献，请先从 Zotero 同步")
    context = "\n".join(
        f"[{i.id}] {i.title}（{i.year or '?年'}，类型 {i.item_type}，标签：{i.tags or '无'}，摘要：{(i.abstract or '')[:200]}）"
        for i in items
    )
    recs = _call("recommend-literature", deepseek.recommend_literature, context)
    by_id = {i.id: i for i in items}
    out = []
    for r in recs[:5]:
        if not isinstance(r, dict):
            continue
        item = by_id.get(r.get("id"))
        if not item:
            continue
        out.append({"id": item.id, "title": item.title, "year": item.year, "reason": (r.get("reason") or "").strip()})
    return {"items": out}


# ---------- 笔记批量 AI 打标 ----------
@router.post("/note-tags")
def ai_note_tags(data: dict | None = None, db: Session = Depends(get_db)):
    import re

    _guard()
    limit = int((data or {}).get("limit") or 20)
    items = (
        db.query(Note)
        .filter(Note.deleted_at.is_(None), Note.tags == "")
        .order_by(Note.updated_at.desc())
        .limit(limit)
        .all()
    )
    if not items:
        raise HTTPException(400, "没有未打标的笔记")
    out = []
    for n in items:
        try:
            tags = deepseek.tag_literature(n.title, (n.content or "")[:500])
            raw = [t.strip() for t in re.split(r"[,，、;；\s]+", tags) if t.strip()]
            out.append({"id": n.id, "title": n.title, "suggested": raw[:6]})
            _record_ai("note-tags", f"笔记打标：{n.title}", tags[:3000])
        except AIError:
            break
        except Exception:
            continue
    return {"items": out}


@router.post("/note-tags/apply")
def apply_note_tags(data: dict, db: Session = Depends(get_db)):
    changes = data.get("changes") or []
    done = 0
    for c in changes:
        n = db.get(Note, c.get("id"))
        if n:
            tags = str(c.get("tags") or "").strip()
            n.tags = tags
            done += 1
    db.commit()
    return {"ok": True, "done": done}


# ---------- 通用 AI 对话（带知识库上下文 + 科研画像） ----------
@router.post("/chat")
def ai_chat(data: dict, db: Session = Depends(get_db)):
    _guard()
    messages = data.get("messages") or []
    if not messages or not messages[-1].get("content", "").strip():
        raise HTTPException(400, "请输入要问的问题")
    profile = _profile_block(db)
    user_last = messages[-1].get("content", "")[:200]
    # 自动检索知识库作为参考背景
    kb_lines = []
    try:
        _, kb = _search_kb(db, user_last, top=3)
        for k in kb:
            if isinstance(k, dict) and k.get("title"):
                kb_lines.append(f"· {k['title']}：{(k.get('snippet') or '')[:150]}")
    except Exception:
        pass
    context = ""
    if profile:
        context += profile + "\n"
    if kb_lines:
        context += "以下是用户知识库中可能相关的内容（回答时可引用，没有直接关系就忽略）：\n" + "\n".join(kb_lines)
    system = (
        "你是研究生的科研助手（红外小目标检测方向）。回复简洁、结构化、使用中文。"
        + (f"\n\n{context}" if context else "")
    )
    result = _call("chat", deepseek.chat, messages[-4:], system)
    return {"result": result}


# ---------- 批量 AI 处理 ----------
# ---------- 论文写作流水线 ----------
@router.post("/paper-outline")
def ai_paper_outline(data: dict, db: Session = Depends(get_db)):
    _guard()
    title = (data.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "请输入论文主题")
    direction = (data.get("direction") or "").strip()
    notes = (data.get("notes") or "").strip()
    profile = _profile_block(db)
    if profile and not direction:
        direction = profile
    result = _call("paper-outline", deepseek.paper_outline, title, direction, notes)
    return {"result": result}


@router.post("/paper-chapter")
def ai_paper_chapter(data: dict, db: Session = Depends(get_db)):
    _guard()
    title = (data.get("title") or "").strip()
    chapter = (data.get("chapter") or "").strip()
    if not title or not chapter:
        raise HTTPException(400, "请输入论文主题与章节")
    notes = (data.get("notes") or "").strip()
    kb = data.get("kb")
    if not kb:
        _, kb = _search_kb(db, f"{title} {chapter}", top=5)
    refs = []
    for k in kb:
        if isinstance(k, dict) and k.get("title"):
            refs.append(f"· {k['title']}：{(k.get('snippet') or '')[:200]}")
    result = _call("paper-chapter", deepseek.paper_chapter, title, chapter, notes, "\n".join(refs))
    return {"result": result}


@router.post("/paper-polish")
def ai_paper_polish(data: dict):
    _guard()
    text = (data.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "请输入要处理的文字")
    mode = data.get("mode") or "polish"
    result = _call("paper-polish", deepseek.paper_polish, text, mode)
    return {"result": result}


@router.post("/batch-tag")
def ai_batch_tag(data: dict | None = None, db: Session = Depends(get_db)):
    import re

    _guard()
    limit = int((data or {}).get("limit") or 50)
    items = (
        db.query(LiteratureItem)
        .filter(LiteratureItem.read_status != "read")
        .limit(limit)
        .all()
    )
    if not items:
        raise HTTPException(400, "没有待打标的文献")
    done = 0
    for it in items:
        try:
            tags = deepseek.tag_literature(it.title, it.abstract)
            raw = re.split(r"[,，、;；\s]+", tags)
            raw_existing = [t.strip() for t in it.tags.split(",") if t.strip()]
            existing_norm = {_norm_tag(t) for t in raw_existing}
            new = sorted({_norm_tag(t) for t in raw if t.strip()} - existing_norm)
            it.tags = ",".join(dict.fromkeys(raw_existing + new))
            done += 1
            _record_ai("batch-tag", f"批量打标：{it.title}", tags[:3000])
        except AIError:
            break
        except Exception:
            continue
    db.commit()
    return {"ok": True, "done": done, "total": len(items)}


@router.post("/batch-summarize")
def ai_batch_summarize(data: dict | None = None, db: Session = Depends(get_db)):
    _guard()
    limit = int((data or {}).get("limit") or 20)
    items = (
        db.query(LiteratureItem)
        .filter(LiteratureItem.ai_summary == "")
        .limit(limit)
        .all()
    )
    if not items:
        raise HTTPException(400, "没有需要总结的文献")
    done = 0
    for it in items:
        if not (it.abstract or "").strip():
            continue
        try:
            result = deepseek.summarize_text(f"文献标题：{it.title}\n摘要：{it.abstract}")
            it.ai_summary = result
            done += 1
            _record_ai("batch-summarize", f"批量总结：{it.title}", result[:3000])
        except AIError:
            break
        except Exception:
            continue
    db.commit()
    return {"ok": True, "done": done, "total": len(items)}


@router.post("/estimate-tasks")
def ai_estimate_tasks(data: dict | None = None, db: Session = Depends(get_db)):
    """AI 预估时长：
    - {ids: [任务id]}：预估指定任务（todo/doing 且未填 est_minutes）
    - {item_ids: [清单项id]}：预估今日清单项（写清单项自身 est_minutes；kind=task 有关联任务且未预估时归入任务渠道写 Task，任务已有预估则跳过）
    - {preview: true}：只返回预估结果不落库，供前端确认/修改后自行写入
    两者都不传时全库预估任务（向后兼容）。"""
    _guard()
    data = data or {}
    ids = [int(x) for x in (data.get("ids") or [])]
    item_ids = [int(x) for x in (data.get("item_ids") or [])]
    preview = bool(data.get("preview"))
    updated = 0
    result_tasks: dict = {}
    result_items: dict = {}

    task_rows = db.query(Task).filter(Task.status.in_(["todo", "doing"]), Task.est_minutes.is_(None))
    if ids:
        task_rows = task_rows.filter(Task.id.in_(ids))
    task_rows = task_rows.limit(50).all()

    d_rows: list = []
    if item_ids:
        dq = (
            db.query(DailyItem)
            .filter(DailyItem.status == "pending", DailyItem.est_minutes.is_(None), DailyItem.id.in_(item_ids))
            .limit(50)
            .all()
        )
        for it in dq:
            if it.kind == "task" and it.source_id:
                t = db.get(Task, it.source_id)
                if t and t.est_minutes is None:
                    if t.id not in [x.id for x in task_rows]:
                        task_rows.append(t)
                    continue
                if t and t.est_minutes is not None:
                    continue  # 任务已预估，清单项自动带出，无需再估
            d_rows.append(it)

    if not task_rows and not d_rows:
        raise HTTPException(400, "今日清单里的任务都已有时长预估")

    if task_rows:
        tasks = [
            {
                "id": t.id,
                "title": t.title,
                "type": {"habit": "习惯打卡", "study": "学习", "once": "一次性"}.get(t.task_type, t.task_type),
                "priority": t.priority,
                "due": t.due_date.isoformat() if t.due_date else "",
                "goal": t.goal.title if t.goal else "",
            }
            for t in task_rows
        ]
        result = _call("estimate-tasks", deepseek.estimate_task_times, tasks)
        for t in task_rows:
            mins = result.get(t.id)
            if mins:
                mins = max(5, min(1440, int(mins)))
                if preview:
                    result_tasks[t.id] = mins
                else:
                    t.est_minutes = mins
                    updated += 1
    if d_rows:
        items = [
            {
                "id": it.id,
                "title": it.content,
                "type": {"task": "任务", "habit": "习惯打卡", "literature": "读文献", "manual": "手动", "ai": "AI建议"}.get(it.kind, it.kind),
                "priority": it.weight,
                "due": it.due_date.isoformat() if it.due_date else "",
                "goal": "",
            }
            for it in d_rows
        ]
        result = _call("estimate-tasks", deepseek.estimate_task_times, items)
        for it in d_rows:
            mins = result.get(it.id)
            if mins:
                mins = max(5, min(1440, int(mins)))
                if preview:
                    result_items[it.id] = mins
                else:
                    it.est_minutes = mins
                    updated += 1
    if not preview:
        db.commit()
    return {
        "ok": True,
        "updated": updated,
        "total": len(task_rows) + len(d_rows),
        "tasks": {str(k): v for k, v in result_tasks.items()},
        "items": {str(k): v for k, v in result_items.items()},
    }
