"""Self_analysis 规划文件夹：递归扫描 + 结构化解析（只读）。

用户在「设置」中指定的学习/生活规划文件夹：
- plan/*.md   规划文档（00 总索引+进度表 / 01 三年规划 / 02 逐日清单 / 03 Python 路径 /
              04 大模型栈 / 05 周复盘+导师周报模板 / 06 研一上作战计划 / 07 算法刷题路径）
- 复盘/*.md 或 plan/复盘/*.md   周复盘历史（工作台导出或手写，读取兼容两种位置）

本模块把 plan 文档解析成结构化数据（当前阶段/本周目标/检查点/固定节奏/铁律/进度表），
并拼成可注入 AI prompt 的文本。**本模块只读文件**；回写操作在 routers/self_analysis.py
中经由备份 + 双重确认流程执行。

注意：解析失败/结构变化时降级为「全文截取」，保证 AI 总有上下文可用。
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

_HIDE_DIRS = {".git", "node_modules", "__pycache__", ".idea", ".vscode"}


# ---------------------------------------------------------------- 基础 IO
def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def scan(root: Path) -> list[Path]:
    """递归扫描文件夹下所有 md（排除隐藏目录）。"""
    root = Path(root)
    if not root.exists():
        return []
    out = []
    for f in root.rglob("*.md"):
        try:
            parts = f.relative_to(root).parts
        except ValueError:
            parts = (f.name,)
        if any(part in _HIDE_DIRS or part.startswith(".") for part in parts[:-1]):
            continue
        out.append(f)
    return sorted(out)


def _clean(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    return s.strip()


# ---------------------------------------------------------------- 日期
def _infer_date(text: str, today: date) -> date | None:
    """把 '9.30' / '10.13' / '2027.1.15' 解析为最接近今天的日期。"""
    m = re.search(r"(\d{4})[年./-](\d{1,2})(?:[月./-](\d{1,2}))?", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})[月./-](\d{1,2})", text)
    if not m:
        return None
    mo, d = int(m.group(1)), int(m.group(2))
    cands = []
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            cands.append(date(y, mo, d))
        except ValueError:
            continue
    if not cands:
        return None
    return min(cands, key=lambda x: abs((x - today).days))


# ---------------------------------------------------------------- Markdown 结构
def _section(text: str, kw: str) -> str | None:
    """取标题包含 kw 的章节正文（到下一个同级/更高级标题为止）。"""
    heads = list(re.finditer(r"^(#{1,6})[ \t]*(.+?)[ \t]*$", text, re.M))
    for idx, m in enumerate(heads):
        if kw in m.group(2):
            level = len(m.group(1))
            end = len(text)
            for nxt in heads[idx + 1:]:
                if len(nxt.group(1)) <= level:
                    end = nxt.start()
                    break
            return text[m.end():end]
    return None


def _list_items(block: str, numbered: bool = False) -> list[str]:
    """解析列表项（续行并入上一条），用于铁律/关键规则/情报。"""
    out: list[str] = []
    if not block:
        return out
    for line in block.splitlines():
        m = re.match(r"^\s*(\d+[.、]|[*-])\s+(.+)$", line)
        if m:
            out.append(_clean(m.group(2)))
        elif out and line.strip() and line.startswith((" ", "\t")) and not line.strip().startswith(("|", "```", "#")):
            tail = _clean(line)
            if tail:
                out[-1] += " " + tail
    return out


def _code_blocks(block: str) -> list[str]:
    return re.findall(r"```[^\n]*\n(.*?)```", block, re.S)


def _table_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        body = [c for c in cells if c]
        if not body:
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in body):
            continue
        rows.append(cells)
    return rows


_HEADER_WORDS = {"项目", "状态", "差距", "节点", "时间", "前置条件", "模块", "目标时间", "备注",
                 "检查点", "日期", "必须达成", "文件", "内容", "使用时机"}


def _is_header(row: list[str]) -> bool:
    return bool(row) and all((c in _HEADER_WORDS) or c == "" for c in row)


# ---------------------------------------------------------------- 各文档解析
_PHASE_RE = re.compile(r"^#{3,4}\s*阶段(P\d)[（(]([^）)]*)[）)][：:]?\s*(.*)$", re.M)
_WEEK_ROW_RE = re.compile(r"^\|\s*第\s*(\d+)\s*周\s*[（(]([^）)]*)[）)]\s*\|\s*([^|]*)\|\s*([^|]*)\|", re.M)
_CKPT_ROW_RE = re.compile(r"^\|\s*(M\d)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", re.M)
_RHYTHM_RE = re.compile(r"(\d{1,2}:\d{2})\s*[-–~]\s*(\d{1,2}:\d{2})\s+(.+)")


def _parse_phases(t06: str, today: date) -> list[dict]:
    out = []
    for m in _PHASE_RE.finditer(t06):
        pid, rng, title = m.group(1), m.group(2), _clean(m.group(3))
        dates = re.findall(r"(\d{1,2}\.\d{1,2})", rng)
        start = _infer_date(dates[0], today) if dates else None
        end = _infer_date(dates[1], today) if len(dates) > 1 else None
        tail = t06[m.end(): m.end() + 400]
        gm = re.search(r"\*\*目标[：:]\s*(.+?)\*\*", tail)
        goal = _clean(gm.group(1)) if gm else ""
        out.append({"id": pid, "range": rng, "title": title, "goal": goal, "start": start, "end": end})
    return out


def _parse_weeks(t06: str, today: date) -> list[dict]:
    out = []
    for m in _WEEK_ROW_RE.finditer(t06):
        n = int(m.group(1))
        rng = m.group(2)
        dates = re.findall(r"(\d{1,2}\.\d{1,2})", rng)
        start = _infer_date(dates[0], today) if dates else None
        end = _infer_date(dates[1], today) if len(dates) > 1 else None
        out.append({"n": n, "range": rng, "paper": _clean(m.group(3)), "tech": _clean(m.group(4)),
                    "start": start, "end": end})
    return out


def _parse_checkpoints(t06: str, today: date) -> list[dict]:
    out = []
    for m in _CKPT_ROW_RE.finditer(t06):
        d = _infer_date(m.group(2), today)
        out.append({"id": m.group(1), "date_text": _clean(m.group(2)), "date": d, "content": _clean(m.group(3))})
    return out


def _parse_rhythm(t06: str) -> tuple[list[dict], list[str]]:
    sec = _section(t06, "每周固定节奏") or ""
    rhythm, notes = [], []
    blocks = _code_blocks(sec) or [sec]
    for block in blocks:
        for line in block.splitlines():
            line = line.rstrip()
            if not line.strip():
                continue
            m = _RHYTHM_RE.search(line)
            if m:
                rhythm.append({"time": f"{m.group(1)}-{m.group(2)}", "what": _clean(m.group(3))})
            elif "：" in line or ":" in line:
                notes.append(_clean(line))
    return rhythm, notes


def _parse_progress(t00: str) -> list[dict]:
    sec = _section(t00, "当前真实进度") or ""
    out = []
    for row in _table_rows(sec):
        if _is_header(row) or not row[0]:
            continue
        out.append({"item": _clean(row[0]), "status": _clean(row[1]) if len(row) > 1 else "",
                    "gap": _clean(row[2]) if len(row) > 2 else ""})
    return out


def _parse_lines(t06: str) -> list[dict]:
    sec = _section(t06, "三条主线") or ""
    out = []
    for block in _code_blocks(sec):
        for line in block.splitlines():
            s = _clean(line)
            if not s:
                continue
            m = re.match(r"^(.+?)\s*[：:]\s*(.+)$", s)
            if m:
                out.append({"name": m.group(1).strip(), "desc": m.group(2).strip()})
    return out


def _parse_nodes(t01: str) -> list[dict]:
    sec = _section(t01, "生死节点") or ""
    out = []
    for row in _table_rows(sec):
        if _is_header(row) or not row[0]:
            continue
        out.append({"name": _clean(row[0]), "when": _clean(row[1]) if len(row) > 1 else "",
                    "need": _clean(row[2]) if len(row) > 2 else ""})
    return out


def _parse_timeline(t01: str) -> list[str]:
    sec = _section(t01, "三年时间线") or ""
    out = []
    for block in _code_blocks(sec):
        for line in block.splitlines():
            s = _clean(line)
            if s:
                out.append(s)
    return out


def _parse_skill_targets(t01: str) -> list[dict]:
    sec = _section(t01, "技能树") or ""
    out = []
    for row in _table_rows(sec):
        if _is_header(row) or not row[0]:
            continue
        out.append({"skill": _clean(row[0]), "target": _clean(row[1]) if len(row) > 1 else "",
                    "note": _clean(row[2]) if len(row) > 2 else ""})
    return out


# ---------------------------------------------------------------- 文件选择
def _pick(texts: dict[str, str], token: str, keywords: tuple[str, ...]) -> str:
    for name, t in texts.items():
        if Path(name).name.startswith(token):
            return t
    for t in texts.values():
        head = t[:2000]
        if keywords and all(k in head for k in keywords):
            return t
    for t in texts.values():
        head = t[:2000]
        if keywords and any(k in head for k in keywords):
            return t
    return ""


def load(root: Path, today: date | None = None) -> dict:
    """结构化加载整个文件夹（只读）。"""
    today = today or date.today()
    root = Path(root)
    files = scan(root)
    texts: dict[str, str] = {}
    for f in files:
        try:
            rel = f.relative_to(root)
        except ValueError:
            rel = Path(f.name)
        texts[str(rel).replace("\\", "/")] = _read(f)
    if not texts:
        return {"root": str(root), "today": today.isoformat(), "files": [], "empty": True}

    t00 = _pick(texts, "00", ("总索引", "当前真实进度"))
    t01 = _pick(texts, "01", ("三年总体规划",))
    t06 = _pick(texts, "06", ("作战计划", "三条主线"))

    phases = _parse_phases(t06, today)
    weeks = _parse_weeks(t06, today)
    checkpoints = _parse_checkpoints(t06, today)
    rhythm, rhythm_notes = _parse_rhythm(t06)

    current_phase = None
    for p in phases:
        if p["start"] and p["end"] and p["start"] <= today <= p["end"]:
            current_phase = p
            break
    if current_phase is None and phases:
        if today < (phases[0]["start"] or today):
            current_phase = None
        else:
            current_phase = phases[-1]
            current_phase = {**current_phase, "passed": True}

    current_week = None
    for w in weeks:
        if w["start"] and w["end"] and w["start"] <= today <= w["end"]:
            current_week = w
            break
    if current_week is None and weeks and weeks[0]["start"] and today >= weeks[0]["start"]:
        # 按天推算第几周（表格未覆盖时兜底）
        n = (today - weeks[0]["start"]).days // 7 + 1
        for w in weeks:
            if w["n"] == n:
                current_week = w
                break

    next_ckpt = None
    for c in checkpoints:
        if c["date"] and c["date"] >= today:
            next_ckpt = c
            break
    if next_ckpt is None and checkpoints:
        next_ckpt = checkpoints[-1]

    # 兼容根目录 复盘/ 与 plan/复盘/ 两种存放位置（05 模板手写在 plan/复盘/）
    reviews = [k for k in texts if "复盘" in Path(k).parts]

    return {
        "root": str(root),
        "today": today.isoformat(),
        "files": list(texts.keys()),
        "empty": False,
        "phase": current_phase,
        "phases": phases,
        "week": current_week,
        "weeks": weeks,
        "checkpoints": checkpoints,
        "next_checkpoint": next_ckpt,
        "rhythm": rhythm,
        "rhythm_notes": rhythm_notes,
        "iron_rules": _list_items(_section(t00, "铁律") or "", numbered=True),
        "key_info": _list_items(_section(t00, "情报") or "", numbered=True),
        "key_rules": _list_items(_section(t06, "关键规则") or "", numbered=True),
        "progress": _parse_progress(t00),
        "lines": _parse_lines(t06),
        "nodes": _parse_nodes(t01),
        "timeline": _parse_timeline(t01),
        "skill_targets": _parse_skill_targets(t01),
        "reviews": sorted(reviews),
    }


# ---------------------------------------------------------------- 注入 AI 的文本
def _format_prompt(d: dict) -> str:
    seg: list[str] = []
    seg.append("【作战计划 · Self_analysis 结构化提取】（所有今日建议都必须服务于以下阶段/周目标/节奏，不要跑题）")

    p = d.get("phase")
    if p:
        line = f"当前阶段：{p['id']} {p.get('title', '')}（{p.get('range', '')}）"
        if p.get("goal"):
            line += f"｜阶段目标：{p['goal']}"
        if p.get("passed"):
            line += "（该阶段已结束，请提示用户更新计划）"
        seg.append(line)
    w = d.get("week")
    if w:
        seg.append(f"本周：第{w['n']}周（{w.get('range', '')}）")
        if w.get("paper"):
            seg.append(f"  · 论文线本周目标：{w['paper']}")
        if w.get("tech"):
            seg.append(f"  · 技术线本周目标：{w['tech']}")

    ck = d.get("next_checkpoint")
    if ck and ck.get("date"):
        days = (ck["date"] - date.fromisoformat(d["today"])).days
        tail = f"，剩 {days} 天" if days >= 0 else f"（已过 {-days} 天）"
        seg.append(f"最近检查点：{ck['id']}（{ck['date_text']}{tail}）：{ck['content']}")
    later = [c for c in d.get("checkpoints", []) if c is not d.get("next_checkpoint")][:3]
    if later:
        seg.append("后续检查点：" + "；".join(f"{c['id']} {c['date_text']} {c['content'][:40]}" for c in later))

    if d.get("rhythm"):
        seg.append("每日固定节奏（安排任务时尽量让时间落在对应时间段，并在 time_range 里体现）：")
        for r in d["rhythm"]:
            seg.append(f"  · {r['time']} {r['what']}")
    if d.get("rhythm_notes"):
        seg.append("周节奏备注：" + "；".join(d["rhythm_notes"][:6]))

    if d.get("iron_rules"):
        seg.append("本周铁律：" + "；".join(d["iron_rules"][:8]))
    if d.get("key_info"):
        seg.append("关键情报：" + "；".join(d["key_info"][:5]))
    if d.get("key_rules"):
        seg.append("长期关键规则：" + "；".join(d["key_rules"][:8]))

    if d.get("lines"):
        seg.append("三条主线：" + "；".join(f"{x['name']}={x['desc'][:60]}" for x in d["lines"][:4]))
    if d.get("nodes"):
        seg.append("三大生死节点：" + "；".join(f"{n['name']}（{n['when']}）" for n in d["nodes"][:4]))
    if d.get("skill_targets"):
        seg.append("技能目标：" + "；".join(f"{s['skill']}={s['target']}" for s in d["skill_targets"][:8]))
    if d.get("progress"):
        seg.append("当前进度（记录于文档中，可能滞后于实际）："
                   + "；".join(f"{p['item']}={p['status']}" for p in d["progress"][:8]))
    if d.get("reviews"):
        seg.append(f"复盘历史：已有 {len(d['reviews'])} 份（最近：{d['reviews'][-1]}）")
    return "\n".join(seg)


def _raw_dump(root: Path, limit_files: int = 8, limit_chars: int = 3000) -> str:
    parts = []
    for f in scan(root)[:limit_files]:
        txt = _read(f)[:limit_chars]
        if txt:
            parts.append(f"## {f.name}\n{txt}")
    return "\n\n".join(parts)


def build_prompt(root: Path, today: date | None = None) -> str:
    """拼给 AI 的上下文；结构解析失败时降级为全文截取。"""
    try:
        d = load(root, today)
    except Exception:
        return ""
    if d.get("empty"):
        return ""
    text = _format_prompt(d)
    if text.strip() and (d.get("phase") or d.get("week") or d.get("rhythm") or d.get("checkpoints")):
        return text
    return _raw_dump(Path(root))


# ---------------------------------------------------------------- 每日清单解析（导入用）
def _date_headings(text: str, today: date) -> list[dict]:
    """找出『## 9.30（周三）』这类按日期分节的标题。"""
    out = []
    heads = list(re.finditer(r"^(#{2,4})[ \t]*(.+?)[ \t]*$", text, re.M))
    for i, m in enumerate(heads):
        heading = m.group(2).strip()
        dm = re.match(r"^(\d{1,2}\.\d{1,2})", heading)
        if not dm:
            continue
        days = re.findall(r"(\d{1,2}\.\d{1,2})", heading)
        ds = [x for x in (_infer_date(x, today) for x in days) if x]
        if not ds:
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append({"heading": heading, "start": m.start(), "body_start": m.end(), "end": end,
                    "dates": ds, "first": ds[0], "last": ds[-1]})
    return out


def parse_daily_tasks(root: Path, today: date | None = None) -> list[dict]:
    """解析 02 逐日清单的 checkbox → [{date, content, checked, file, section, line}]。

    - 行内显式日期（如『10.6（周二）：…』）优先；
    - 含『每天』的条目在多天区间内逐日展开；
    - 其余归到所在小节的第一天。
    """
    today = today or date.today()
    root = Path(root)
    texts = {}
    for f in scan(root):
        try:
            rel = str(f.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = f.name
        texts[rel] = _read(f)
    f02 = _pick(texts, "02", ("每日任务清单", "本周核心"))
    if not f02:
        return []
    fname = next((k for k in texts if Path(k).name.startswith("02")), "")
    if not fname:
        fname = next((k for k, v in texts.items() if v == f02), "")
    out: list[dict] = []
    for sec in _date_headings(f02, today):
        seg = f02[sec["body_start"]:sec["end"]]
        for line in seg.splitlines():
            m = re.match(r"^-\s*\[( |x|X)\]\s*(.+?)\s*$", line)
            checked = False
            content = ""
            if m:
                checked = m.group(1).lower() == "x"
                content = m.group(2).strip()
            else:
                m2 = re.match(r"^-\s+(.+?)\s*$", line)
                if not m2:
                    continue
                content = m2.group(1).strip()
            if not content:
                continue
            # 行内显式日期
            dm = re.match(r"^(\d{1,2}\.\d{1,2})[（(]?[^0-9]*[）)]?[：:]\s*(.+)$", content)
            target_dates = []
            if dm:
                dd = _infer_date(dm.group(1), today)
                if dd:
                    target_dates = [dd]
                    content = dm.group(2).strip()
            if not target_dates:
                if "每天" in content and sec["last"] > sec["first"]:
                    d = sec["first"]
                    while d <= sec["last"]:
                        target_dates.append(d)
                        d = date.fromordinal(d.toordinal() + 1)
                else:
                    target_dates = [sec["first"]]
            for d in target_dates:
                out.append({"date": d, "content": _clean(content), "checked": checked,
                            "file": fname, "section": sec["heading"], "line": line.strip()})
    return out


def parse_skill_specs(root: Path) -> list[dict]:
    """从 03/04 学习路径 + 01 技能树生成技能栈导入定义（幂等导入用）。"""
    root = Path(root)
    texts: dict[str, str] = {}
    for f in scan(root):
        try:
            rel = str(f.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = f.name
        texts[rel] = _read(f)
    t01 = _pick(texts, "01", ("三年总体规划",))
    t03 = _pick(texts, "03", ("Python 学习路径",))
    t04 = _pick(texts, "04", ("大模型技术栈",))
    t00 = _pick(texts, "00", ("当前真实进度",))

    specs: list[dict] = []
    st3 = [s.strip() for s in re.findall(r"^##\s*阶段\d+[：:]\s*([^（(]+)", t03, re.M)]
    if st3:
        specs.append({"name": "Python 工程能力", "source": "03_Python学习路径", "stages": st3})
    st4 = [s.strip() for s in re.findall(r"^##\s*第\d+层[：:]\s*([^（(]+)", t04, re.M)]
    if st4:
        specs.append({"name": "大模型技术栈", "source": "04_大模型技术栈", "stages": st4})

    pytorch_initial: dict = {}
    for row in _parse_progress(t00):
        if "PyTorch" in row["item"]:
            m = re.search(r"(\d{1,3})\s*%", row.get("status", ""))
            if m:
                pytorch_initial = {"基础（小土堆）": min(100, int(m.group(1)))}

    for row in _parse_skill_targets(t01):
        nm = row["skill"]
        if any(k in nm for k in ("Python", "LeetCode", "大模型", "多模态")):
            continue
        if "PyTorch" in nm:
            specs.append({"name": "PyTorch", "source": "01_技能树", "initial": pytorch_initial,
                          "stages": ["基础（小土堆）", "MNIST 独立跑通", "CNN/注意力", "项目实战"]})
        elif "DL" in nm or "深度学习" in nm:
            specs.append({"name": "深度学习系统课（李沐）", "source": "01_技能树",
                          "stages": ["第1-3章", "第4-6章", "第7-8章", "Transformer"]})
        elif "论文" in nm:
            specs.append({"name": "论文/科研", "source": "01_技能树",
                          "stages": ["文献攻坚", "确定改进点", "复现 baseline", "实验对比", "写作投稿"]})
    return specs


# ---------------------------------------------------------------- 复盘/进度块渲染
def plan_week_number(d: date, weeks: list[dict]) -> int | None:
    for w in weeks:
        if w["start"] and w["end"] and w["start"] <= d <= w["end"]:
            return w["n"]
    if weeks and weeks[0]["start"] and d >= weeks[0]["start"]:
        return (d - weeks[0]["start"]).days // 7 + 1
    return None


def render_review_md(week_start: date, week_end: date, week_no: int | None,
                     content: dict, stats: dict) -> str:
    """按 05 模板渲染周复盘 md（工作台导出用）。"""
    c = content or {}
    title = f"第{week_no}周复盘" if week_no else "周复盘"
    lines = [
        f"# {title}（日期：{week_start} - {week_end}）",
        "",
        "## 1. 目标完成度",
        f"- 本周计划了 {stats.get('planned', 0)} 件事，完成 {stats.get('done_count', 0)} 件"
        f"（完成率 {stats.get('percent', 0)}%）",
        f"- 未完成的原因：{c.get('problems', '') or '（待补充）'}",
        "",
        "## 2. 本周学到（技术 / 认知）",
        "",
    ]
    lines += [f"- {x}" for x in (c.get("progress", "") or "").split("\n") if x.strip()] or ["- "]
    lines += [
        "",
        "## 3. 卡点 & 解决",
        f"- 卡在哪：{c.get('problems', '')}",
        f"- 改进措施：{c.get('improvements', '')}",
        "",
        "## 4. 情绪与状态（1-10，附一句原因）",
        f"- 本周心理状态：{c.get('mood', '') or '（待补充）'}",
        "",
        "## 5. 量化数据（工作台自动统计）",
        f"- 投入时长：{stats.get('focus_text', '0 分钟')}（番茄 {stats.get('pomodoros', 0)} 个）",
        f"- 完成任务：{stats.get('done_count', 0)} 个",
        f"- 打卡/习惯：{stats.get('checkin_days', 0)} 天",
        f"- 文献阅读：本周 {stats.get('lit_read', 0)} 篇",
        f"- 刷题：本周 {stats.get('oj_week', 0)} 题（累计 {stats.get('oj_total', 0)} 题）",
        f"- 在岗时间：{stats.get('attendance_text', '0 分钟')}",
        "",
        "## 6. 下周最重要的3件事",
        "",
    ]
    todo_lines = [f"{i + 1}. {x.strip('0123456789.、 ')}"
                  for i, x in enumerate((c.get("todo", "") or "").split("\n")) if x.strip()]
    lines += todo_lines or ["1. ", "2. ", "3. "]
    lines += [
        "",
        "## 7. 对AI教练的问题",
        f"- {c.get('ai_question', '') or '（待补充）'}",
    ]
    return "\n".join(lines).rstrip() + "\n"
