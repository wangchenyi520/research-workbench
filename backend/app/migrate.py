from sqlalchemy import inspect, text

from .database import engine

MIGRATIONS = [
    ("tasks", "sort_order", "INTEGER DEFAULT 0"),
    ("tasks", "completed_at", "DATETIME"),
    ("notes", "goal_id", "INTEGER"),
    ("notes", "folder", "VARCHAR DEFAULT ''"),
    ("literature_items", "read_status", "VARCHAR(20) DEFAULT 'unread'"),
    ("literature_items", "my_notes", "TEXT DEFAULT ''"),
    ("literature_items", "goal_id", "INTEGER"),
    ("literature_items", "collection_keys", "VARCHAR DEFAULT ''"),
    ("literature_items", "zotero_version", "INTEGER"),
    ("literature_items", "journal_level", "VARCHAR DEFAULT ''"),
    ("literature_items", "impact_factor", "VARCHAR DEFAULT ''"),
    ("daily_items", "time_range", "VARCHAR DEFAULT ''"),
    ("daily_items", "auto_done_at", "DATETIME"),
    ("tasks", "repeat_weekdays", "VARCHAR DEFAULT ''"),
    ("tasks", "repeat_source_id", "INTEGER"),
    ("notes", "deleted_at", "DATETIME"),
    ("literature_items", "pdf_path", "VARCHAR DEFAULT ''"),
    ("literature_items", "read_date", "DATE"),
    ("tasks", "est_minutes", "INTEGER"),
    ("tasks", "actual_minutes", "INTEGER"),
    ("daily_items", "est_minutes", "INTEGER"),
    ("daily_papers", "pdf_file", "VARCHAR DEFAULT ''"),
    ("daily_papers", "zotero_key", "VARCHAR"),
    ("daily_papers", "zotero_pdf_key", "VARCHAR"),
    ("daily_items", "auto_landed", "BOOLEAN DEFAULT 0"),
    ("self_sync_links", "line_no", "INTEGER"),
    ("attendance_segments", "auto_closed", "BOOLEAN DEFAULT 0"),
]


def _rebuild_time_logs(conn):
    """time_logs.task_id 改可空（自由番茄钟不绑定任务）。

    SQLite 的 ALTER TABLE 无法修改列约束，需 12 步重建表：
    rename → create → insert → drop，幂等（task_id 已可空则跳过）。
    """
    insp = inspect(engine)
    try:
        cols = {c["name"]: c for c in insp.get_columns("time_logs")}
    except Exception:
        return
    if "task_id" not in cols:
        return
    if cols["task_id"].get("nullable"):
        return
    old = "time_logs_old"
    defs = []
    for c in insp.get_columns("time_logs"):
        t = (c["type"] or "").__str__()
        if c["name"] == "task_id":
            defs.append("task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE")
            continue
        seg = f"{c['name']} {t}"
        if not c.get("nullable"):
            seg += " NOT NULL"
        if c.get("primary_key"):
            seg += " PRIMARY KEY"
        defs.append(seg)
    conn.execute(text(f"ALTER TABLE time_logs RENAME TO {old}"))
    conn.execute(text(f"CREATE TABLE time_logs ({', '.join(defs)})"))
    conn.execute(
        text(
            f"INSERT INTO time_logs (id, task_id, start_time, end_time, duration_seconds, kind, note, created_at) "
            f"SELECT id, task_id, start_time, end_time, duration_seconds, kind, note, created_at FROM {old}"
        )
    )
    conn.execute(text(f"DROP TABLE {old}"))


def run_migrations():
    insp = inspect(engine)
    with engine.begin() as conn:
        _rebuild_time_logs(conn)
        for table, column, coltype in MIGRATIONS:
            try:
                cols = {c["name"] for c in insp.get_columns(table)}
            except Exception:
                continue
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
