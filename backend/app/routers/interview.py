from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import InterviewQuestion

router = APIRouter(prefix="/api/interview", tags=["interview"])

CATEGORIES = ["DL", "CV", "算法", "C++", "Python", "OS", "网络", "数据库", "项目", "其他"]

# 掌握程度 -> 下次复习间隔天数（艾宾浩斯简版）
REVIEW_INTERVAL = {0: 1, 1: 2, 2: 4}


class QuestionCreate(BaseModel):
    question: str = Field(..., min_length=1)
    category: str = "DL"
    answer: str = ""


class QuestionUpdate(BaseModel):
    question: str | None = None
    category: str | None = None
    answer: str | None = None
    mastery: int | None = None


class ReviewCreate(BaseModel):
    mastery: int = 0


def _serialize(q: InterviewQuestion):
    return {
        "id": q.id,
        "question": q.question,
        "category": q.category,
        "answer": q.answer,
        "mastery": q.mastery,
        "review_count": q.review_count,
        "last_review": q.last_review.isoformat() if q.last_review else None,
        "next_review": q.next_review.isoformat() if q.next_review else None,
        "created_at": q.created_at.isoformat(),
        "updated_at": q.updated_at.isoformat(),
    }


@router.get("/questions")
def list_questions(
    category: str | None = None,
    due: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(InterviewQuestion)
    if category:
        q = q.filter(InterviewQuestion.category == category)
    if due:
        q = q.filter(
            (InterviewQuestion.next_review.is_(None))
            | (InterviewQuestion.next_review <= date.today())
        )
    rows = q.order_by(InterviewQuestion.updated_at.desc()).all()
    return [_serialize(x) for x in rows]


@router.post("/questions")
def create_question(data: QuestionCreate, db: Session = Depends(get_db)):
    q = InterviewQuestion(**data.model_dump())
    db.add(q)
    db.commit()
    db.refresh(q)
    return _serialize(q)


@router.put("/questions/{qid}")
def update_question(qid: int, data: QuestionUpdate, db: Session = Depends(get_db)):
    q = db.get(InterviewQuestion, qid)
    if not q:
        raise HTTPException(404, "题目不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(q, k, v)
    db.commit()
    db.refresh(q)
    return _serialize(q)


@router.delete("/questions/{qid}")
def delete_question(qid: int, db: Session = Depends(get_db)):
    q = db.get(InterviewQuestion, qid)
    if not q:
        raise HTTPException(404, "题目不存在")
    db.delete(q)
    db.commit()
    return {"ok": True}


# ---------- 复习 ----------
@router.post("/questions/{qid}/review")
def review_question(qid: int, data: ReviewCreate, db: Session = Depends(get_db)):
    """标记复习：更新掌握程度，按间隔安排下次复习日期。"""
    q = db.get(InterviewQuestion, qid)
    if not q:
        raise HTTPException(404, "题目不存在")
    mastery = max(0, min(2, int(data.mastery)))
    q.mastery = mastery
    q.review_count += 1
    q.last_review = date.today()
    q.next_review = date.today() + timedelta(days=REVIEW_INTERVAL[mastery])
    db.commit()
    db.refresh(q)
    return _serialize(q)


@router.get("/stats")
def interview_stats(db: Session = Depends(get_db)):
    rows = db.query(InterviewQuestion).all()
    total = len(rows)
    mastery = [0, 0, 0]  # [不会, 模糊, 掌握]
    for q in rows:
        mastery[q.mastery] += 1
    due = sum(1 for q in rows if q.next_review is None or q.next_review <= date.today())
    today = date.today()
    reviewed_today = sum(1 for q in rows if q.last_review == today)
    by_category: dict[str, int] = {}
    for q in rows:
        by_category[q.category] = by_category.get(q.category, 0) + 1
    return {
        "total": total,
        "mastery": mastery,
        "due_today": due,
        "reviewed_today": reviewed_today,
        "by_category": by_category,
    }
