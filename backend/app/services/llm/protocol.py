"""LLM client protocol for AI report and SQL features."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
    ) -> str:
        """Return assistant text for a chat completion request."""
        ...
