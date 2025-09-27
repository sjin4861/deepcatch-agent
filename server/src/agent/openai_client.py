from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Mapping, Optional

try:
    from openai import OpenAI as OpenAIBase
except ImportError:  # pragma: no cover - dependency guard
    OpenAIBase = None  # type: ignore

logger = logging.getLogger(__name__)


class OpenAIChatClient:
    """Thin wrapper around the OpenAI Chat Completions API."""

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.6"))
        self._client: Optional[Any] = None

        if not self.api_key:
            logger.info("OPENAI_API_KEY not set; falling back to templated responses.")
            return

        if OpenAIBase is None:
            logger.warning("openai package unavailable; install to enable GPT responses.")
            return

        self._client = OpenAIBase(api_key=self.api_key)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def generate(self, prompt: str, messages: Iterable[Mapping[str, str]]) -> str:
        if not self._client:
            raise RuntimeError("OpenAI client is not configured.")

        completion = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "system", "content": prompt}, *messages],
        )
        choice = completion.choices[0]
        if not choice.message or not choice.message.content:
            raise RuntimeError("OpenAI returned an empty message.")
        return choice.message.content.strip()


_openai_singleton: OpenAIChatClient | None = None


def get_openai_client() -> OpenAIChatClient:
    global _openai_singleton
    if _openai_singleton is None:
        _openai_singleton = OpenAIChatClient()
    return _openai_singleton
