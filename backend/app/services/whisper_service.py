import threading
from pathlib import Path

from ..config import DATA_DIR

_model = None
_lock = threading.Lock()
MODEL_SIZE = "base"


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from faster_whisper import WhisperModel

                _model = WhisperModel(
                    MODEL_SIZE,
                    device="cpu",
                    compute_type="int8",
                    download_root=str(DATA_DIR / "whisper-models"),
                )
    return _model


def transcribe(audio_path: Path) -> str:
    model = _get_model()
    segments, info = model.transcribe(str(audio_path), language="zh", vad_filter=True)
    text = "".join(seg.text for seg in segments).strip()
    return text or ""
