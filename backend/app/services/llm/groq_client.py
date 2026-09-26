"""Groq-backed LLMClient."""

from __future__ import annotations

from typing import Any, cast

from fastapi import HTTPException
from groq import Groq
from groq.types.chat import ChatCompletionMessageParam

from backend.app.core.settings import get_settings
from backend.app.services.llm.protocol import LLMClient


class GroqClient:
    """Chat completions via the Groq API."""

    _client: Groq
    _model: str

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        key = (api_key if api_key is not None else settings.groq_api_key) or ""
        key = key.strip()
        if not key:
            raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured.")
        self._client = Groq(api_key=key)
        self._model = model or settings.groq_model

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
    ) -> str:
        typed_messages = cast(list[ChatCompletionMessageParam], messages)
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=typed_messages,
            temperature=temperature,
        )
        content: Any = completion.choices[0].message.content
        return str(content or "").strip()


def get_llm_client() -> LLMClient:
    return GroqClient()
