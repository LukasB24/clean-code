# Security Policy

## Scope

clean-code is a static analyzer: it parses Python source with `ast`/
`tokenize` and never executes, imports, or evaluates the code it checks. The
main security-relevant surface is therefore narrow — things like a crafted
input file causing a crash/hang, a config-parsing issue, or (if ever added)
any code path that would execute analyzed code.

## Reporting a Vulnerability

Please report security issues privately, not in a public issue:

1. Use GitHub's [private vulnerability reporting](https://github.com/LukasB24/clean-code/security/advisories/new)
   for this repository ("Security" tab → "Report a vulnerability").
2. Include a minimal reproduction (input file + command) and the impact you
   expect it to have.

You should get an initial response within a few days. If the report is
confirmed, we'll work out a fix and disclosure timeline with you before any
public advisory is published.

## Supported Versions

This project is pre-1.0 (`0.x`). Only the latest release on
[PyPI](https://pypi.org/project/clean-code/) and the latest commit on
`main` are supported — please reproduce against one of those before
reporting.
