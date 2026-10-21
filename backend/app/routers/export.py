import io
import json

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Experiment, Task, TimeLog

router = APIRouter(prefix="/api/export", tags=["export"])

TYPE_LABEL = {"habit": "习惯", "study": "学习", "once": "一次性"}
STATUS_LABEL = {"todo": "待办", "doing": "进行中", "done": "已完成", "archived": "已归档", "deferred": "已延后"}
LOG_KIND_LABEL = {"manual": "手动计时", "pomodoro": "番茄钟"}
EXP_STATUS_LABEL = {"running": "进行中", "done": "已完成", "archived": "已归档"}


def _xlsx_response(filename: str, headers: list, rows: list) -> Response:
    """生成 .xlsx（openpyxl）：Excel 直接打开中文不乱码、数字/日期不丢格式。

    openpyxl 延迟到真正导出时才导入（模块级导入会随后端启动常驻 ~13MB 内存，
    而导出是低频功能——2026-10-14 内存审计）。
    """
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "导出数据"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    # 表头加粗 + 列宽自适应
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    for col in ws.columns:
        width = max(len(str(c.value or "")) for c in col) + 4
        ws.column_dimensions[col[0].column_letter].width = min(max(width, 8), 60)
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tasks")
def export_tasks(db: Session = Depends(get_db)):
    """任务完成记录：任务 + 完成情况 + 累计时长/番茄/打卡天数。"""
    rows = []
    for t in db.query(Task).filter(Task.status.notin_(["archived", "deferred"])).order_by(Task.id).all():
        total_sec = sum(ts.duration_seconds or 0 for ts in t.time_logs)
        pomos = sum(1 for ts in t.time_logs if ts.kind == "pomodoro" and ts.end_time)
        checkins = len(t.checkins)
        rows.append(
            [
                t.id,
                t.title,
                TYPE_LABEL.get(t.task_type, t.task_type),
                STATUS_LABEL.get(t.status, t.status),
                t.priority,
                t.due_date.isoformat() if t.due_date else "",
                t.created_at.isoformat(),
                t.completed_at.isoformat() if t.completed_at else "",
                total_sec,
                pomos,
                checkins,
                t.tags or "",
            ]
        )
    return _xlsx_response(
        "tasks.xlsx",
        ["ID", "标题", "类型", "状态", "优先级", "截止日期", "创建时间", "完成时间", "累计时长(秒)", "番茄数", "打卡天数", "标签"],
        rows,
    )


@router.get("/timelogs")
def export_timelogs(db: Session = Depends(get_db)):
    """计时 / 番茄明细：每条投入记录。"""
    rows = []
    for lg in db.query(TimeLog).order_by(TimeLog.start_time.desc()).all():
        t = db.get(Task, lg.task_id) if lg.task_id else None
        rows.append(
            [
                lg.start_time.isoformat(),
                lg.end_time.isoformat() if lg.end_time else "",
                LOG_KIND_LABEL.get(lg.kind, lg.kind),
                lg.duration_seconds or 0,
                t.title if t else (lg.note or "自由番茄"),
                lg.note or "",
            ]
        )
    return _xlsx_response(
        "timelogs.xlsx",
        ["开始时间", "结束时间", "类型", "时长(秒)", "任务", "备注"],
        rows,
    )


@router.get("/experiments")
def export_experiments(db: Session = Depends(get_db)):
    """实验记录（指标为 JSON 串，含创建/更新时间）。"""
    rows = []
    for e in db.query(Experiment).filter(Experiment.status != "archived").order_by(Experiment.id).all():
        try:
            metrics = json.loads(e.metrics or "{}")
        except Exception:
            metrics = {}
        rows.append(
            [
                e.id,
                e.title,
                e.dataset,
                e.model,
                e.baseline,
                EXP_STATUS_LABEL.get(e.status, e.status),
                json.dumps(metrics, ensure_ascii=False),
                e.notes or "",
                e.created_at.isoformat(),
                e.updated_at.isoformat(),
            ]
        )
    return _xlsx_response(
        "experiments.xlsx",
        ["ID", "标题", "数据集", "模型", "对比基线", "状态", "指标", "备注", "创建时间", "更新时间"],
        rows,
    )