"""Anthropic implementation of the LLMClient protocol."""

from __future__ import annotations


class AnthropicClient:
    """LLM client backed by the Anthropic Messages API.

    Requires the ``anthropic`` package (``pip install "cleancode[llm]"``) and an
    ``ANTHROPIC_API_KEY`` in the environment (or an explicit ``api_key``).
    """

    def __init__(
        self,
        model: str = "claude-sonnet-5",
        max_tokens: int = 16000,
        api_key: str | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as error:
            raise ImportError(
                "the LLM feedback loop needs the anthropic package; install it with "
                'pip install "cleancode[llm]"'
            ) from error
        self.model = model
        self.max_tokens = max_tokens
        kwargs = {} if api_key is None else {"api_key": api_key}
        self._client = anthropic.Anthropic(**kwargs)

    def complete(self, *, system: str, messages: list[dict[str, str]]) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
        )
        return "".join(block.text for block in response.content if block.type == "text")
