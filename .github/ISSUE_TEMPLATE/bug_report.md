---
name: Bug report
about: A rule misfires, crashes, or the CLI does something wrong
title: ""
labels: bug
---

**What happened**

A clear description of the incorrect behavior.

**Minimal reproduction**

The smallest Python snippet that reproduces it, plus the command you ran:

```python
# paste the snippet here
```

```bash
clean-code check ...
```

**Expected vs. actual**

- Expected: ...
- Actual (paste the real `clean-code` output): ...

**Environment**

- clean-code version (`clean-code --version`):
- Python version:
- OS:

**Config**

Paste any relevant `[tool.cleancode]` section from your `pyproject.toml`, if
you have one — some bugs only show up with non-default options.
