import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Review
from ..schemas import ReviewUpdate

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


def _load_content(raw: str | None):
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def week_range(ref: date):
    start = ref - timedelta(days=ref.weekday())
    end = start + timedelta(days=6)
    return start, end


@router.get("/current")
def get_current_review(db: Session = Depends(get_db)):
    start, end = week_range(date.today())
    review = (
        db.query(Review)
        .filter(Review.week_start == start)
        .first()
    )
    if not review:
        review = Review(
            week_start=start,
            week_end=end,
            content=json.dumps({"done": "", "todo": "", "progress": "", "problems": "", "improvements": "", "goal_progress": []}, ensure_ascii=False),
            completed=False,
        )
        db.add(review)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            review = (
                db.query(Review)
                .filter(Review.week_start == start)
                .first()
            )
        else:
            db.refresh(review)
    if not review:
        raise HTTPException(500, "无法加载周复盘，请重试")
    return {
        "id": review.id,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "content": _load_content(review.content),
        "completed": review.completed,
    }


@router.put("/{review_id}")
def update_review(review_id: int, data: ReviewUpdate, db: Session = Depends(get_db)):
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(404, "复盘不存在")
    if data.content is not None:
        r.content = json.dumps(data.content, ensure_ascii=False)
    if data.completed is not None:
        r.completed = data.completed
    db.commit()
    db.refresh(r)
    return {"ok": True}


@router.get("")
def list_reviews(db: Session = Depends(get_db)):
    rows = db.query(Review).order_by(Review.week_start.desc()).limit(30).all()
    return [
        {
            "id": r.id,
            "week_start": r.week_start.isoformat(),
            "week_end": r.week_end.isoformat() if r.week_end else None,
            "content": _load_content(r.content),
            "completed": r.completed,
        }
        for r in rows
    ]
