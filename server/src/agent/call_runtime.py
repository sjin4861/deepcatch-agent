from __future__ import annotations

from threading import Lock
from typing import List, Dict, Any, Optional
from datetime import datetime

_transcript_lock = Lock()
_status_lock = Lock()
_transcripts: Dict[str, List[Dict[str, Any]]] = {}
_status: Dict[str, str] = {}

FINAL_STATUSES = {"completed", "failed", "no-answer", "canceled", "busy"}


def append_transcript(call_sid: Optional[str], speaker: str, text: str):  # pragma: no cover - IO wrapper
    if not call_sid or not text:
        return
    with _transcript_lock:
        _transcripts.setdefault(call_sid, []).append({
            "speaker": speaker,
            "text": text,
            "ts": datetime.utcnow().isoformat() + "Z",
        })


def drain_transcript(call_sid: Optional[str]):  # pragma: no cover - IO wrapper
    if not call_sid:
        return []
    with _transcript_lock:
        items = _transcripts.get(call_sid, [])
        if not items:
            return []
        _transcripts[call_sid] = []
        return items


def update_status(call_sid: Optional[str], status: Optional[str]):  # pragma: no cover
    if not call_sid or not status:
        return
    with _status_lock:
        _status[call_sid] = status


def get_status(call_sid: Optional[str]) -> Optional[str]:  # pragma: no cover
    if not call_sid:
        return None
    with _status_lock:
        return _status.get(call_sid)


def is_final(call_sid: Optional[str]) -> bool:  # pragma: no cover
    st = get_status(call_sid)
    return st in FINAL_STATUSES


def cleanup(call_sid: Optional[str]):  # pragma: no cover
    if not call_sid:
        return
    with _transcript_lock:
        _transcripts.pop(call_sid, None)
    with _status_lock:
        _status.pop(call_sid, None)
