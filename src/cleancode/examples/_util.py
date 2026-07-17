"""Snippet-generation helpers shared by the per-band example modules.

A handful of rules (module/class/function length, file comment density)
only trigger past a real line-count threshold — these build that filler
programmatically so the *source* of an example module stays short even
though the *rendered* snippet is long.
"""

from __future__ import annotations


def numbered_statements(count: int, indent: str = "    ", comment_every: int = 0) -> str:
    lines: list[str] = []
    for i in range(count):
        if comment_every and i % comment_every == 0:
            lines.append(f"{indent}# step {i}")
        lines.append(f"{indent}value_{i} = {i}")
    return "\n".join(lines)


def numbered_methods(count: int) -> str:
    return "\n".join(
        f"    def method_{i}(self):\n        return {i}\n" for i in range(count)
    )
