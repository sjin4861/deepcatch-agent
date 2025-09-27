from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatToolResult(BaseModel):
    """Structured payload describing a tool call result."""

    id: str = Field(..., description="고유 ID")
    toolName: Optional[str] = Field(default=None, description="실행된 툴 이름")
    title: Optional[str] = Field(default=None, description="결과 제목")
    content: str = Field(..., description="결과 내용")
    metadata: Optional[Dict] = Field(default=None, description="추가 메타데이터")
    createdAt: str = Field(..., description="ISO8601 생성 시각")


class ChatRequest(BaseModel):
    """사용자 메시지를 담는 요청 모델."""

    message: str = Field(..., description="사용자 입력 문장")


class ChatResponse(BaseModel):
    """에이전트 응답 모델."""

    message: str = Field(..., description="어시스턴트가 사용자에게 전달할 문장")
    toolResults: List[ChatToolResult] = Field(
        default_factory=list,
        description="에이전트가 호출한 툴의 결과 목록",
    )
    callSuggested: bool = Field(
        default=False,
        description="모든 정보가 수집되어 전화 연결 제안을 하는지 여부",
    )


class AgentMessage(BaseModel):
    """그래프 내부에서 사용되는 메시지 표현."""

    role: ChatRole = Field(..., description="메시지 역할")
    content: str = Field(..., description="메시지 텍스트")
    toolCalls: Optional[List[ChatToolResult]] = Field(
        default=None,
        description="선택적으로 포함되는 툴 호출 결과",
    )
