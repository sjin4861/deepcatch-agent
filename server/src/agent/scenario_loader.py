from __future__ import annotations

import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

from src.config import settings, logger


def load_scenario_steps(scenario_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load scenario JSON script from configured directory.

    Expected file structure: <scenario_dir>/<scenario_id>.json with schema:
      { "id": "scenario1", "steps": [ {"role": "assistant"|"user", "text": "..."}, ... ] }
    Returns list of step dicts; empty on failure.
    """
    scenario_dir = settings.scenario_dir
    if not settings.scenario_mode:
        return []
    sid = scenario_id or settings.scenario_id
    if not scenario_dir or not sid:
        return []
    path = Path(scenario_dir) / f"{sid}.json"
    if not path.exists():
        candidates = []
        # 1) CWD 기준 상대 재조합
        candidates.append(Path.cwd() / scenario_dir / f"{sid}.json")
        # 2) 'server/data/scenarios' 형태가 중복되었을 가능성 → 'server/' 한 번 제거
        if scenario_dir.startswith('server/'):
            trimmed = scenario_dir[len('server/') :]
            candidates.append(Path.cwd() / trimmed / f"{sid}.json")
        # 3) 'data/scenarios' 직접
        candidates.append(Path.cwd() / 'data' / 'scenarios' / f"{sid}.json")
        # 4) src 기준 (config 파일 위치 인접)
        candidates.append(Path(__file__).resolve().parents[2] / 'data' / 'scenarios' / f"{sid}.json")
        found = None
        for c in candidates:
            if c.exists():
                found = c
                break
        if found is None:
            logger.warning("시나리오 파일을 찾을 수 없습니다: %s | tried %d fallbacks", path, len(candidates))
            return []
        path = found
    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        # --- Format A: { "steps": [ {"role":..., "text":...}, ... ] }
        steps = data.get("steps")
        if isinstance(steps, list):
            normalized = []
            for idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                role = step.get("role") or "assistant"
                text = step.get("text") or ""
                if not text:
                    continue
                normalized.append({"role": role, "text": text, "idx": idx})
            if normalized:
                return normalized

        # --- Format B: { "assistant_lines": ["...", "..."] }
        assistant_lines = data.get("assistant_lines")
        if isinstance(assistant_lines, list):
            normalized = []
            for idx, line in enumerate(assistant_lines):
                if not isinstance(line, str) or not line.strip():
                    continue
                normalized.append({"role": "assistant", "text": line.strip(), "idx": idx})
            return normalized
        return []
    except Exception as e:
        logger.error("시나리오 로딩 실패 (%s): %s", path, e)
        return []


class ScenarioState:
    """In-memory cursor for progressing through a scenario script."""

    def __init__(self, steps: List[Dict[str, Any]]):
        self.steps = steps
        self.cursor = 0

    def next_assistant_line(self) -> Optional[str]:
        while self.cursor < len(self.steps):
            step = self.steps[self.cursor]
            self.cursor += 1
            if step["role"] == "assistant":
                return step["text"]
        return None

    def inject_user_line(self, text: str):  # optional: track user path
        pass

    def finished(self) -> bool:
        return self.cursor >= len(self.steps)
