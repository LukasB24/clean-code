"""BAD/GOOD examples for the correctness rules (PY9xx)."""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "PY901": Example(
        bad="try:\n    connect()\nexcept:\n    pass\n",
        good='try:\n    connect()\nexcept ConnectionError:\n    log.warning("connection failed")\n',
        note="`except Exception:` is merely broad, not bare, and is not flagged.",
    ),
    "PY902": Example(
        bad="try:\n    connect()\nexcept ConnectionError:\n    pass\n",
        good='try:\n    connect()\nexcept ConnectionError:\n    log.warning("connection failed")\n',
        note="A handler that continues/returns/breaks, logs, or re-raises is not flagged.",
    ),
}
