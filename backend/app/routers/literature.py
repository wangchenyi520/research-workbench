import json
import re
import shutil
import uuid
from datetime import date
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import PDF_DIR
from ..database import get_db
from ..models import LiteratureItem, ZoteroCollection
from ..schemas import LiteratureUpdate
from ..services import deepseek, zotero

router = APIRouter(prefix="/api/literature", tags=["literature"])


def serialize(item: LiteratureItem):
    try:
        authors = json.loads(item.authors or "[]")
    except Exception:
        authors = []
    return {
        "id": item.id,
        "zotero_key": item.zotero_key,
        "title": item.title,
        "authors": authors,
        "year": item.year,
        "publication": item.publication,
        "item_type": item.item_type,
        "abstract": item.abstract,
        "tags": item.tags,
        "ai_summary": item.ai_summary,
        "read_status": item.read_status,
        "my_notes": item.my_notes,
        "goal_id": item.goal_id,
        "collection_keys": item.collection_keys,
        "url": item.url,
        "doi": item.doi,
        "journal_level": item.journal_level,
        "impact_factor": item.impact_factor,
        "pdf_path": item.pdf_path,
        "read_date": item.read_date.isoformat() if item.read_date else None,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


@router.get("/zotero/status")
def zotero_status():
    return {"running": zotero.is_running()}


@router.post("/sync")
def sync_from_zotero(db: Session = Depends(get_db)):
    """增量合并同步：已存在则跳过，新条目插入，并同步 Zotero 集合。"""
    if not zotero.is_configured():
        raise HTTPException(400, "未配置 Zotero API Key 和 User ID，请到设置页填写。")
    try:
        raw = zotero.get_items(limit=200)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            raise HTTPException(400, "Zotero API Key 无效或无权访问，请检查设置。")
        raise HTTPException(502, f"Zotero 同步失败（{e.response.status_code}）")
    except Exception as e:
        raise HTTPException(502, f"Zotero 同步失败：{e}")

    # 同步集合
    try:
        collections = zotero.get_collections()
        col_map = {}
        for c in collections:
            col_map[c["key"]] = c["name"]
            existing = db.query(ZoteroCollection).filter(ZoteroCollection.zotero_key == c["key"]).first()
            if existing:
                existing.name = c["name"]
                existing.parent_key = c["parent_key"]
            else:
                db.add(ZoteroCollection(zotero_key=c["key"], name=c["name"], parent_key=c["parent_key"]))
    except Exception:
        col_map = {}

    # 增量合并文献（分页拉取全量，见 zotero.get_items）
    items = zotero.parse_items(raw)
    added = 0
    updated = 0
    for it in items:
        existing = None
        if it["zotero_key"]:
            existing = (
                db.query(LiteratureItem)
                .filter(LiteratureItem.zotero_key == it["zotero_key"])
                .first()
            )
            if existing is None:
                # 补链认领：本地存在「工作台手工入库/每日论文推送但还没同步过」的同标题无 key 条目
                # → 认领该 Zotero key，避免同步拉回一条重复的新条目
                existing = (
                    db.query(LiteratureItem)
                    .filter(
                        LiteratureItem.title == it["title"],
                        LiteratureItem.zotero_key.is_(None),
                    )
                    .first()
                )
                if existing:
                    existing.zotero_key = it["zotero_key"]
        if existing:
            # 增量：先补集合信息
            existing.collection_keys = it["collection_keys"]
            # 条目在 Zotero 侧有更新时，刷新元数据（不覆盖本地 AI 总结/阅读状态/笔记）
            ver = it.get("zotero_version")
            if ver is not None and existing.zotero_version != ver:
                existing.title = it["title"]
                existing.authors = json.dumps(it["authors"], ensure_ascii=False)
                existing.year = it["year"]
                existing.publication = it["publication"]
                existing.item_type = it["item_type"]
                existing.abstract = it["abstract"]
                existing.tags = it["tags"]
                existing.url = it["url"]
                existing.doi = it["doi"]
                existing.zotero_version = ver
                updated += 1
            continue
        data = {k: v for k, v in it.items()}
        if isinstance(data.get("authors"), list):
            data["authors"] = json.dumps(data["authors"], ensure_ascii=False)
        db.add(LiteratureItem(**data))
        added += 1
    db.commit()
    return {"ok": True, "added": added, "updated": updated, "collections": len(col_map)}


@router.get("/collections")
def list_collections(db: Session = Depends(get_db)):
    cols = db.query(ZoteroCollection).all()
    return [{"key": c.zotero_key, "name": c.name, "parent_key": c.parent_key} for c in cols]


def _norm_tag(t: str) -> str:
    t = t.strip()
    for suf in ("算法", "方法", "技术", "研究", "方向", "综述", "框架", "模型"):
        if t.endswith(suf) and len(t) > len(suf) + 1:
            t = t[: -len(suf)]
    return t


@router.post("/cleanup-tags")
def cleanup_tags(data: dict | None = None, db: Session = Depends(get_db)):
    """清理近似重复标签：preview=true 返回建议，preview=false 实际合并。"""
    preview = bool((data or {}).get("preview", True))
    items = db.query(LiteratureItem).all()
    groups: dict[str, dict[str, int]] = {}
    for i in items:
        for t in [x.strip() for x in i.tags.split(",") if x.strip()]:
            groups.setdefault(_norm_tag(t), {}).setdefault(t, 0)
            groups[_norm_tag(t)][t] += 1
    suggestions = []
    for key, variants in groups.items():
        if len(variants) > 1:
            std = key if key else max(variants, key=len)
            suggestions.append({"standard": std, "variants": sorted(variants.keys())})
    if preview or not suggestions:
        return {"suggestions": suggestions, "count": len(suggestions), "applied": False}

    merged_items = 0
    for sug in suggestions:
        std = sug["standard"]
        for v in sug["variants"]:
            if v == std:
                continue
            for i in items:
                tags = [x.strip() for x in i.tags.split(",") if x.strip()]
                if v in tags:
                    tags = [std if x == v else x for x in tags]
                    i.tags = ",".join(dict.fromkeys(tags))
                    merged_items += 1
    db.commit()
    return {"suggestions": suggestions, "count": len(suggestions), "applied": True, "merged_items": merged_items}


@router.get("")
def list_literature(db: Session = Depends(get_db), q: str = ""):
    query = db.query(LiteratureItem)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(
            (LiteratureItem.title.like(like))
            | (LiteratureItem.authors.like(like))
            | (LiteratureItem.tags.like(like))
        )
    rows = query.order_by(LiteratureItem.updated_at.desc()).all()
    return [serialize(r) for r in rows]


@router.get("/{item_id}")
def get_literature(item_id: int, db: Session = Depends(get_db)):
    item = db.get(LiteratureItem, item_id)
    if not item:
        raise HTTPException(404, "文献不存在")
    return serialize(item)


@router.post("/{item_id}/summarize")
def summarize_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(LiteratureItem, item_id)
    if not item:
        raise HTTPException(404, "文献不存在")
    text = item.abstract or item.title
    if not text.strip():
        raise HTTPException(400, "该文献没有摘要，无法总结")
    try:
        result = deepseek.summarize_text(f"文献标题：{item.title}\n摘要：{item.abstract}")
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    item.ai_summary = result
    db.commit()
    return {"result": result}


@router.get("/{item_id}/cite")
def cite_item(item_id: int, db: Session = Depends(get_db), style: str = "gb7714"):
    """生成参考文献条目。style: gb7714（学位论文）/ apa / bibtex。"""
    item = db.get(LiteratureItem, item_id)
    if not item:
        raise HTTPException(404, "文献不存在")
    try:
        authors = json.loads(item.authors or "[]")
    except Exception:
        authors = []
    title = item.title or ""
    year = item.year
    pub = item.publication or ""
    doi = item.doi or ""
    if style == "bibtex":
        key = re.sub(r"[^\w\u4e00-\u9fa5]", "", title)[:20] or f"item{item.id}"
        a = " and ".join(a.replace(" ", ", ") for a in authors)
        return {
            "text": f"@article{{{key},\n  title = {{{title}}},\n  author = {{{a or 'Unknown'}}},\n  year = {{{year or ''}}},\n  journal = {{{pub}}},\n}}",
            "style": "bibtex",
        }
    if style == "apa":
        # APA: LastName, F. M., & LastName, F. M. (Year). Title. Journal.
        a = []
        for name in authors:
            parts = [p for p in re.split(r"[\s,]+", name.strip()) if p]
            if len(parts) >= 2:
                a.append(f"{parts[-1]}, {' '.join(x[0] + '.' for x in parts[:-1])}")
            else:
                a.append(name)
        if len(a) > 7:
            a = a[:6] + ["… " + a[-1]]
        sep = ", " if len(a) <= 2 else ", "
        joined = " & ".join([sep.join(a[:1]), a[1]]) if len(a) == 2 else sep.join(a)
        return {
            "text": f"{joined} ({year}). {title}. {pub}." if year else f"{joined}. {title}. {pub}.",
            "style": "apa",
        }
    # GB/T 7714
    a = []
    for name in authors:
        if "," in name:
            parts = [p.strip() for p in name.split(",")]
            a.append(parts[-1] + " " + parts[0])
        else:
            a.append(name)
    if len(a) > 3:
        a = a[:3] + ["等"]
    authors_str = "，".join(a)
    item_tag = {"journalArticle": "[J]", "thesis": "[D]", "conferencePaper": "[C]", "book": "[M]", "preprint": "[J/OL]"}.get(item.item_type, "[J]")
    base = f"{authors_str}. {title}{item_tag}."
    if pub:
        base += f" {pub}"
    if year:
        base += f", {year}."
    if doi:
        base += f" DOI: {doi}."
    return {"text": base, "style": "gb7714"}


@router.post("/batch-journal-info")
def batch_journal_info(db: Session = Depends(get_db), limit: int = 50):
    """AI 批量补全文献期刊等级/影响因子（不保证绝对准确，提示用户核实）。"""
    items = (
        db.query(LiteratureItem)
        .filter(LiteratureItem.publication != "", LiteratureItem.journal_level == "")
        .limit(limit)
        .all()
    )
    if not items:
        raise HTTPException(400, "没有需要补全期刊信息的文献")
    from ..services.deepseek import AIError

    done = 0
    for it in items:
        try:
            info = deepseek.journal_info(it.publication)
            if info.get("level"):
                it.journal_level = info["level"]
            if info.get("if"):
                it.impact_factor = info["if"]
            done += 1
        except AIError:
            break
        except Exception:
            continue
    db.commit()
    return {"ok": True, "done": done, "total": len(items)}


@router.put("/{item_id}")
def update_literature(item_id: int, data: LiteratureUpdate, db: Session = Depends(get_db)):
    item = db.get(LiteratureItem, item_id)
    if not item:
        raise HTTPException(404, "文献不存在")
    old_status = item.read_status
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    # 阅读计划：置「已读」记录 read_date（统计本周阅读量用），离开已读清空
    if "read_status" in data.model_fields_set and item.read_status != old_status:
        if item.read_status == "read":
            if not item.read_date:
                item.read_date = date.today()
        else:
            item.read_date = None
    db.commit()
    db.refresh(item)
    return serialize(item)


# ---------- PDF 关联 ----------
@router.post("/{item_id}/pdf")
async def upload_pdf(item_id: int, file: UploadFile, db: Session = Depends(get_db)):
    item = db.get(LiteratureItem, item_id)
    if not item:
        raise HTTPException(404, "文献不存在")
    ext = Path(file.filename or "paper.pdf").suffix.lower()
    if ext != ".pdf":
        raise HTTPException(400, "只支持 PDF 文件")
    filename = f"{item_id}_{uuid.uuid4().hex[:8]}.pdf"
    dest = PDF_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    item.pdf_path = filename
    db.commit()
    return {"ok": True, "pdf_path": filename}


@router.get("/pdf/{filename}")
def get_pdf(filename: str):
    name = Path(filename).name
    dest = PDF_DIR / name
    if not dest.exists():
        raise HTTPException(404, "PDF 不存在")
    return FileResponse(dest, media_type="application/pdf", filename=name)


@router.delete("/{item_id}/pdf")
def delete_pdf(item_id: int, db: Session = Depends(get_db)):
    item = db.get(LiteratureItem, item_id)
    if not item:
        raise HTTPException(404, "文献不存在")
    if item.pdf_path:
        try:
            f = PDF_DIR / Path(item.pdf_path).name
            if f.exists():
                f.unlink()
        except OSError:
            pass
        item.pdf_path = ""
        db.commit()
    return {"ok": True}


@router.delete("/{item_id}")
def delete_literature(item_id: int, db: Session = Depends(get_db)):
    item = db.get(LiteratureItem, item_id)
    if not item:
        raise HTTPException(404, "文献不存在")
    # C7：同步清理今日清单里的「读文献」待办项，避免残留死引用
    from ..models import DailyItem

    db.query(DailyItem).filter(
        DailyItem.kind == "literature", DailyItem.source_id == item_id
    ).delete(synchronize_session=False)
    db.delete(item)
    db.commit()
    return {"ok": True}
