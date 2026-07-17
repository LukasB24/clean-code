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
    "PY903": Example(
        bad=(
            "def run(row):\n"
            "    try:\n"
            "        a = parse(row)\n"
            "        b = validate(a)\n"
            "        c = normalize(b)\n"
            "        d = save(c)\n"
            "    except Exception:\n"
            "        logger.error(\"failed\")\n"
        ),
        good=(
            "def run(row):\n"
            "    try:\n"
            "        a = parse(row)\n"
            "        b = validate(a)\n"
            "        c = normalize(b)\n"
            "        d = save(c)\n"
            "    except ValueError:\n"
            "        logger.error(\"failed\")\n"
        ),
        note="A short try (at or under `max_statements`) wrapping a broad except is not flagged.",
    ),
}
