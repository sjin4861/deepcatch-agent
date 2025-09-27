from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime


class CallState(str, Enum):
    pending = "pending"
    preparing = "preparing"
    dialing = "dialing"
    ringing = "ringing"
    connected = "connected"
    streaming = "streaming"
    extracting = "extracting"
    completed = "completed"
    no_answer = "no_answer"
    failed = "failed"
    canceled = "canceled"


@dataclass
class TranscriptTurn:
    speaker: str  # 'agent' | 'shop'
    text: str
    ts: str


@dataclass
class ExtractedSlots:
    price_quote: Optional[str] = None
    capacity_confirmed: Optional[int] = None
    departure_time: Optional[str] = None
    conditions_notes: Optional[str] = None

    def merge(self, other: 'ExtractedSlots') -> 'ExtractedSlots':
        if other.price_quote:
            self.price_quote = other.price_quote
        if other.capacity_confirmed is not None:
            self.capacity_confirmed = other.capacity_confirmed
        if other.departure_time:
            self.departure_time = other.departure_time
        if other.conditions_notes:
            self.conditions_notes = other.conditions_notes
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            'price_quote': self.price_quote,
            'capacity_confirmed': self.capacity_confirmed,
            'departure_time': self.departure_time,
            'conditions_notes': self.conditions_notes,
        }


@dataclass
class CallResult:
    call_sid: Optional[str]
    state: CallState
    shop_name: Optional[str]
    phone: Optional[str]
    transcript: List[TranscriptTurn]
    slots: ExtractedSlots
    started_at: Optional[str]
    ended_at: Optional[str]
    error_code: Optional[str] = None
    message: Optional[str] = None

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            'call_sid': self.call_sid,
            'state': self.state,
            'shop_name': self.shop_name,
            'phone': self.phone,
            'transcript_len': len(self.transcript),
            'slots': self.slots.to_dict(),
            'started_at': self.started_at,
            'ended_at': self.ended_at,
            'error_code': self.error_code,
            'message': self.message,
        }


@dataclass
class CallGraphState:
    # externally supplied (rename plan_details -> call_plan_details to avoid main graph key collision)
    call_plan_details: Any
    shop_name: Optional[str]
    phone: Optional[str] = None  # 대상 상점 전화번호 (place_call_node에서 채워짐)
    scenario_id: Optional[str] = None
    scenario_active: bool = False
    scenario_finished: bool = False

    # dynamic/runtime
    call_state: CallState = CallState.pending
    call_sid: Optional[str] = None
    transcript: List[TranscriptTurn] = field(default_factory=list)
    slots: ExtractedSlots = field(default_factory=ExtractedSlots)
    attempt_count: int = 0
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    max_ring_seconds: int = 25
    max_total_seconds: int = 600

    def add_turn(self, speaker: str, text: str):
        self.transcript.append(TranscriptTurn(speaker=speaker, text=text, ts=datetime.utcnow().isoformat()+"Z"))

    def build_result(self) -> CallResult:
        return CallResult(
            call_sid=self.call_sid,
            state=self.call_state,
            shop_name=self.shop_name,
            phone=self.phone,
            transcript=self.transcript,
            slots=self.slots,
            started_at=self.started_at,
            ended_at=self.ended_at,
            error_code=self.error_code,
            message=self.error_message,
        )
