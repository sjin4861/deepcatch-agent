from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from .types import ChatToolResult


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def make_tool_result(
    *,
    tool: str,
    title: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> ChatToolResult:
    return ChatToolResult(
        id=str(uuid4()),
        toolName=tool,
        title=title,
        content=content,
        metadata=metadata,
        createdAt=_now_iso(),
    )
