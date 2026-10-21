import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from ..config import DATA_DIR
from ..services import whisper_service

router = APIRouter(prefix="/api/voice", tags=["voice"])

AUDIO_DIR = DATA_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/transcribe")
async def transcribe_voice(file: UploadFile):
    if file is None or not file.filename:
        raise HTTPException(400, "缺少音频文件")
    suffix = Path(file.filename or "audio.webm").suffix.lower() or ".webm"
    dest = AUDIO_DIR / f"{uuid.uuid4().hex}{suffix}"
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            text = whisper_service.transcribe(dest)
        except Exception as e:
            print(f"[voice] transcribe failed: {e}")
            raise HTTPException(500, f"语音转写失败：{e}")
        return {"text": text}
    finally:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
