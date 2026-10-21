# -*- coding: utf-8 -*-
"""生活记录：体重（迁自作战计划，展示用）+ 饮品记录（AI 营养分析）+ 夜间放松（私密、隐晦展示）。

- 体重写入口沿用 /api/self-analysis/weight（同一张表），本页只读取与展示；
- 饮品/夜间放松为新表，随 create_all 自动建，无需迁移；
- 健康范围（每周上限）存 Setting：life_drink_weekly_limit / life_relax_weekly_limit。
"""
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DrinkLog, RelaxLog, Setting, WeightRecord
from ..services import deepseek, nutrition
from .ai import _record_ai

router = APIRouter(prefix="/api/life", tags=["life"])

LIMIT_KEYS = {"drink_weekly": "life_drink_weekly_limit", "relax_weekly": "life_relax_weekly_limit"}
LIMIT_DEFAULTS = {"drink_weekly": 3, "relax_weekly": 3}


def _get_limit(db: Session, key: str) -> int:
    row = db.get(Setting, LIMIT_KEYS[key])
    try:
        return max(0, min(99, int(row.value))) if row and row.value != "" else LIMIT_DEFAULTS[key]
    except (TypeError, ValueError):
        return LIMIT_DEFAULTS[key]


def _set_limit(db: Session, key: str, value) -> int:
    try:
        v = max(0, min(99, int(value)))
    except (TypeError, ValueError):
        v = LIMIT_DEFAULTS[key]
    row = db.get(Setting, LIMIT_KEYS[key])
    if row:
        row.value = str(v)
    else:
        db.add(Setting(key=LIMIT_KEYS[key], value=str(v)))
    return v


def _week_start(today: date) -> date:
    return today - timedelta(days=today.weekday())


def _parse_date(v) -> date:
    if not v:
        return date.today()
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        raise HTTPException(400, "日期格式不正确")


def _fnum(v, cap: float) -> float:
    try:
        return round(max(0.0, min(float(cap), float(v or 0))), 1)
    except (TypeError, ValueError):
        return 0.0


def _drink_dict(r: DrinkLog) -> dict:
    return {
        "id": r.id,
        "date": r.date.isoformat(),
        "name": r.name,
        "volume_ml": r.volume_ml or 0,
        "sugar_g": r.sugar_g or 0,
        "fat_g": r.fat_g or 0,
        "calories": r.calories or 0,
        "ai_analyzed": bool(r.ai_analyzed),
        "ai_note": r.ai_note or "",
        "note": r.note or "",
        "created_at": r.created_at.isoformat(timespec="minutes") if r.created_at else "",
    }


def _relax_dict(r: RelaxLog) -> dict:
    return {
        "id": r.id,
        "date": r.date.isoformat(),
        "note": r.note or "",
        "created_at": r.created_at.isoformat(timespec="minutes") if r.created_at else "",
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    today = date.today()
    ws = _week_start(today)
    ms = today.replace(day=1)

    weight_rows = db.query(WeightRecord).order_by(WeightRecord.date.desc()).limit(30).all()
    weight_rows = list(reversed(weight_rows))
    latest_w = weight_rows[-1] if weight_rows else None
    prev_w = weight_rows[-2] if len(weight_rows) > 1 else None

    drinks = db.query(DrinkLog).order_by(DrinkLog.date.desc(), DrinkLog.id.desc()).limit(200).all()
    week_drinks = [x for x in drinks if x.date >= ws]
    month_drinks = [x for x in drinks if x.date >= ms]

    relax = db.query(RelaxLog).order_by(RelaxLog.date.desc(), RelaxLog.id.desc()).limit(200).all()
    week_relax = [x for x in relax if x.date >= ws]
    month_relax = [x for x in relax if x.date >= ms]

    return {
        "today": today.isoformat(),
        "week_start": ws.isoformat(),
        "limits": {k: _get_limit(db, k) for k in LIMIT_KEYS},
        "weight": {
            "records": [{"date": r.date.isoformat(), "weight": r.weight, "note": r.note or ""} for r in weight_rows],
            "latest": ({"date": latest_w.date.isoformat(), "weight": latest_w.weight} if latest_w else None),
            "prev": ({"date": prev_w.date.isoformat(), "weight": prev_w.weight} if prev_w else None),
        },
        "drinks": {
            "week_count": len(week_drinks),
            "month_count": len(month_drinks),
            "week_sugar": round(sum(x.sugar_g or 0 for x in week_drinks), 1),
            "week_calories": round(sum(x.calories or 0 for x in week_drinks), 1),
            "records": [_drink_dict(x) for x in drinks[:60]],
        },
        "relax": {
            "week_count": len(week_relax),
            "month_count": len(month_relax),
            "records": [_relax_dict(x) for x in relax[:60]],
        },
    }


# ---------------------------------------------------------------- 饮品
@router.post("/drinks")
def add_drink(data: dict, db: Session = Depends(get_db)):
    name = str(data.get("name") or "").strip()[:60]
    if not name:
        raise HTTPException(400, "请输入饮品名称")
    d = _parse_date(data.get("date"))
    row = DrinkLog(
        date=d,
        name=name,
        volume_ml=int(_fnum(data.get("volume_ml"), 3000)),
        sugar_g=_fnum(data.get("sugar_g"), 500),
        fat_g=_fnum(data.get("fat_g"), 500),
        calories=_fnum(data.get("calories"), 5000),
        ai_analyzed=bool(data.get("ai_analyzed")),
        ai_note=str(data.get("ai_note") or "")[:120],
        note=str(data.get("note") or "")[:100],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "item": _drink_dict(row)}


@router.post("/drinks/analyze")
def analyze_drink(data: dict, db: Session = Depends(get_db)):
    """调用 DeepSeek 分析饮品营养（先联网检索参考资料，不做落库）。"""
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "请先填写饮品名称")
    if not deepseek.is_configured():
        raise HTTPException(400, "未配置 DeepSeek API Key，请先到设置页填写。")
    vol = None
    try:
        vol = max(0, min(3000, int(float(data.get("volume_ml"))))) if data.get("volume_ml") else None
    except (TypeError, ValueError):
        vol = None
    try:
        snippets, source = nutrition.search_drink_info(name)
    except Exception:
        snippets, source = [], ""
    research = "\n".join(f"- {s}" for s in snippets)
    try:
        result = deepseek.analyze_drink_nutrition(name, vol, research)
    except deepseek.AIError as e:
        raise HTTPException(e.status_code, str(e))
    except Exception as e:
        raise HTTPException(500, f"AI 调用异常：{e}")
    _record_ai("生活记录·饮品分析", f"{name} {vol or ''}ml", json.dumps(result, ensure_ascii=False))
    result["source"] = source  # food_db / web / ''
    result["snippet_count"] = len(snippets)
    return result


@router.delete("/drinks/{did}")
def delete_drink(did: int, db: Session = Depends(get_db)):
    row = db.get(DrinkLog, did)
    if not row:
        raise HTTPException(404, "记录不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 夜间放松
@router.post("/relax")
def add_relax(data: dict | None = None, db: Session = Depends(get_db)):
    data = data or {}
    d = _parse_date(data.get("date"))
    row = RelaxLog(date=d, note=str(data.get("note") or "").strip()[:100])
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "item": _relax_dict(row)}


@router.delete("/relax/{rid}")
def delete_relax(rid: int, db: Session = Depends(get_db)):
    row = db.get(RelaxLog, rid)
    if not row:
        raise HTTPException(404, "记录不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 健康范围（每周上限）
@router.put("/limits")
def set_limits(data: dict, db: Session = Depends(get_db)):
    out = {}
    for k in LIMIT_KEYS:
        if k in data and data[k] is not None:
            out[k] = _set_limit(db, k, data[k])
        else:
            out[k] = _get_limit(db, k)
    db.commit()
    return {"ok": True, "limits": out}
