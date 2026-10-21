from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Setting
from ..services import secure

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULTS = {
    "deepseek_api_key": "",
    "review_reminder_day": "6",   # 周日=6
    "review_reminder_time": "20:00",
    "theme": "light",             # light/dark
    "zotero_api_key": "",
    "zotero_user_id": "",
    "pomodoro_minutes": "25",
    "break_minutes": "5",
    "reminder_enabled": "true",
    "auto_backup_enabled": "true",
    "autostart_enabled": "false",
    "daily_ai_enabled": "true",                # 每日 AI 自动整理今日清单
    "daily_ai_auto_land": "true",              # AI 任务自动落进今日清单（可删改；关闭则只给建议手动采纳）
    "evening_view_enabled": "false",           # 早晚视角开关
    "evening_view_time": "22:00",              # 晚于该时间默认进「完成情况」视图
    "self_analysis_path": "",
    "research_profile": '{"direction":"","methods":"","stage":"","goal":"","writing_style":""}',
    "daily_paper_enabled": "true",               # 每日论文推荐开关（懒生成，首次打开工作台触发）
    "daily_paper_query": "infrared small target detection",  # 每日论文检索词（默认红外小目标检测）
}

# 敏感设置：返回时掩码展示，提交时若仍是掩码形式则保留原值
SENSITIVE_KEYS = ("deepseek_api_key", "zotero_api_key")


def _mask(value: str) -> str:
    v = value.strip()
    if not v:
        return ""
    if len(v) <= 8:
        return "****"
    return f"{v[:4]}****{v[-4:]}"


def _is_masked(value: str) -> bool:
    return "****" in value


def ensure_defaults(db: Session):
    existing = {s.key for s in db.query(Setting).all()}
    for k, v in DEFAULTS.items():
        if k not in existing:
            db.add(Setting(key=k, value=v))
    db.commit()


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    ensure_defaults(db)
    out = {}
    for s in db.query(Setting).all():
        v = secure.decrypt_str(s.value)  # 敏感值存库为密文，读出解密后再掩码
        if s.key in SENSITIVE_KEYS and v:
            v = _mask(v)
        out[s.key] = v
    return out


def _style_targets(key: str):
    """外观类设置 → 需要立即刷新的桌面窗口（保存后毫秒级生效，不再等 4 秒轮询）。"""
    if not (key.startswith("cap_") or key.startswith("checklist_widget_")):
        return []
    from ..services import attendance_pill, checklist_pill, checklist_widget, pomodoro_pill, reminder_pill

    mapping = {
        "checklist_widget_bg": [checklist_widget.notify_style, checklist_pill.PILL.notify_style],
        "checklist_widget_opacity": [checklist_widget.notify_style, checklist_pill.PILL.notify_style],
        "checklist_widget_bg_mode": [checklist_widget.notify_style],
        "cap_checklist_bg": [checklist_pill.PILL.notify_style],
        "cap_checklist_opacity": [checklist_pill.PILL.notify_style],
        "cap_attendance_bg": [attendance_pill.PILL.notify_style],
        "cap_attendance_opacity": [attendance_pill.PILL.notify_style],
        "cap_reminder_bg": [reminder_pill.PILL.notify_style],
        "cap_reminder_opacity": [reminder_pill.PILL.notify_style],
        "cap_pomodoro_bg": [pomodoro_pill.PILL.notify_style],
        "cap_pomodoro_opacity": [pomodoro_pill.PILL.notify_style],
    }
    return mapping.get(key, [])


@router.put("/{key}")
def set_setting(key: str, data: dict, db: Session = Depends(get_db)):
    s = db.get(Setting, key)
    value = data.get("value", "")
    # 前端提交的是掩码时，说明用户未修改，保留原值
    if key in SENSITIVE_KEYS and _is_masked(str(value)):
        return {"ok": True, "key": key, "value": s.value if s else value}
    # 敏感 Key 加密存储
    if key in SENSITIVE_KEYS and value:
        value = secure.encrypt_str(str(value))
    if not s:
        s = Setting(key=key, value=value)
        db.add(s)
    else:
        s.value = value
    db.commit()
    # 桌面窗口外观：立即通知对应窗口重读样式（失败不影响设置保存）
    for fn in _style_targets(key):
        try:
            fn()
        except Exception as e:
            print(f"[settings] style notify failed for {key}: {e}")
    return {"ok": True, "key": key, "value": value}


# ---------- 开机自启 ----------
def _autostart_command() -> str:
    import sys

    from ..config import BASE_DIR

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    desktop = BASE_DIR.parent / "desktop.py"
    return f'"{pythonw}" "{desktop}"'


@router.get("/autostart")
def get_autostart():
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        try:
            winreg.QueryValueEx(key, "Workbench")
            enabled = True
        except FileNotFoundError:
            enabled = False
        winreg.CloseKey(key)
        return {"enabled": enabled}
    except Exception:
        return {"enabled": False}


@router.post("/autostart")
def set_autostart(data: dict):
    enabled = bool(data.get("enabled", False))
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        if enabled:
            winreg.SetValueEx(key, "Workbench", 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(key, "Workbench")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return {"enabled": enabled}
    except Exception as e:
        return {"enabled": enabled, "error": str(e)}
