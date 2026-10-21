import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .config import DATA_DIR
from .database import Base, SessionLocal, engine
from .migrate import run_migrations
from .routers import (
    ai,
    attendance,
    attendance_pill,
    backup,
    checklist_widget,
    daily,
    daily_paper,
    export,
    free_pomodoro,
    goals,
    interview,
    jobs,
    life,
    literature,
    maintenance,
    notes,
    oj,
    pomodoro,
    reminder_pill,
    reminders,
    research,
    reviews,
    self_analysis,
    settings,
    skills,
    stats,
    studylog,
    tasks,
    voice,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .services import reminder
    from .services.active_sessions import startup_recovery
    from .services.backups import auto_backup

    # 启动自愈：恢复上次退出时暂停的任务番茄钟 + 收尾异常退出的残留计时
    startup_recovery()
    # 延后任务到期回归：阶段进入 90 天窗口的 deferred 任务恢复为待办
    from .services.task_flow import reactivate_deferred_tasks

    _db = SessionLocal()
    try:
        reactivate_deferred_tasks(_db)
    finally:
        _db.close()
    # 桌面悬浮清单：上次退出前开着则自动恢复（偏好存 data/checklist_widget.json）
    from .services import checklist_widget as _checklist_widget

    _checklist_widget.restore_on_startup()
    # 桌面胶囊（考勤/提醒）：上次退出前开着则延迟恢复（偏好存 data/pill_*.json）
    from .services import attendance_pill as _att_pill
    from .services import reminder_pill as _rm_pill

    _att_pill.PILL.restore_on_startup()
    _rm_pill.PILL.restore_on_startup()
    reminder.start_scheduler()
    auto_backup()
    yield


app = FastAPI(title="研究生工作台", version="0.1.0", lifespan=lifespan)

# 全局日志：写入 data/logs/workbench.log，任何未捕获异常都会留痕
_LOG_DIR = DATA_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.FileHandler(_LOG_DIR / "workbench.log", encoding="utf-8"), logging.StreamHandler()],
)


@app.exception_handler(Exception)
async def _log_unhandled(request: Request, exc: Exception):
    import traceback

    logging.getLogger("workbench").error(
        "Unhandled %s %s: %s\n%s", request.method, request.url.path, exc, traceback.format_exc()
    )
    return JSONResponse(status_code=500, content={"detail": f"服务器内部错误：{exc}"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
run_migrations()

app.include_router(tasks.router)
app.include_router(pomodoro.router)
app.include_router(goals.router)
app.include_router(notes.router)
app.include_router(reviews.router)
app.include_router(settings.router)
app.include_router(ai.router)
app.include_router(literature.router)
app.include_router(backup.router)
app.include_router(stats.router)
app.include_router(studylog.router)
app.include_router(voice.router)
app.include_router(daily.router)
app.include_router(skills.router)
app.include_router(research.router)
app.include_router(maintenance.router)
app.include_router(oj.router)
app.include_router(jobs.router)
app.include_router(life.router)
app.include_router(interview.router)
app.include_router(export.router)
app.include_router(reminders.router)
app.include_router(free_pomodoro.router)
app.include_router(daily_paper.router)
app.include_router(attendance.router)
app.include_router(self_analysis.router)
app.include_router(checklist_widget.router)
app.include_router(attendance_pill.router)
app.include_router(reminder_pill.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 未匹配的 /api 路径统一返回 404（避免落到前端静态文件返回 index.html/405）
@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def api_not_found(rest: str):
    raise HTTPException(404, "接口不存在")


FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
