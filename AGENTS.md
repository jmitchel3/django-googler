# Project Guidelines for django-googler

## Automatic Versioning, Changelog, and Push Workflow

Whenever you complete a change or update to this repository, ALWAYS perform the following release steps before finishing (unless the user explicitly asks not to commit/push):

1. **Verify quality first**:
   - Run `ruff check src tests` and `ruff format --check src tests`.
   - Run Django migration and system checks (`makemigrations django_googler --check --dry-run` and `check`).
   - Run the full test suite with coverage (`--fail-under=90`).

2. **Bump the Semantic Version** in `pyproject.toml` (and keep `uv.lock`'s `django-googler` package `version` in sync):
   - **Patch** (`X.Y.Z+1`): Bug fixes, security patches, documentation updates, tests, or internal refactors.
   - **Minor** (`X.Y+1.0`): Backwards-compatible new features, settings, signals, or API enhancements.
   - **Major** (`X+1.0.0`): Breaking changes.

3. **Update `CHANGELOG.md`**:
   - Add a new dated section at the top (`## [X.Y.Z] - YYYY-MM-DD`) following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) (`Security`, `Added`, `Changed`, `Fixed`, `Removed`) accurately summarizing the actual changes made.
   - Add the corresponding GitHub compare link at the bottom of `CHANGELOG.md` (e.g. `[X.Y.Z]: https://github.com/jmitchel3/django-googler/compare/vPREV...vX.Y.Z`).

4. **Commit, Tag, and Push to GitHub**:
   - Stage the changes and commit with a clear, descriptive message referencing the release version.
   - Create an annotated git tag `vX.Y.Z` (e.g. `git tag -a vX.Y.Z -m "Release vX.Y.Z"`).
   - Push `main` and the new tag to `origin` (`git push origin main && git push origin vX.Y.Z`). Note that pushing a `v*` tag triggers the GitHub Actions CI + PyPI release workflow.
