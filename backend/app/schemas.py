from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Task ----------
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, description="任务标题不能为空")
    description: str = ""
    task_type: str = "once"
    priority: int = Field(2, ge=1, le=5)
    due_date: Optional[date] = None
    goal_id: Optional[int] = None
    tags: str = ""
    pomodoro_minutes: int = Field(25, ge=1, le=120)
    break_minutes: int = Field(5, ge=0, le=60)
    repeat_weekdays: str = ""
    est_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None

    @field_validator("est_minutes", "actual_minutes", mode="before")
    @classmethod
    def _empty_int(cls, v):
        # 前端可能提交空字符串（未填预估时长），容错转 None 避免 422
        if v == "" or v is None:
            return None
        return v


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    task_type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    due_date: Optional[date] = None
    goal_id: Optional[int] = None
    tags: Optional[str] = None
    pomodoro_minutes: Optional[int] = None
    break_minutes: Optional[int] = None
    sort_order: Optional[int] = None
    repeat_weekdays: Optional[str] = None
    est_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None

    @field_validator("est_minutes", "actual_minutes", mode="before")
    @classmethod
    def _empty_int(cls, v):
        if v == "" or v is None:
            return None
        return v


class SubtaskCreate(BaseModel):
    title: str = Field(..., min_length=1)


class SubtaskUpdate(BaseModel):
    title: Optional[str] = None
    done: Optional[bool] = None
    sort_order: Optional[int] = None


class CheckinCreate(BaseModel):
    date: date
    note: str = ""


class TimeLogCreate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    kind: str = "manual"
    note: str = ""


class TimeLogOut(OrmModel):
    id: int
    task_id: int
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: int
    kind: str
    note: str


# ---------- Goal ----------
class GoalCreate(BaseModel):
    title: str
    description: str = ""
    level: str = "annual"
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    parent_id: Optional[int] = None
    status: str = "active"
    progress: float = 0


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    level: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    parent_id: Optional[int] = None
    status: Optional[str] = None
    progress: Optional[float] = None


class MilestoneCreate(BaseModel):
    title: str
    description: str = ""
    due_date: Optional[date] = None
    color: str = "#7C6CF0"
    sort_order: int = 0


class MilestoneUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[date] = None
    completed: Optional[bool] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None


# ---------- Note ----------
class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = ""
    tags: str = ""
    pinned: bool = False
    folder: str = ""
    goal_id: Optional[int] = None


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None
    pinned: Optional[bool] = None
    folder: Optional[str] = None
    goal_id: Optional[int] = None


# ---------- Literature ----------
class LiteratureItemOut(OrmModel):
    id: int
    zotero_key: Optional[str]
    title: str
    authors: str
    year: Optional[int]
    publication: str
    item_type: str
    abstract: str
    tags: str
    ai_summary: str
    url: str
    doi: str


class LiteratureUpdate(BaseModel):
    ai_summary: Optional[str] = None
    tags: Optional[str] = None
    title: Optional[str] = None
    read_status: Optional[str] = None
    my_notes: Optional[str] = None
    goal_id: Optional[int] = None
    journal_level: Optional[str] = None
    impact_factor: Optional[str] = None
    pdf_path: Optional[str] = None


# ---------- Review ----------
class ReviewUpdate(BaseModel):
    content: Optional[dict] = None
    completed: Optional[bool] = None


# ---------- Settings ----------
class SettingUpdate(BaseModel):
    key: str
    value: str


# ---------- Reminder ----------
class ReminderCreate(BaseModel):
    title: str = Field(..., min_length=1)
    remind_at: datetime
    repeat: str = "none"  # none/daily/weekly/monthly
    advance_minutes: list[int] = []
    note: str = ""

    @field_validator("advance_minutes", mode="before")
    @classmethod
    def _norm_advance(cls, v):
        if v in (None, ""):
            return []
        if isinstance(v, str):
            import json

            try:
                v = json.loads(v)
            except Exception:
                return []
        out = []
        for x in (v or []):
            try:
                n = int(x)
            except Exception:
                continue
            if n > 0:
                out.append(n)
        return out[:5]  # 最多 5 次提前提醒


class ReminderUpdate(BaseModel):
    title: Optional[str] = None
    remind_at: Optional[datetime] = None
    repeat: Optional[str] = None
    advance_minutes: Optional[list[int]] = None
    note: Optional[str] = None
    status: Optional[str] = None
