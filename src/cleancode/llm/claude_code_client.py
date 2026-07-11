"""Claude Code CLI implementation of the LLMClient protocol."""

from __future__ import annotations

import shutil
import subprocess


class ClaudeCodeError(RuntimeError):
    """The ``claude`` CLI was missing, timed out, or exited non-zero."""


class ClaudeCodeClient:
    """LLM client that shells out to the Claude Code CLI (``claude --print``).

    Unlike :class:`AnthropicClient` this needs no ``ANTHROPIC_API_KEY`` — it
    reuses whatever login the ``claude`` CLI already holds, so a Claude Pro or
    Max subscription drives the feedback loop instead of pay-as-you-go credits.
    """

    def __init__(
        self,
        model: str | None = None,
        binary: str = "claude",
        timeout: float = 180.0,
    ) -> None:
        if shutil.which(binary) is None:
            raise ClaudeCodeError(
                f"the {binary!r} CLI was not found on PATH; install Claude Code "
                "from https://claude.com/claude-code to use this client"
            )
        self.model = model
        self.binary = binary
        self.timeout = timeout

    def complete(self, *, system: str, messages: list[dict[str, str]]) -> str:
        command = [self.binary, "--print", "--append-system-prompt", system]
        if self.model is not None:
            command += ["--model", self.model]
        try:
            completed = subprocess.run(
                command,
                input=_flatten(messages),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )
        except FileNotFoundError as error:
            raise ClaudeCodeError(f"could not launch the {self.binary!r} CLI") from error
        except subprocess.TimeoutExpired as error:
            raise ClaudeCodeError(
                f"the {self.binary!r} CLI timed out after {self.timeout}s"
            ) from error
        except subprocess.CalledProcessError as error:
            raise ClaudeCodeError(
                f"the {self.binary!r} CLI exited with status {error.returncode}: "
                f"{(error.stderr or '').strip()}"
            ) from error
        return completed.stdout.strip()


def _flatten(messages: list[dict[str, str]]) -> str:
    """Render the chat history as one prompt for the single-shot CLI.

    ``claude --print`` takes a single prompt rather than a message array, so the
    refinement turns are labelled and replayed inline; the final user turn (the
    latest violation feedback) therefore lands last, where it carries the most
    weight.
    """
    if len(messages) == 1:
        return messages[0]["content"]
    blocks = []
    for message in messages:
        speaker = "Assistant" if message["role"] == "assistant" else "User"
        blocks.append(f"{speaker}:\n{message['content']}")
    return "\n\n".join(blocks)
