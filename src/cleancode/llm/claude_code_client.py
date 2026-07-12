"""Claude Code CLI implementation of the LLMClient protocol."""

from __future__ import annotations

import shutil
import subprocess


class ClaudeCodeError(RuntimeError):
    """The ``claude`` CLI was missing, timed out, or exited non-zero."""


# The `claude` CLI is an agentic coding tool: given "create a json parser" it
# will otherwise try to *build* it — reading the project, running Bash, writing
# files — which is slow and can hang on tool permissions. We only want one text
# completion, so every agentic tool is disabled and it answers directly.
_DISALLOWED_TOOLS = [
    "Bash", "Edit", "Write", "Read", "Glob", "Grep", "Task",
    "WebFetch", "WebSearch", "NotebookEdit", "TodoWrite",
]


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
        command = [
            self.binary,
            "--print",
            "--append-system-prompt",
            system,
            "--disallowedTools",
            *_DISALLOWED_TOOLS,
        ]
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
                _diagnose_failure(self.binary, error.returncode, error.stderr or "")
            ) from error
        return completed.stdout.strip()


def _diagnose_failure(binary: str, returncode: int, stderr: str) -> str:
    """Turn a raw CLI failure into a message the user can act on."""
    lowered = stderr.lower()
    if "usage limit" in lowered or "rate limit" in lowered or "rate_limit" in lowered:
        return (
            "Claude Code usage limit reached. Wait for it to reset, or run with "
            f"--via anthropic (needs ANTHROPIC_API_KEY) instead.\n({stderr.strip()})"
        )
    if "anthropic_api_key" in lowered and "precedence" in lowered:
        return (
            "The `claude` CLI ignored your claude.ai login because ANTHROPIC_API_KEY "
            "is set in the environment. Either run `unset ANTHROPIC_API_KEY` to use "
            "your Pro/Max subscription via --via claude-code, or pass --via anthropic "
            f"to bill that key directly.\n({stderr.strip()})"
        )
    return f"the {binary!r} CLI exited with status {returncode}: {stderr.strip()}"


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
