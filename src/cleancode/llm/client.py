"""Provider-agnostic LLM client protocol."""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    """Anything that can turn a system prompt + message history into a reply.

    ``messages`` follows the familiar chat shape:
    ``[{"role": "user" | "assistant", "content": str}, ...]``.
    """

    def complete(self, *, system: str, messages: list[dict[str, str]]) -> str: ...
