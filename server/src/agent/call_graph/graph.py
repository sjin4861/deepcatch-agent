from __future__ import annotations

from typing import Callable, Any, Dict
try:  # optional dependency guard
    from langgraph.graph import StateGraph, END  # type: ignore
except Exception:  # pragma: no cover - fallback for dev environment without langgraph
    class _Terminal:  # minimal END sentinel
        pass
    END = _Terminal()

    class StateGraph:  # extremely small fake orchestrator
        def __init__(self, _state_type):
            self.nodes = {}
            self.edges = {}
            self.entry = None

        def add_node(self, name, fn):
            self.nodes[name] = fn

        def set_entry_point(self, name):
            self.entry = name

        def add_edge(self, start, end):
            self.edges.setdefault(start, []).append(end)

        def compile(self):
            class _Compiled:
                def __init__(self, outer):
                    self.outer = outer

                def invoke(self, state):
                    current = self.outer.entry
                    visited_guard = 0
                    while current and current is not END:
                        fn = self.outer.nodes[current]
                        state = fn(state)
                        # naive path selection: first edge; streaming loop will rely on condition inside node
                        outs = self.outer.edges.get(current, [])
                        if not outs:
                            break
                        # if stream node signals completion -> pick extract
                        if current == 'stream':
                            # heuristic: if state.call_state == 'extracting' choose 'extract'
                            if state.call_state.value == 'extracting':
                                nxt = 'extract'
                            else:
                                nxt = 'stream'
                            current = nxt if nxt in outs else outs[0]
                        else:
                            current = outs[0]
                        visited_guard += 1
                        if visited_guard > 200:  # avoid infinite loop in fallback
                            break
                    return state
            return _Compiled(self)
from .models import CallGraphState, CallState
from src.config import settings
try:  # scenario loader optional
    from ..scenario_loader import load_scenario_steps, ScenarioState
except Exception:  # pragma: no cover
    load_scenario_steps = lambda *a, **k: []  # type: ignore
    ScenarioState = None  # type: ignore

# Placeholder extraction + call service interfaces will be injected.

# Node implementations -------------------------------------------------

def prepare_node(state: CallGraphState, services) -> CallGraphState:
    state.call_state = CallState.preparing
    # Scenario 활성화 준비
    if settings.scenario_mode:
        steps = load_scenario_steps(state.scenario_id)
        if steps:
            state.scenario_active = True
            # 첫 assistant 선제 멘트가 있다면 transcript에 추가
            if ScenarioState is not None:
                scenario_obj = ScenarioState(steps)
                if settings.scenario_auto_feed_all:
                    # 모든 assistant 라인 즉시 공급
                    fed = 0
                    while True:
                        nxt = scenario_obj.next_assistant_line()
                        if not nxt:
                            state.scenario_finished = True
                            break
                        state.add_turn("assistant", nxt)
                        fed += 1
                else:
                    first_line = scenario_obj.next_assistant_line()
                    if first_line:
                        state.add_turn("assistant", first_line)
                state._scenario_obj = scenario_obj  # type: ignore
    return state


def place_call_node(state: CallGraphState, services) -> CallGraphState:
    if state.call_state != CallState.preparing:
        return state
    state.call_state = CallState.dialing
    result = services.start_reservation_call(details=state.call_plan_details, preferred_name=state.shop_name)
    # reuse existing start_reservation_call structure; adapt
    if result.success:
        state.call_sid = result.sid
        state.call_state = CallState.ringing
        state.started_at = services.now_iso()
        # 비즈니스 실제 전화번호를 state.phone에 기록 (Twilio 발신 from_number는 환경변수로 고정)
        try:
            selection = services.pick_business(details=state.call_plan_details, preferred_name=state.shop_name)
            if selection.business:
                state.phone = selection.business.phone  # type: ignore[attr-defined]
        except Exception:
            pass
    else:
        state.call_state = CallState.failed
        state.error_message = result.message or "call failed"
    return state


def monitor_node(state: CallGraphState, services) -> CallGraphState:
    # Poll runtime status buffer for updated telephony state.
    if state.call_state in (CallState.ringing, CallState.dialing, CallState.preparing):
        status = services.peek_call_status(state.call_sid) or ""
        if status in ("queued", "initiated", "dialing"):
            state.call_state = CallState.dialing
        elif status in ("ringing",):
            state.call_state = CallState.ringing
        elif status in ("answered", "in-progress", "completed"):
            # Treat answered/in-progress as connected/streaming entry
            if state.call_state != CallState.connected:
                state.call_state = CallState.connected
        elif status in ("no-answer", "busy"):
            state.call_state = CallState.no_answer
            state.ended_at = services.now_iso()
        elif status in ("failed", "canceled"):
            state.call_state = CallState.failed
            state.ended_at = services.now_iso()
    return state


def streaming_node(state: CallGraphState, services) -> CallGraphState:
    if state.call_state == CallState.connected:
        state.call_state = CallState.streaming
        # Simulate transcript ingestion (future: real socket handoff)
        for line in services.drain_transcript_buffer(state.call_sid):
            state.add_turn(line['speaker'], line['text'])
    else:
        if state.call_state == CallState.streaming:
            for line in services.drain_transcript_buffer(state.call_sid):
                state.add_turn(line['speaker'], line['text'])
    # Scenario 진행: assistant 스크립트 공급
    if getattr(state, "_scenario_obj", None) is not None and state.call_state == CallState.streaming and not state.scenario_finished:
        so = getattr(state, "_scenario_obj")
        if settings.scenario_auto_feed_all:
            # 남은 assistant 라인 모두 순차 추가
            fed = 0
            while True:
                nxt = so.next_assistant_line()
                if not nxt:
                    state.scenario_finished = True
                    break
                state.add_turn('assistant', nxt)
                fed += 1
            if fed:
                # 한 번에 공급 후 즉시 추출로 넘어가도록 한다
                pass
        else:
            # 기존 조건: 마지막이 user일 때 한 줄씩
            if state.transcript and state.transcript[-1].speaker == 'user':
                nxt = so.next_assistant_line()
                if nxt:
                    state.add_turn('assistant', nxt)
                else:
                    state.scenario_finished = True

    # termination conditions
    total_seconds = 0
    if state.started_at:
        # 단순 비교 (실제 파싱 생략) → 추후 ISO 파싱하여 실제 duration 계산 가능
        pass
    if services.call_completed(state.call_sid) or state.scenario_finished:
        state.call_state = CallState.extracting
    return state


def extract_node(state: CallGraphState, services) -> CallGraphState:
    if state.call_state != CallState.extracting:
        return state
    state.call_state = CallState.completed
    state.ended_at = services.now_iso()
    # run simple extraction
    slots = services.extract_slots_from_transcript(state.transcript)
    state.slots.merge(slots)
    return state


def finalize_node(state: CallGraphState, services) -> CallGraphState:
    # nothing extra for now
    return state

# Graph builder -------------------------------------------------------

def build_call_graph(services) -> StateGraph:
    g = StateGraph(CallGraphState)
    g.add_node("prepare", lambda s: prepare_node(s, services))
    g.add_node("place", lambda s: place_call_node(s, services))
    g.add_node("monitor", lambda s: monitor_node(s, services))
    g.add_node("stream", lambda s: streaming_node(s, services))
    g.add_node("extract", lambda s: extract_node(s, services))
    g.add_node("final", lambda s: finalize_node(s, services))

    g.set_entry_point("prepare")

    g.add_edge("prepare", "place")
    g.add_edge("place", "monitor")
    g.add_edge("monitor", "stream")
    g.add_edge("stream", "stream")  # loop until completion condition
    g.add_edge("stream", "extract")
    g.add_edge("extract", "final")
    g.add_edge("final", END)

    return g.compile()


class CallExecutionAgent:
    """Call sub-graph executor.

    LangGraph 사용 시 dataclass 기반 state merge에서 'call_plan_details'가 여러 노드 반환으로
    한 step 내 다중 값으로 간주되어 INVALID_CONCURRENT_GRAPH_UPDATE 오류가 발생했으므로
    단순 순차 실행기로 강제 전환한다.
    """
    def __init__(self, services):
        self.services = services
        # 보수적: LangGraph 미사용 (필요 시 토글 환경변수 도입 가능)
        self._simple = True
        if not self._simple:
            self.graph = build_call_graph(services)

    def run(self, initial: Dict[str, Any]):
        state = CallGraphState(**initial)
        if not getattr(self, '_simple', True):  # LangGraph 경로 (현재 비활성)
            result_state = self.graph.invoke(state)
            return result_state.build_result()

        # ---- 수동 순차 실행 ----
        services = self.services
        # 1) 준비
        state = prepare_node(state, services)
        if state.call_state == CallState.failed:
            return state.build_result()
        # 2) 발신 시도
        state = place_call_node(state, services)
        if state.call_state in (CallState.failed, CallState.no_answer):
            return state.build_result()
        # 시나리오가 준비 단계에서 이미 모두 공급되어 finished 되었다면 바로 추출로 전환
        if state.scenario_finished and state.call_state in (CallState.ringing, CallState.dialing, CallState.preparing):
            state.call_state = CallState.extracting
        # 3) 모니터 + 스트리밍 루프 (최대 n 회)
        max_loops = 5
        loop_count = 0
        while loop_count < max_loops and state.call_state not in (CallState.completed, CallState.failed, CallState.no_answer, CallState.extracting):
            prev_state = state.call_state
            state = monitor_node(state, services)
            state = streaming_node(state, services)
            if state.call_state == CallState.extracting:
                break
            # 변화 없으면 짧은 루프 종료 (실제 환경에서는 외부 webhook이 상태 갱신)
            if state.call_state == prev_state:
                loop_count += 1
            else:
                loop_count = 0
        # 4) 추출 단계
        if state.call_state == CallState.extracting:
            state = extract_node(state, services)
        # 5) 마무리
        state = finalize_node(state, services)
        return state.build_result()
