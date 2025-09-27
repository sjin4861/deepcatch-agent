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
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "1.0"))
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

    def chat_completion(
        self,
        *,
        system_prompt: str,
        messages: Iterable[Mapping[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        response_format: Optional[Mapping[str, Any]] = None,
    ) -> str:
        if not self._client:
            raise RuntimeError("OpenAI client is not configured.")

        selected_model = model or self.model
        payload_messages = [{"role": "system", "content": system_prompt}, *messages]

        # Use the Responses API when model includes "gpt-5"
        if "gpt-5" in selected_model.lower():
            return self._call_responses_api(
                model=selected_model,
                payload_messages=payload_messages,
                response_format=response_format,
            )

        params: dict[str, Any] = {
            "model": selected_model,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": payload_messages,
        }
        if response_format is not None:
            params["response_format"] = response_format

        completion = self._client.chat.completions.create(**params)
        choice = completion.choices[0]
        if not choice.message or not choice.message.content:
            raise RuntimeError("OpenAI returned an empty message.")
        return choice.message.content.strip()

    def _call_responses_api(
        self,
        *,
        model: str,
        payload_messages: list[Mapping[str, str]],
        response_format: Optional[Mapping[str, Any]],
    ) -> str:
        inputs = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in payload_messages
        ]
        params: dict[str, Any] = {
            "model": model,
            "input": inputs,
            "reasoning": {"effort": "minimal"},
        }
        if response_format is not None:
            logger.debug(
                "Responses API response_format not supported; ignoring structured output request."
            )

        response = self._client.responses.create(**params)
        text = getattr(response, "output_text", None)
        if text:
            return str(text).strip()

        outputs = getattr(response, "output", None)
        if isinstance(outputs, list):
            parts: list[str] = []
            for item in outputs:
                content = getattr(item, "content", None)
                if isinstance(content, list):
                    for chunk in content:
                        value = getattr(chunk, "text", None)
                        if value and getattr(value, "value", None):
                            parts.append(str(value.value))
                elif getattr(item, "text", None):
                    parts.append(str(item.text))
            if parts:
                return "".join(parts).strip()

        raise RuntimeError("OpenAI responses API returned an empty message.")

    def generate(self, prompt: str, messages: Iterable[Mapping[str, str]]) -> str:
        return self.chat_completion(
            system_prompt=prompt,
            messages=messages,
        )


_openai_singleton: OpenAIChatClient | None = None


def get_openai_client() -> OpenAIChatClient:
    global _openai_singleton
    if _openai_singleton is None:
        _openai_singleton = OpenAIChatClient()
    return _openai_singleton
