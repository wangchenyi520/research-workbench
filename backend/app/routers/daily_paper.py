# -*- coding: utf-8 -*-
"""每日论文推荐：每天精选一篇红外小目标检测领域论文（OpenAlex 检索 + AI 中文导读）。

流程：首次打开工作台懒生成（POST /generate，当天唯一、幂等）→
OpenAlex 检索候选（真实引用数，失败降级 arXiv）→ 与文献库/历史推荐去重 →
DeepSeek 挑选 + 生成中文导读（无 key 时启发式降级）→ 存库 + 桌面通知。
支持：三档评价（rate）、标记已读（read）、一键入库（archive → LiteratureItem）。
"""

import json
import logging
import re
import threading
from datetime import date
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import DAILY_PAPER_DIR
from ..database import get_db
from ..models import DailyPaper, Goal, LiteratureItem, Setting
from ..services import deepseek, paper_sources, zotero
from ..services.deepseek import AIError
from ..services.notification import notify

router = APIRouter(prefix="/api/daily-paper", tags=["daily-paper"])

LEVEL_ORDER = {"week": 0, "month": 1, "quarter": 2, "annual": 3}
RATINGS = {"useful", "general", "not_interested", ""}
ZOTERO_COLLECTION_NAME = "红外小目标检测每日论文推荐"  # 用户自建集合：所有每日论文推送到这里

_gen_lock = threading.Lock()  # 生成互斥：防止前端懒生成与调度器兜底并发双跑


def serialize(p: DailyPaper) -> dict:
    try:
        authors = json.loads(p.authors or "[]")
    except Exception:
        authors = []
    return {
        "id": p.id,
        "paper_date": p.paper_date.isoformat(),
        "title": p.title,
        "authors": authors,
        "year": p.year,
        "publication": p.publication,
        "doi": p.doi,
        "url": p.url,
        "citation_count": p.citation_count,
        "abstract": p.abstract,
        "summary": p.summary,
        "why_read": p.why_read,
        "relation": p.relation,
        "rating": p.rating,
        "read": p.read,
        "literature_id": p.literature_id,
        "pdf_file": p.pdf_file,
        "zotero_key": p.zotero_key or "",
        "zotero_pdf_key": p.zotero_pdf_key or "",
        "source": p.source,
        "created_at": p.created_at.isoformat(),
    }


def _enabled(db: Session) -> bool:
    s = db.get(Setting, "daily_paper_enabled")
    return (s.value if s else "true") != "false"


def _zotero_auto_enabled(db: Session) -> bool:
    """自动存入 Zotero 开关（daily_paper_zotero，默认开）。"""
    s = db.get(Setting, "daily_paper_zotero")
    return (s.value if s else "true") != "false"


def _paper_type(publication: str) -> str:
    """按期刊/会议名判断 Zotero itemType。"""
    pub = (publication or "").lower()
    if "arxiv" in pub or "preprint" in pub:
        return "preprint"
    if "conference" in pub or "proceedings" in pub:
        return "conferencePaper"
    return "journalArticle"


def _zotero_err_text(e: Exception) -> str:
    """把推送异常转成简短可读提示。"""
    msg = ""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code in (403, 401):
            msg = "Zotero API Key 无效或无写入权限"
        elif code in (429,):
            msg = "Zotero API 限流"
        else:
            msg = f"Zotero API 返回 {code}"
    elif isinstance(e, httpx.TimeoutException):
        msg = "连接 Zotero 超时"
    else:
        msg = str(e) or e.__class__.__name__
    return msg[:120]


def _date_tag(p: DailyPaper) -> str:
    """推荐日期标签，如「推荐9月6日」（用户要求方便回看哪天推荐）。"""
    d = p.paper_date
    return f"推荐{d.month}月{d.day}日"


def _read_tag(p: DailyPaper) -> str:
    return "已读" if p.read else "未读"


def _zotero_tags(p: DailyPaper) -> list[str]:
    """推送到 Zotero 的标签：领域 + 来源 + 推荐日期 + 阅读状态。"""
    return ["红外小目标", "每日推荐", _date_tag(p), _read_tag(p)]


def _ensure_zotero_tags(p: DailyPaper, collection_key: str = "") -> str:
    """给已在 Zotero 的条目补齐「领域 + 来源 + 推荐日期 + 已读/未读」标签（幂等，返回 warning 或空）。"""
    if not (p.zotero_key and zotero.is_configured()):
        return ""
    try:
        zotero.update_item_tags(
            p.zotero_key,
            add=_zotero_tags(p),
            remove=["未读" if p.read else "已读"],
            collection_key=collection_key,
        )
        return ""
    except Exception as e:
        return _zotero_err_text(e)


def _push_to_zotero(db: Session, p: DailyPaper, attach_pdf: bool = True) -> str:
    """把一篇每日论文推送到用户 Zotero 库（集合：红外小目标检测每日论文推荐）。

    - 幂等：p.zotero_key 已记录（推送过）→ 直接返回，不重复创建
    - 未配置 Zotero Key/User ID → 抛 ValueError（调用方决定静默或提示）
    - 成功：回填 p.zotero_key（附件成功再回填 zotero_pdf_key）并 commit
    - 标签含「推荐M月D日」「已读/未读」，方便回看哪天推荐、哪些没读
    - 失败：抛出（条目失败后 p 无 key，下次可重推；附件失败只回填条目 key，可补挂）
    """
    if p.zotero_key:
        return p.zotero_key
    collection_key = zotero.ensure_collection(ZOTERO_COLLECTION_NAME)
    try:
        authors = json.loads(p.authors or "[]")
    except Exception:
        authors = []
    item = zotero.build_paper_item(
        title=p.title,
        authors=authors,
        year=p.year,
        publication=p.publication,
        doi=p.doi,
        url=p.url,
        abstract=p.abstract,
        tags=_zotero_tags(p),
        item_type=_paper_type(p.publication),
        collection_key=collection_key,
    )
    item_key = zotero.push_item(item)
    if not item_key:
        raise ValueError("Zotero 未返回条目 key")
    p.zotero_key = item_key
    # PDF 附件：本地已下载且条目下还没挂附件时上传（尽力而为，失败不影响条目）
    if attach_pdf and p.pdf_file and not p.zotero_pdf_key:
        f = DAILY_PAPER_DIR / Path(p.pdf_file).name
        if f.exists():
            try:
                p.zotero_pdf_key = zotero.push_pdf_attachment(item_key, f)
            except Exception as e:
                logging.getLogger("workbench").warning(
                    "每日论文 PDF 附件上传 Zotero 失败（题录已推，可稍后补挂）：%s", _zotero_err_text(e)
                )
                p.zotero_pdf_key = None
    db.commit()
    return item_key


def _adopt_existing_zotero_key(db: Session, p: DailyPaper) -> bool:
    """认领 Zotero 里已存在的同标题条目（本地文献库有 zotero_key，如用户手动导入后同步回填）。

    避免「论文已在用户 Zotero 库中，工作台又推一次」造成重复条目。
    返回 True 表示认领成功（或本就有 key）。
    """
    if p.zotero_key:
        return True
    lit = (
        db.query(LiteratureItem)
        .filter(LiteratureItem.title == p.title, LiteratureItem.zotero_key.isnot(None))
        .first()
    )
    if not lit:
        return False
    p.zotero_key = lit.zotero_key
    if not p.literature_id:
        p.literature_id = lit.id
    db.commit()
    return True


def _norm_title(t: str) -> str:
    import re

    return re.sub(r"[\s\-_.,:：，。]", "", (t or "").lower())


def _build_context(db: Session) -> str:
    """用户科研画像 + 当前阶段目标（周>月>季>年，覆盖今天）。"""
    parts = []
    s = db.get(Setting, "research_profile")
    raw = (s.value if s else "") or ""
    try:
        p = json.loads(raw) if raw else {}
    except Exception:
        p = {}
    for k, label in (
        ("direction", "研究方向"),
        ("methods", "常用方法/工具"),
        ("stage", "当前阶段"),
        ("goal", "毕业/近期目标"),
    ):
        if str(p.get(k) or "").strip():
            parts.append(f"{label}：{p.get(k)}")
    today = date.today()
    covering = []
    for g in db.query(Goal).filter(Goal.status == "active").all():
        start_ok = (not g.period_start) or g.period_start <= today
        end_ok = (not g.period_end) or g.period_end >= today
        if start_ok and end_ok:
            covering.append(g)
    covering.sort(key=lambda g: LEVEL_ORDER.get(g.level, 9))
    if covering:
        lines = []
        for g in covering[:3]:
            lines.append(f"- {g.title}" + (f"（{g.period_start}~{g.period_end}）" if g.period_start or g.period_end else ""))
        parts.append("当前阶段目标：\n" + "\n".join(lines))
    if not parts:
        return ""
    return "用户背景：\n" + "\n".join(parts)


def _pick_fallback(candidates: list[dict]) -> dict:
    """无 DeepSeek key 时的启发式挑选：综合引用数与新颖度（近 2 年给加权分）。"""
    today_year = date.today().year
    best = None
    best_score = -1
    for c in candidates:
        cites = c.get("citation_count") or 0
        recent = (c.get("year") or 0) >= today_year - 2
        score = cites + (200 if recent else 0)
        if score > best_score:
            best_score = score
            best = c
    return best or candidates[0]


@router.get("/today")
def today_paper(db: Session = Depends(get_db)):
    p = db.query(DailyPaper).filter(DailyPaper.paper_date == date.today()).first()
    return serialize(p) if p else None


@router.post("/generate")
def generate_paper(db: Session = Depends(get_db)):
    """生成今天的推荐论文（幂等：当天已有直接返回，不重复弹窗）。"""
    if not _enabled(db):
        raise HTTPException(400, "每日论文推荐已在设置中关闭")
    return _do_generate(db)


def _do_generate(db: Session) -> dict:
    """生成今天的推荐论文（幂等 + 并发安全），供端点与调度器复用。

    - 当天已有 → 直接返回（不重检索、不重复弹窗）
    - 真正生成时：检索 → 去重 → AI/启发式挑选 → 落库 → 下载 PDF → 桌面通知
    - 进程内锁 + daily_papers.paper_date 唯一约束兜底：前端懒生成与调度器
      并发触发时只有一个会真正生成，另一个返回已生成的记录
    """
    with _gen_lock:
        existing = db.query(DailyPaper).filter(DailyPaper.paper_date == date.today()).first()
        if existing:
            return serialize(existing)

        candidates, source = paper_sources.fetch_candidates()
        if not candidates:
            raise HTTPException(502, "论文数据源暂不可用（OpenAlex/arXiv 均无响应），请稍后再试")

        # 去重：跳过文献库已有 / 历史推荐过的标题
        exclude: set[str] = set()
        for t in db.query(LiteratureItem.title).all():
            if t[0]:
                exclude.add(_norm_title(t[0]))
        for t in db.query(DailyPaper.title).all():
            if t[0]:
                exclude.add(_norm_title(t[0]))
        cands = [c for c in candidates if _norm_title(c.get("title", "")) not in exclude]
        if not cands:
            raise HTTPException(400, "今天的候选论文都已在文献库或推荐过，换个检索词或明天再来")
        candidates = cands

        context = _build_context(db)
        chosen = None
        guide = {}
        try:
            guide = deepseek.daily_paper_guide(candidates, context)
            if isinstance(guide, dict) and guide.get("paper"):
                matched = next(
                    (c for c in candidates if _norm_title(c.get("title")) == _norm_title(guide["paper"])),
                    None,
                )
                if matched:
                    chosen = matched
        except AIError:
            pass  # 无 key / AI 失败 → 启发式降级
        if chosen is None:
            chosen = _pick_fallback(candidates)
            guide = {}
            no_key = not deepseek.is_configured()
            guide["summary"] = (
                "未配置 DeepSeek API Key，暂无法生成 AI 中文导读。这是一篇领域内值得关注的论文，"
                "配置 API Key 后可获得 AI 精挑与导读。"
                if no_key
                else "AI 导读生成失败，已按引用数/年份自动选择，可在设置页检查 API Key 后重新生成。"
            )
            guide["why_read"] = f"领域内{'高引' if (chosen.get('citation_count') or 0) >= 100 else '最新'}论文（{chosen.get('year') or '年份未知'}）"
            guide["relation"] = "与你的红外小目标检测研究方向直接相关"

        p = DailyPaper(
            paper_date=date.today(),
            title=chosen["title"],
            authors=json.dumps(chosen.get("authors") or [], ensure_ascii=False),
            year=chosen.get("year"),
            publication=chosen.get("publication") or "",
            doi=chosen.get("doi") or "",
            url=chosen.get("url") or "",
            citation_count=chosen.get("citation_count"),
            abstract=chosen.get("abstract") or "",
            summary=guide.get("summary") or "",
            why_read=guide.get("why_read") or "",
            relation=guide.get("relation") or "",
            source=chosen.get("source") or source,
        )
        db.add(p)
        try:
            db.flush()
        except IntegrityError:
            # 并发双跑：另一请求已插入今天的论文（paper_date 唯一）→ 返回已有的
            db.rollback()
            existing = (
                db.query(DailyPaper).filter(DailyPaper.paper_date == date.today()).first()
            )
            if existing:
                return serialize(existing)
            raise
        db.commit()
        db.refresh(p)

        # 自动下载论文 PDF 到 daily_paper 目录（尽力而为，失败不阻塞推荐）
        try:
            prefix = f"{date.today().isoformat()}_{paper_sources._safe_filename(p.title)}".replace(" ", "_")
            pdf_name = paper_sources.download_pdf(chosen.get("pdf_url") or "", DAILY_PAPER_DIR, prefix)
            if pdf_name:
                p.pdf_file = pdf_name
                db.commit()
        except Exception:
            pass
        db.refresh(p)

        # 自动推送到 Zotero（开关打开且已配置 Key 时；失败不影响推荐本体，可稍后手动补推）
        try:
            if _zotero_auto_enabled(db) and zotero.is_configured():
                if _adopt_existing_zotero_key(db, p):
                    # 论文此前已被手动导入 Zotero → 认领并补标签/集合，不重复创建
                    _ensure_zotero_tags(p, collection_key=zotero.ensure_collection(ZOTERO_COLLECTION_NAME))
                else:
                    _push_to_zotero(db, p)
        except Exception as e:
            logging.getLogger("workbench").warning(
                "每日论文自动推送 Zotero 失败（可在每日论文页用「同步文件夹到 Zotero」重试）：%s",
                _zotero_err_text(e),
            )

        try:
            cites = p.citation_count
            cites_txt = f"，引用 {cites}" if cites else ""
            notify("📄 今日论文推荐", f"《{p.title[:30]}》已为你精选（{p.year or '?'}{cites_txt}），去读读看吧", "#/daily-paper")
        except Exception:
            pass
        return serialize(p)


@router.get("/history")
def paper_history(db: Session = Depends(get_db)):
    rows = db.query(DailyPaper).order_by(DailyPaper.paper_date.desc()).limit(90).all()
    return [serialize(p) for p in rows]


def _match_paper_for_file(filename: str, papers: list[DailyPaper]) -> tuple[DailyPaper | None, str]:
    """把文件夹里的 PDF 匹配到某篇每日论文，返回 (paper, match_type)。

    匹配优先级：①数据库已记录的 pdf_file 同名 → recorded；
    ②文件名前缀 YYYY-MM-DD 命中的 paper_date → date；
    ③文件名归一化后包含论文标题 → title；否则 None。
    （手动从出版商下载的乱名文件多数匹配不上，由前端手动关联。）
    """
    stem = Path(filename).stem
    for p in papers:  # ① 已登记文件
        if p.pdf_file and Path(p.pdf_file).name == filename:
            return p, "recorded"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", stem)  # ② 日期前缀
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            d = None
        if d:
            for p in papers:
                if p.paper_date == d:
                    return p, "date"
    nf = _norm_title(stem)  # ③ 标题模糊包含
    best, best_len = None, 0
    for p in papers:
        nt = _norm_title(p.title)
        if nt and (nt in nf or nf in nt) and len(nt) > best_len:
            best, best_len = p, len(nt)
    if best:
        return best, "title"
    return None, "none"


@router.get("/folder-scan")
def folder_scan(db: Session = Depends(get_db)):
    """扫描 daily_paper 文件夹，返回每个 PDF 的匹配结果与候选论文列表（供前端预览/手动关联）。"""
    papers = db.query(DailyPaper).order_by(DailyPaper.paper_date.desc()).all()
    files = []
    if DAILY_PAPER_DIR.exists():
        for f in sorted(DAILY_PAPER_DIR.glob("*.pdf")):
            if not f.is_file():
                continue
            p, mtype = _match_paper_for_file(f.name, papers)
            files.append(
                {
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "match": mtype,
                    "paper_id": p.id if p else None,
                    "paper_date": p.paper_date.isoformat() if p else "",
                    "paper_title": p.title if p else "",
                    "already_in_zotero": bool(p.zotero_key) if p else False,
                    "already_has_pdf": bool(p.zotero_pdf_key) if p else False,
                    "recorded": bool(p and p.pdf_file and Path(p.pdf_file).name == f.name),
                }
            )
    candidates = [
        {
            "id": p.id,
            "paper_date": p.paper_date.isoformat(),
            "title": p.title,
            "zotero_key": p.zotero_key or "",
        }
        for p in papers
    ]
    return {
        "dir": str(DAILY_PAPER_DIR),
        "configured": zotero.is_configured(),
        "files": files,
        "candidates": candidates,
    }


@router.post("/sync-folder")
def sync_folder(data: dict, db: Session = Depends(get_db)):
    """把 daily_paper 文件夹里的 PDF 同步到 Zotero（题录 + PDF 附件 + 推荐日期/已读标签）。

    body: `{"items": [{"filename": "...", "paper_id": 3}]}`
    - 论文若未推送过 Zotero → 先推送题录（集合「红外小目标检测每日论文推荐」）再挂 PDF
    - 已推送过 → 补推标签 / 补挂 PDF 附件
    - 都会回写数据库 pdf_file（让工作台「打开 PDF」指向文件夹里的文件）
    逐条容错，单条失败不影响其余；返回每条结果与汇总。
    """
    if not zotero.is_configured():
        raise HTTPException(400, "未配置 Zotero API Key / User ID，无法同步")
    items = data.get("items")
    if not items:
        # 未指定则自动同步所有已匹配的文件（供「一键全部同步」用）
        papers = db.query(DailyPaper).order_by(DailyPaper.paper_date.desc()).all()
        items = []
        if DAILY_PAPER_DIR.exists():
            for f in sorted(DAILY_PAPER_DIR.glob("*.pdf")):
                p, _ = _match_paper_for_file(f.name, papers)
                if p:
                    items.append({"filename": f.name, "paper_id": p.id})

    collection_key = zotero.ensure_collection(ZOTERO_COLLECTION_NAME)
    results = []
    pushed = attached = tag_updated = 0
    for it in items:
        filename = Path(str(it.get("filename") or "")).name
        pid = it.get("paper_id")
        entry = {"filename": filename, "paper_id": pid, "ok": False}
        try:
            p = db.get(DailyPaper, int(pid)) if pid else None
            if not p:
                entry["error"] = "关联的每日论文不存在"
                results.append(entry)
                continue
            f = DAILY_PAPER_DIR / filename
            if not (filename and f.exists() and f.suffix.lower() == ".pdf"):
                entry["error"] = "PDF 文件不存在"
                results.append(entry)
                continue
            p.pdf_file = filename
            db.commit()
            entry["title"] = p.title
            entry["pushed"] = False
            entry["attached"] = False
            _adopt_existing_zotero_key(db, p)  # 论文已在 Zotero（手动导入过）→ 认领，不重复创建
            if not p.zotero_key:
                _push_to_zotero(db, p, attach_pdf=True)  # 题录 + 附件一起推
                entry["pushed"] = True
                pushed += 1
                if p.zotero_pdf_key:
                    entry["attached"] = True
                    attached += 1
            else:
                warn = _ensure_zotero_tags(p, collection_key=collection_key)
                if not warn:
                    tag_updated += 1
                if not p.zotero_pdf_key:
                    # 条目下可能已有 PDF（用户手动挂过）→ 认领已有附件，不重复挂
                    existing_pdf = zotero.find_pdf_attachment(p.zotero_key)
                    if existing_pdf:
                        p.zotero_pdf_key = existing_pdf
                        db.commit()
                    else:
                        p.zotero_pdf_key = zotero.push_pdf_attachment(p.zotero_key, f)
                        db.commit()
                        entry["attached"] = True
                        attached += 1
            entry["zotero_key"] = p.zotero_key
            entry["ok"] = True
        except Exception as e:
            entry["error"] = _zotero_err_text(e)
            db.rollback()
        results.append(entry)
    return {
        "total": len(results),
        "pushed": pushed,
        "attached": attached,
        "tag_updated": tag_updated,
        "failed": sum(1 for r in results if not r.get("ok")),
        "results": results,
        "collection_key": collection_key,
    }


@router.get("/{pid}/pdf")
def get_paper_pdf(pid: int, db: Session = Depends(get_db)):
    """返回已下载的论文 PDF（浏览器可直接打开）。"""
    p = db.get(DailyPaper, pid)
    if not p:
        raise HTTPException(404, "推荐不存在")
    if not p.pdf_file:
        raise HTTPException(404, "该论文没有可用的开放 PDF")
    f = DAILY_PAPER_DIR / Path(p.pdf_file).name
    if not f.exists():
        raise HTTPException(404, "PDF 文件不存在")
    return FileResponse(f, media_type="application/pdf", filename=f"{p.paper_date}_{p.title[:40]}.pdf")


@router.post("/{pid}/rate")
def rate_paper(pid: int, data: dict, db: Session = Depends(get_db)):
    p = db.get(DailyPaper, pid)
    if not p:
        raise HTTPException(404, "推荐不存在")
    rating = str(data.get("rating") or "")
    if rating not in RATINGS:
        raise HTTPException(400, "rating 只能是 useful/general/not_interested/空")
    p.rating = rating
    db.commit()
    return serialize(p)


@router.post("/{pid}/read")
def mark_read(pid: int, db: Session = Depends(get_db)):
    p = db.get(DailyPaper, pid)
    if not p:
        raise HTTPException(404, "推荐不存在")
    p.read = True
    db.commit()
    # 已读状态同步到 Zotero 标签（未读 → 已读），失败不阻塞，返回 warning
    warning = _ensure_zotero_tags(p)
    return {**serialize(p), "zotero_warning": warning}


@router.post("/{pid}/archive")
def archive_paper(pid: int, db: Session = Depends(get_db)):
    """一键入库：本地文献库 + 推送到 Zotero（幂等，先推后存并回填 zotero_key）。

    - 论文已在 Zotero（p.zotero_key 有）或本地条目是从 Zotero 同步来的 → 不重复推送
    - 推送失败不阻塞本地入库，返回 zotero_warning 供前端提示
    """
    p = db.get(DailyPaper, pid)
    if not p:
        raise HTTPException(404, "推荐不存在")

    # 复用/准备本地文献库条目
    lit = None
    if p.literature_id:
        lit = db.get(LiteratureItem, p.literature_id)
    if not lit:
        lit = db.query(LiteratureItem).filter(LiteratureItem.title == p.title).first()

    warning = None
    pushed = False
    if not (p.zotero_key or (lit and lit.zotero_key)):
        # 需要推送：手动归档动作不受「自动存入 Zotero」开关限制
        if not zotero.is_configured():
            warning = "未配置 Zotero API Key / User ID，仅存入本地文献库"
        else:
            try:
                _push_to_zotero(db, p, attach_pdf=False)
                pushed = True
            except Exception as e:
                warning = f"推送到 Zotero 失败：{_zotero_err_text(e)}"

    if not lit:
        try:
            authors = json.loads(p.authors or "[]")
        except Exception:
            authors = []
        item_type = _paper_type(p.publication)
        if item_type == "preprint":
            item_type = "journalArticle"  # 本地文献库此前只存 conference/journal，Zotero 侧才用 preprint
        lit = LiteratureItem(
            title=p.title,
            authors=json.dumps(authors, ensure_ascii=False),
            year=p.year,
            publication=p.publication,
            item_type=item_type,
            abstract=p.abstract,
            tags="红外小目标,每日推荐",
            url=p.url,
            doi=p.doi,
        )
        db.add(lit)
        db.flush()
    # 回填 zotero_key 到本地条目（防 Zotero 同步时重复拉回新条目）与论文记录
    zkey = p.zotero_key or (lit.zotero_key or "")
    if zkey:
        if not p.zotero_key:
            p.zotero_key = zkey
        if not lit.zotero_key:
            lit.zotero_key = zkey
    p.literature_id = lit.id
    db.commit()
    # 条目此前已存在于 Zotero（非本次新推）时，补一次推荐日期/已读标签
    if zkey and not pushed:
        warning = warning or (_ensure_zotero_tags(p) or None)
    return {**_serialize_lit(lit), "zotero_key": zkey, "zotero_warning": warning}


@router.post("/{pid}/pdf")
async def upload_paper_pdf(pid: int, file: UploadFile, db: Session = Depends(get_db)):
    """上传 PDF（付费墙论文：浏览器里用校园网权限下好后传给工作台）。

    覆盖本地 pdf_file（推送 Zotero 附件用）；若论文还没推送 Zotero 则顺带整单推送，
    已推送但附件未挂上则补挂附件。推送失败返回 zotero_warning，不阻塞上传。
    """
    p = db.get(DailyPaper, pid)
    if not p:
        raise HTTPException(404, "推荐不存在")
    ext = Path(file.filename or "paper.pdf").suffix.lower()
    if ext != ".pdf":
        raise HTTPException(400, "只支持 PDF 文件")
    if p.pdf_file:
        # 覆盖已下载文件：先删旧文件防残留
        try:
            old = DAILY_PAPER_DIR / Path(p.pdf_file).name
            if old.exists():
                old.unlink()
        except OSError:
            pass
    else:
        p.pdf_file = paper_sources._safe_filename(p.title) + ".pdf"
        p.pdf_file = f"{p.paper_date.isoformat()}_{p.pdf_file}"
    dest = DAILY_PAPER_DIR / Path(p.pdf_file).name
    import shutil

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    p.pdf_file = dest.name
    db.commit()

    warning = None
    _adopt_existing_zotero_key(db, p)  # 论文已在 Zotero（手动导入过）→ 认领，不重复创建
    if not zotero.is_configured():
        warning = "已上传本地 PDF；未配置 Zotero Key / User ID，未推送到 Zotero"
    elif not p.zotero_key:
        try:
            _push_to_zotero(db, p)  # 整单推送（含刚上传的 PDF 附件）
        except Exception as e:
            warning = f"推送到 Zotero 失败：{_zotero_err_text(e)}"
    elif not p.zotero_pdf_key:
        try:
            p.zotero_pdf_key = zotero.push_pdf_attachment(p.zotero_key, dest)
            db.commit()
        except Exception as e:
            warning = f"PDF 附件上传失败：{_zotero_err_text(e)}"
    if p.zotero_key and not warning:
        warning = _ensure_zotero_tags(p) or None
    return {**serialize(p), "zotero_warning": warning}


def _serialize_lit(lit: LiteratureItem) -> dict:
    try:
        authors = json.loads(lit.authors or "[]")
    except Exception:
        authors = []
    return {
        "id": lit.id,
        "title": lit.title,
        "authors": authors,
        "year": lit.year,
        "publication": lit.publication,
        "doi": lit.doi,
        "url": lit.url,
        "abstract": lit.abstract,
        "tags": lit.tags,
        "read_status": lit.read_status,
    }