from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String, default="annual")  # annual/quarter/month/week
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, default="active")  # active/done/archived
    progress: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    parent: Mapped["Goal | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Goal"]] = relationship(back_populates="parent", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="goal")


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[str] = mapped_column(String, default="#7C6CF0")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    task_type: Mapped[str] = mapped_column(String, default="once")  # habit/study/once
    status: Mapped[str] = mapped_column(String, default="todo")  # todo/doing/done/archived
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1-5
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"), nullable=True)
    tags: Mapped[str] = mapped_column(String, default="")
    pomodoro_minutes: Mapped[int] = mapped_column(Integer, default=25)
    break_minutes: Mapped[int] = mapped_column(Integer, default=5)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 循环任务：repeat_weekdays 形如 "1,3"（datetime.weekday()，0=周一），空=不循环
    repeat_weekdays: Mapped[str] = mapped_column(String, default="")
    # 循环任务的模板来源（实例任务的 repeat_source_id 指向模板；模板本身为空）
    repeat_source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 时长预估（分钟）：AI 批量预估或手动填写；actual_minutes 为完成时手填的实际耗时
    est_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    goal: Mapped[Goal | None] = relationship(back_populates="tasks")
    checkins: Mapped[list["Checkin"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    time_logs: Mapped[list["TimeLog"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    subtasks: Mapped[list["TaskSubtask"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskSubtask.sort_order"
    )


class TaskSubtask(Base):
    """任务的子任务（checklist），如实验步骤拆分。"""

    __tablename__ = "task_subtasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String, nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    task: Mapped[Task] = relationship(back_populates="subtasks")


class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    task: Mapped[Task] = relationship(back_populates="checkins")


class TimeLog(Base):
    __tablename__ = "time_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # task_id 可空：自由番茄钟（不绑定任务）的计时记录 task_id 为空
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String, default="manual")  # manual/pomodoro
    note: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    task: Mapped[Task | None] = relationship(back_populates="time_logs")


class FreePomodoro(Base):
    """自由番茄钟：不绑定具体任务的学习专注计时（后端权威计时源）。

    - status: running / paused / done / abandoned
    - phase: work / break（free 模式恒为 work）
    - work_seconds: 已累计有效工作秒（暂停期间不计，轮次结算后继续累计）
    - rounds: 已完成的番茄轮数（tomato 模式，每轮结算写一条 TimeLog）
    - 计时计算：有效工作秒 = work_seconds + (running 且 work 阶段 ? now - phase_started_at : 0)
    - 桌面窗口/页面关闭后仍由后端计时，退出进程时 shutdown 保存。
    """

    __tablename__ = "free_pomodoros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String, default="")  # 学习状态文字（如「数学」「写综述」）
    mode: Mapped[str] = mapped_column(String, default="tomato")  # tomato / free
    status: Mapped[str] = mapped_column(String, default="running")
    work_min: Mapped[int] = mapped_column(Integer, default=25)  # free 模式存 0（无倒计时）
    break_min: Mapped[int] = mapped_column(Integer, default=5)
    rounds: Mapped[int] = mapped_column(Integer, default=0)
    work_seconds: Mapped[int] = mapped_column(Integer, default=0)
    phase: Mapped[str] = mapped_column(String, default="work")
    phase_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String, default="")
    folder: Mapped[str] = mapped_column(String, default="")  # 文件夹路径，如 文献/红外
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 回收站软删标记


class NoteImage(Base):
    __tablename__ = "note_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[int | None] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    original_name: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    note: Mapped[Note | None] = relationship()


class NoteAttachment(Base):
    """笔记附件：PDF/Word/任意文件，存 data/attachments。"""

    __tablename__ = "note_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String, nullable=False)  # 磁盘存储名（uuid）
    original_name: Mapped[str] = mapped_column(String, default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    note: Mapped[Note] = relationship()


class LiteratureItem(Base):
    __tablename__ = "literature_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zotero_key: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    zotero_version: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Zotero 条目版本号，用于增量刷新元数据
    title: Mapped[str] = mapped_column(String, nullable=False)
    authors: Mapped[str] = mapped_column(Text, default="[]")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publication: Mapped[str] = mapped_column(String, default="")
    item_type: Mapped[str] = mapped_column(String, default="journalArticle")
    abstract: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String, default="")
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    read_status: Mapped[str] = mapped_column(String, default="unread")  # unread/reading/read
    my_notes: Mapped[str] = mapped_column(Text, default="")
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
    )
    collection_keys: Mapped[str] = mapped_column(String, default="")  # Zotero 集合 key（逗号分隔）
    url: Mapped[str] = mapped_column(String, default="")
    doi: Mapped[str] = mapped_column(String, default="")
    journal_level: Mapped[str] = mapped_column(String, default="")  # 中科院分区/会议等级，如「中科院二区」
    impact_factor: Mapped[str] = mapped_column(String, default="")  # 影响因子，如 5.8
    pdf_path: Mapped[str] = mapped_column(String, default="")  # 本地 PDF 文件名（存 data/pdfs），空=无
    read_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # 置「已读」的日期，阅读计划统计用
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ZoteroCollection(Base):
    __tablename__ = "zotero_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zotero_key: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, default="")
    parent_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    week_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    content: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ReminderLog(Base):
    __tablename__ = "reminder_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=0)  # 3 / 1 / 0 天
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class StudyLog(Base):
    __tablename__ = "study_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    dataset: Mapped[str] = mapped_column(String, default="")
    model: Mapped[str] = mapped_column(String, default="")
    metrics: Mapped[str] = mapped_column(Text, default="{}")  # JSON key-value
    baseline: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="running")  # running/done/archived
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    venue: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="planning")  # planning/writing/draft/polish/submitted/revision/accepted
    submitted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class DailyItem(Base):
    """今日清单项：待办/进行中的当日计划，未完成自动顺延。"""

    __tablename__ = "daily_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, default="manual")  # task/habit/literature/manual/ai
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    quadrant: Mapped[str] = mapped_column(String, default="important_urgent")
    # important_urgent / important_not / not_urgent_important / not_important_not
    weight: Mapped[int] = mapped_column(Integer, default=10)  # 1-100
    pomodoros: Mapped[int] = mapped_column(Integer, default=0)
    time_range: Mapped[str] = mapped_column(String, default="")  # 如 09:00-10:30
    est_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 清单项独立预估时长（kind=task 有关联任务时以任务为准）
    status: Mapped[str] = mapped_column(String, default="pending")  # pending/done
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 任务页联动置 done 的时间戳（非空=任务页发起的完成）；手动勾选为 NULL。
    # 用于取消勾选/恢复任务时区分来源，避免误伤任务页手动完成的任务。
    auto_done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # AI 每日整理自动落地的项（重新生成时只替换当天未完成的自动项；用户手动项不受影响）
    auto_landed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Skill(Base):
    """技能栈：如 PyTorch / 红外小目标算法 / Transformer，进度按阶段平均。"""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    goal: Mapped[Goal | None] = relationship()
    stages: Mapped[list["SkillStage"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan", order_by="SkillStage.order"
    )


class SkillStage(Base):
    """技能的一个阶段，如「入门→进阶→实战」，progress 0-100。"""

    __tablename__ = "skill_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    skill: Mapped[Skill] = relationship(back_populates="stages")


class AiRecord(Base):
    """AI 调用历史记录（功能/输入摘要/结果），供 AI 中心回看。"""

    __tablename__ = "ai_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    feature: Mapped[str] = mapped_column(String, default="")  # summarize/daily-plan/plan/...
    summary: Mapped[str] = mapped_column(String, default="")  # 输入摘要（截断）
    result: Mapped[str] = mapped_column(Text, default="")     # 结果（截断）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class OJProblem(Base):
    """刷题记录：LeetCode/OJ 题目，带难度/标签/状态/打卡日志。"""

    __tablename__ = "oj_problems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)  # 如「1. 两数之和」
    platform: Mapped[str] = mapped_column(String, default="LeetCode")  # LeetCode/牛客/洛谷/...
    difficulty: Mapped[str] = mapped_column(String, default="medium")  # easy/medium/hard
    tags: Mapped[str] = mapped_column(String, default="")  # 逗号分隔，如 数组,双指针
    status: Mapped[str] = mapped_column(String, default="todo")  # todo/doing/done
    url: Mapped[str] = mapped_column(String, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    solves: Mapped[list["OJSolve"]] = relationship(
        back_populates="problem", cascade="all, delete-orphan"
    )


class OJSolve(Base):
    """刷题打卡日志：每次 AC/复刷 记一条，用于每日刷题数与连续天数统计。"""

    __tablename__ = "oj_solves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("oj_problems.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String, default="solve")  # solve(AC)/review(复刷)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    problem: Mapped[OJProblem] = relationship(back_populates="solves")


class JobApplication(Base):
    """求职投递管理：公司/岗位/阶段状态机 + 笔试面试时间线。"""

    __tablename__ = "job_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[str] = mapped_column(String, default="")  # 岗位/方向
    city: Mapped[str] = mapped_column(String, default="")
    channel: Mapped[str] = mapped_column(String, default="")  # 内推人/渠道/官网
    resume_version: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="applied")
    # applied(已投递)/online_test(笔试)/interview1/interview2/interview3/hr/offer/rejected
    applied_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    events: Mapped[list["JobEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="JobEvent.event_date"
    )


class JobEvent(Base):
    """求职时间线事件：笔试/各轮面试/HR 沟通等。"""

    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE")
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    stage: Mapped[str] = mapped_column(String, default="interview1")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    application: Mapped[JobApplication] = relationship(back_populates="events")


class InterviewQuestion(Base):
    """面试八股知识库：问题+答案+掌握程度，支持间隔重复复习。"""

    __tablename__ = "interview_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, default="DL")
    # DL/CV/C++/Python/OS/网络/数据库/项目/算法
    answer: Mapped[str] = mapped_column(Text, default="")
    mastery: Mapped[int] = mapped_column(Integer, default=0)  # 0 不会 / 1 模糊 / 2 掌握
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    last_review: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_review: Mapped[date | None] = mapped_column(Date, nullable=True)  # 到期复习日
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Reminder(Base):
    """琐事提醒：一次性/每日/每周/每月循环，支持多次提前提醒（最多 5 次，每次提前分钟数可配）。"""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    remind_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # 首次提醒时间（精确到分钟）
    repeat: Mapped[str] = mapped_column(String, default="none")  # none/daily/weekly/monthly
    advance_minutes: Mapped[str] = mapped_column(String, default="")  # JSON 数组，如 [10,60,1440]，最多 5 个
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="pending")  # pending/done（done 仅一次性提醒归档用）
    last_done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 周期提醒「本次已处理」标记
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class DailyPaper(Base):
    """每日论文推荐：每天精选一篇红外小目标检测领域论文（OpenAlex 检索真实引用数 + AI 中文导读）。

    生成：首次打开工作台懒生成（当天唯一 paper_date）；去重跳过文献库已有/历史推荐过的标题；
    三档评价（rating: useful/general/not_interested）+ 标记已读 + 一键入库（literature_id 关联文献库）。
    """

    __tablename__ = "daily_papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    authors: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publication: Mapped[str] = mapped_column(String, default="")  # 期刊/会议名
    doi: Mapped[str] = mapped_column(String, default="")
    url: Mapped[str] = mapped_column(String, default="")
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 真实引用数（尽力而为）
    abstract: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")  # AI 中文导读
    why_read: Mapped[str] = mapped_column(Text, default="")  # 为什么值得读
    relation: Mapped[str] = mapped_column(Text, default="")  # 与用户方向的关联
    rating: Mapped[str] = mapped_column(String, default="")  # useful/general/not_interested
    read: Mapped[bool] = mapped_column(Boolean, default=False)  # 标记已读
    literature_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 一键入库关联的文献库条目
    pdf_file: Mapped[str] = mapped_column(String, default="")  # 已下载的 PDF 文件名（存 daily_paper 目录），空=未找到开放 PDF
    zotero_key: Mapped[str | None] = mapped_column(String, nullable=True)  # 推送 Zotero 成功的条目 key（自动推送/手动归档后回填）
    zotero_pdf_key: Mapped[str | None] = mapped_column(String, nullable=True)  # Zotero 里该条目下已挂的 PDF 附件 key（空=附件未挂）
    source: Mapped[str] = mapped_column(String, default="openalex")  # openalex/arxiv
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ReminderSendLog(Base):
    """琐事提醒发送去重：每个 (reminder_id, trigger_time) 只发一次通知。"""

    __tablename__ = "reminder_send_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reminder_id: Mapped[int] = mapped_column(
        ForeignKey("reminders.id", ondelete="CASCADE"), index=True
    )
    trigger_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # 实际计划触发时刻


class AttendanceDay(Base):
    """考勤日：一天一条记录（实验室/工位在岗计时）。

    - day_closed：用户点了「结束今日」；之后仍可重新「到位」（自动重置）。
    - 在岗时长 = 各 AttendanceSegment 时长之和（离开/暂停期间不计）。
    """

    __tablename__ = "attendance_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    day_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    segments: Mapped[list["AttendanceSegment"]] = relationship(
        back_populates="day", cascade="all, delete-orphan", order_by="AttendanceSegment.start_at"
    )


class AttendanceSegment(Base):
    """在岗时间段：到位→离开 为一段；end_at 为空表示正在计时。"""

    __tablename__ = "attendance_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day_id: Mapped[int] = mapped_column(ForeignKey("attendance_days.id", ondelete="CASCADE"))
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    leave_reason: Mapped[str] = mapped_column(String, default="")  # 离开原因（上课/吃饭/其他/自定义）
    # 跨天自动收口的标记（疑似忘记点「离开」被截到 23:59:59），供前端提示修正；用户修正后清除
    auto_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    day: Mapped[AttendanceDay] = relationship(back_populates="segments")


class SelfSyncLink(Base):
    """Self_analysis 回写关联：工作台实体 ↔ 计划文档中的一行。

    用于「攒批同步」：比较工作台实体当前状态与 md 行内容，生成改动清单（勾选/
    字段/删除/新增），经双重确认后写回；行级合并（找不到对应行即跳过并报告）。
    """

    __tablename__ = "self_sync_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file: Mapped[str] = mapped_column(String, nullable=False)  # 相对 Self_analysis 根目录的路径
    section: Mapped[str] = mapped_column(String, default="")  # 所在小节标题（如 9.30（周三））
    line_text: Mapped[str] = mapped_column(Text, default="")  # 导入时该行文本（含 checkbox 前缀）
    entity: Mapped[str] = mapped_column(String, default="daily_item")  # daily_item / task（工作台任务块）
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 上次同步时行号（识别 md 手改行）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class WeightRecord(Base):
    """体重记录（生活数据）：一天一条，取当天最后填写值。（展示在「生活记录」页）"""

    __tablename__ = "weight_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)  # 单位：斤
    note: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class DrinkLog(Base):
    """饮品记录（生活数据）：含 AI/联网检索估算的营养成分（糖/脂肪/热量）。"""

    __tablename__ = "drink_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    volume_ml: Mapped[int] = mapped_column(Integer, default=0)  # 容量（毫升），0=未填
    sugar_g: Mapped[float] = mapped_column(Float, default=0)  # 糖（克，整杯合计）
    fat_g: Mapped[float] = mapped_column(Float, default=0)  # 脂肪（克，整杯合计）
    calories: Mapped[float] = mapped_column(Float, default=0)  # 热量（千卡，整杯合计）
    ai_analyzed: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否经 AI 分析
    ai_note: Mapped[str] = mapped_column(String, default="")  # AI 估算说明（依据/不确定性）
    note: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RelaxLog(Base):
    """夜间放松记录（私密生活数据，界面隐晦展示）：一次一条，计数即条数。"""

    __tablename__ = "relax_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    note: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
