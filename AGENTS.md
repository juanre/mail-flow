# Repository Guidelines

This guide explains how to work effectively in this repository.

## Project Structure & Module Organization
- Source code lives in `src/mailflow/` (CLI in `cli.py`, pipeline in `process.py`).
- Tests are under `tests/` (pytest discovery: `test_*.py`, `Test*`, `test_*`).
- Workspace member: `archive-protocol/` (shared library + its own tests).
- Docs and reference material in `docs/` and top-level `*.md` files.
- Executable entry point: `mailflow` → `mailflow.cli:cli`.

## Build, Test, and Development Commands
- Install deps: `uv sync`
- Run CLI: `uv run mailflow [subcommand]` (e.g., `uv run mailflow search "invoice"`).
- Tests: `uv run pytest -q`
- Lint: `uv run ruff check .`
- Format: `uv run black . && uv run isort .`
- Types: `uv run mypy src`
- Playwright (PDF support): `playwright install chromium`

## Coding Style & Naming Conventions
- Python 3.11+. Use type hints for new/modified code.
- Formatting: Black (line length 99) and Isort (profile=black).
- Linting: Ruff (pycodestyle, pyflakes, pyupgrade, bugbear, simplify, comprehensions). Keep fixes small and focused.
- Naming: modules `snake_case.py`, classes `PascalCase`, functions/vars `snake_case`, constants `UPPER_SNAKE_CASE`.

## Testing Guidelines
- Framework: Pytest (+ pytest-asyncio). Async tests auto-managed (`asyncio_mode = auto`).
- Discovery: files `tests/test_*.py`, classes `Test*`, functions `test_*`.
- Write tests for new features, edge cases, and bug fixes; prefer small, focused tests.
- Run: `uv run pytest -q` or target a node, e.g. `uv run pytest tests/test_integration.py::TestMailflow -q`.

## Commit & Pull Request Guidelines
- Commit style mirrors history: `Feat:`, `Fix:`, `Docs:`, `Security:`, `Cleanup:`, etc. Use imperative mood and concise scope.
- One logical change per commit. Include rationale when the change isn’t obvious.
- PRs should include: clear summary, motivation, linked issues, testing notes, and any screenshots/logs when UI/CLI output changes.
- Ensure `ruff`, `black`, `isort`, `mypy`, and tests pass before requesting review.

## Security & Configuration Tips
- Never commit secrets. Configure APIs via env vars (e.g., `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).
- User config/data follows XDG paths (see `README.md`), e.g., `~/.config/mailflow/config.json`.
- When working with Gmail/Playwright, validate inputs and paths; prefer dry-runs for batch ops during development.

