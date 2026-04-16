# Repository Guidelines

## Open Source Fork Rule

This repository is a secondary development fork of an upstream open source project. For AI/coding agents, the default rule is: **minimize changes to original upstream code**. Prefer adding new behavior in a **new package** (for example `trendradar/websocket/`) instead of editing existing upstream modules in place. Only touch upstream entrypoints such as `trendradar/__main__.py`, `trendradar/core/loader.py`, or shared config/loaders when wiring is unavoidable. This keeps future upstream merges cheap and low-risk.

## Project Structure & Module Organization

- `trendradar/`: main application code. Core upstream logic lives here.
- `trendradar/dedup/`: shared notification dedup logic and SQLite store.
- `trendradar/websocket/`: fork-specific realtime websocket runtime and channels.
- `mcp_server/`: MCP server entrypoints and tools.
- `tests/dedup/`, `tests/websocket/`: automated regression tests.
- `tools/`: manual smoke scripts and operator utilities, not `pytest` tests.
- `config/`: runtime configuration. `config/websocket.yaml` is websocket-only.
- `docker/`: Dockerfiles, Compose, and container entrypoints.

## Build, Test, and Development Commands

- `python -m trendradar`: run the main scheduled crawler flow locally.
- `python -m trendradar.websocket.service`: run the websocket service only.
- `python tools/jin10_websocket_smoke.py`: manual Jin10 websocket smoke test.
- `pytest tests/websocket tests/dedup/test_store.py tests/dedup/test_realtime_service.py -q`: run websocket and dedup regressions.
- `python -m compileall trendradar/websocket trendradar/dedup tests/websocket tools/jin10_websocket_smoke.py`: quick syntax validation.
- `docker compose -f docker/docker-compose.yml config`: validate Docker Compose before deploy.

## Coding Style & Naming Conventions

Use Python 3.12, 4-space indentation, and `snake_case` for functions, modules, and test files. Keep new packages lowercase. Prefer small, explicit modules over editing large upstream files. Manual scripts belong in `tools/`; automated tests belong in `tests/` and must be named `test_*.py`.

## Testing Guidelines

Use `pytest`. When changing `dedup` or `websocket`, add or update focused tests in `tests/dedup/` or `tests/websocket/`. Cover real regressions first: startup, reconnect, parsing, dedup, SQLite locking, and Feishu rendering. Do not rely on manual smoke scripts as the only verification.

## Commit & PR Guidelines

Recent history includes many generic `update` commits; avoid that for new work. Prefer clear prefixes such as `feat:`, `fix:`, `refactor:`, `docs:`, or `test:`. In PRs or handoff notes, state:

- whether upstream/original files were changed,
- which new package or module owns the feature,
- what tests were run,
- what deployment/config changes are required.
