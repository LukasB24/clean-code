# Releasing

clean-code is published to PyPI via
[trusted publishing](https://docs.pypi.org/trusted-publishers/) — the
`.github/workflows/release.yml` workflow builds and uploads on every
published GitHub Release, authenticating with a short-lived OIDC token
instead of a stored API token.

## One-time setup (already done for `LukasB24/clean-code`)

On [pypi.org](https://pypi.org), under the `clean-code` project's
"Publishing" settings, a trusted publisher is registered with:

- Owner: `LukasB24`
- Repository: `clean-code`
- Workflow: `release.yml`
- Environment: `pypi`

The `pypi` environment referenced by the workflow can optionally have a
[required reviewer](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment#deployment-protection-rules)
configured under repo Settings → Environments, so a publish needs manual
approval even after a release is published.

## Cutting a release

1. Bump the version in **both** places (they must match):
   - `pyproject.toml` → `[project] version`
   - `src/cleancode/__init__.py` → `__version__`
2. Move the `## [Unreleased]` section in `CHANGELOG.md` into a new
   `## [X.Y.Z] - YYYY-MM-DD` section; leave a fresh empty `[Unreleased]`
   above it.
3. Open a PR with just the version bump + changelog, get it merged to `main`.
4. On `main`, create a GitHub Release:
   - Tag: `vX.Y.Z` (target `main`)
   - Title: `X.Y.Z`
   - Notes: paste the new CHANGELOG section
   - **Publish** the release (not a draft) — this is what triggers
     `release.yml`.
5. Watch the `Release` workflow run: it re-runs the full test suite and
   `ruff`, builds the sdist/wheel, runs `twine check`, then publishes.
   Nothing is uploaded if tests or the build fail first.
6. Confirm the new version shows up at
   https://pypi.org/project/clean-code/.

## Version policy

Pre-1.0 (`0.x`), a minor bump (`0.x.0`) may include new rules, changed
rule defaults, or other behavior changes on existing code — read the
CHANGELOG entry before upgrading. A patch (`0.x.y`) stays limited to bug
fixes and docs.

`1.0.0` marks rule IDs, default severities, default options, and the
CLI/config surface as stable. From there, Semantic Versioning applies
as usual:

- **Patch** (`1.0.x`): bug fixes, false-positive/negative fixes on existing
  rules, docs.
- **Minor** (`1.x.0`): new rules, new CLI flags, new config options — all
  additive and backward-compatible.
- **Major** (`x.0.0`): removing/renaming a rule ID, changing a rule's
  default severity or default options in a way that changes behavior on
  existing code without a config change, or breaking CLI/config
  compatibility.
