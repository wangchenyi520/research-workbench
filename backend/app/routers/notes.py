import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import ATTACH_DIR, IMAGES_DIR
from ..database import get_db
from ..models import Note, NoteAttachment, NoteImage
from ..schemas import NoteCreate, NoteUpdate

router = APIRouter(prefix="/api/notes", tags=["notes"])

PREVIEW_LEN = 300

ALLOWED_ATTACH_EXT = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".md", ".zip", ".rar", ".7z", ".csv", ".ipynb"}


def serialize_note(n: Note, preview: bool = False):
    content = n.content
    if preview and content and len(content) > PREVIEW_LEN:
        content = content[:PREVIEW_LEN] + "…"
    return {
        "id": n.id,
        "title": n.title,
        "content": content,
        "tags": n.tags,
        "pinned": n.pinned,
        "folder": n.folder,
        "goal_id": n.goal_id,
        "created_at": n.created_at.isoformat(),
        "updated_at": n.updated_at.isoformat(),
    }


@router.get("")
def list_notes(q: str = "", db: Session = Depends(get_db)):
    query = db.query(Note).filter(Note.deleted_at.is_(None))
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Note.title.like(like), Note.content.like(like)))
    notes = query.order_by(Note.pinned.desc(), Note.updated_at.desc()).all()
    return [serialize_note(n, preview=True) for n in notes]


# 回收站（必须在 /{note_id} 之前注册，避免路由吞掉 "trash"）
@router.get("/trash")
def list_note_trash(db: Session = Depends(get_db)):
    rows = (
        db.query(Note)
        .filter(Note.deleted_at.isnot(None))
        .order_by(Note.deleted_at.desc())
        .all()
    )
    return [
        {
            "id": n.id,
            "title": n.title,
            "folder": n.folder,
            "deleted_at": n.deleted_at.isoformat() if n.deleted_at else None,
        }
        for n in rows
    ]


@router.delete("/trash")
def purge_all_note_trash(db: Session = Depends(get_db)):
    """清空回收站：彻底删除所有已删除（软删）笔记，并清理关联图片文件。"""
    rows = db.query(Note).filter(Note.deleted_at.isnot(None)).all()
    count = 0
    for n in rows:
        imgs = db.query(NoteImage).filter(NoteImage.note_id == n.id).all()
        for img in imgs:
            f = IMAGES_DIR / img.filename
            try:
                if f.exists():
                    f.unlink()
            except OSError:
                pass
        db.query(NoteImage).filter(NoteImage.note_id == n.id).delete()
        db.delete(n)
        count += 1
    db.commit()
    return {"ok": True, "purged": count}


@router.post("")
def create_note(data: NoteCreate, db: Session = Depends(get_db)):
    n = Note(**data.model_dump())
    db.add(n)
    db.commit()
    db.refresh(n)
    return serialize_note(n)


# ---------- 附件（必须在 /{note_id} 之前注册） ----------
@router.get("/attachments/{filename}")
def download_attachment(filename: str):
    name = Path(filename).name
    dest = ATTACH_DIR / name
    if not dest.exists():
        raise HTTPException(404, "附件不存在")
    return FileResponse(dest)


@router.post("/{note_id}/attachments")
async def upload_attachment(note_id: int, file: UploadFile):
    n = None
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        n = db.get(Note, note_id)
    finally:
        db.close()
    if not n:
        raise HTTPException(404, "笔记不存在")
    ext = Path(file.filename or "file.bin").suffix.lower() or ".bin"
    if ext not in ALLOWED_ATTACH_EXT:
        raise HTTPException(400, f"不支持的附件类型 {ext}")
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = ATTACH_DIR / filename
    size = 0
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
        size = f.tell() or dest.stat().st_size
    db = SessionLocal()
    try:
        a = NoteAttachment(
            note_id=note_id,
            filename=filename,
            original_name=Path(file.filename or "file.bin").name,
            size=size,
        )
        db.add(a)
        db.commit()
        db.refresh(a)
        return {
            "id": a.id,
            "original_name": a.original_name,
            "filename": a.filename,
            "size": a.size,
            "url": f"/api/notes/attachments/{a.filename}",
            "created_at": a.created_at.isoformat(),
        }
    finally:
        db.close()


@router.get("/{note_id}/attachments")
def list_attachments(note_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(NoteAttachment)
        .filter(NoteAttachment.note_id == note_id)
        .order_by(NoteAttachment.created_at.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "original_name": a.original_name,
            "filename": a.filename,
            "size": a.size,
            "url": f"/api/notes/attachments/{a.filename}",
            "created_at": a.created_at.isoformat(),
        }
        for a in rows
    ]


@router.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    a = db.get(NoteAttachment, attachment_id)
    if not a:
        raise HTTPException(404, "附件不存在")
    try:
        f = ATTACH_DIR / a.filename
        if f.exists():
            f.unlink()
    except OSError:
        pass
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.get("/{note_id}")
def get_note(note_id: int, db: Session = Depends(get_db)):
    n = db.get(Note, note_id)
    if not n:
        raise HTTPException(404, "笔记不存在")
    return serialize_note(n)


@router.get("/{note_id}/backlinks")
def note_backlinks(note_id: int, db: Session = Depends(get_db)):
    """返回引用了该笔记的所有笔记（反向链接）。"""
    n = db.get(Note, note_id)
    if not n:
        raise HTTPException(404, "笔记不存在")
    # SQLite LIKE 中 [ % _ 是模式特殊字符，需转义，否则含 [[]] 的 pattern 匹配失败
    esc = (
        n.title.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
        .replace("[", "\\[")
    )
    rows = (
        db.query(Note)
        .filter(
            Note.id != note_id,
            Note.deleted_at.is_(None),
            Note.content.like(f"%[[{esc}]]%", escape="\\"),
        )
        .order_by(Note.updated_at.desc())
        .all()
    )
    return [{"id": r.id, "title": r.title, "folder": r.folder, "updated_at": r.updated_at.isoformat()} for r in rows]


@router.put("/{note_id}")
def update_note(note_id: int, data: NoteUpdate, db: Session = Depends(get_db)):
    n = db.get(Note, note_id)
    if not n:
        raise HTTPException(404, "笔记不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(n, k, v)
    n.updated_at = datetime.now()
    db.commit()
    db.refresh(n)
    return serialize_note(n)


@router.delete("/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db)):
    """软删：进回收站（deleted_at 标记），purge 才真删。"""
    n = db.get(Note, note_id)
    if not n:
        raise HTTPException(404, "笔记不存在")
    n.deleted_at = datetime.now()
    db.commit()
    return {"ok": True}


@router.post("/{note_id}/restore")
def restore_note(note_id: int, db: Session = Depends(get_db)):
    n = db.get(Note, note_id)
    if not n:
        raise HTTPException(404, "笔记不存在")
    n.deleted_at = None
    n.updated_at = datetime.now()
    db.commit()
    return {"ok": True}


@router.delete("/{note_id}/purge")
def purge_note(note_id: int, db: Session = Depends(get_db)):
    n = db.get(Note, note_id)
    if not n:
        raise HTTPException(404, "笔记不存在")
    # 清理关联图片文件与记录
    imgs = db.query(NoteImage).filter(NoteImage.note_id == note_id).all()
    for img in imgs:
        f = IMAGES_DIR / img.filename
        try:
            if f.exists():
                f.unlink()
        except OSError:
            pass
    db.query(NoteImage).filter(NoteImage.note_id == note_id).delete()
    db.delete(n)
    db.commit()
    return {"ok": True}


# ---------- Images ----------
@router.post("/images")
async def upload_image(note_id: int | None = None, file: UploadFile | None = None):
    if file is None:
        raise HTTPException(400, "缺少文件")
    ext = Path(file.filename or "img.png").suffix.lower() or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = IMAGES_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    img = NoteImage(note_id=note_id, filename=filename, original_name=file.filename or "")
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        db.add(img)
        db.commit()
        db.refresh(img)
    finally:
        db.close()
    return {
        "id": img.id,
        "url": f"/api/notes/images/{filename}",
        "filename": filename,
        "original_name": img.original_name,
    }


@router.get("/images/{filename}")
def get_image(filename: str):
    # 防止路径遍历：只允许访问图片目录下的文件名，不解析子路径/上级路径
    name = Path(filename).name
    dest = IMAGES_DIR / name
    if not dest.exists():
        raise HTTPException(404, "图片不存在")
    return FileResponse(dest)
