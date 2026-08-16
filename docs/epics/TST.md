# Epic TST — Testing & Validation

Scope: `tests/`.

## Purpose

Unit coverage for the model/service layer that the [REG](REG.md) and
[BAK](BAK.md) CLI commands sit on top of, plus the config-resolution logic
in [CLI](CLI.md).

## Current design

- **Layout mirrors `src/`**: `tests/models/`, `tests/services/`,
  `tests/utils/` — one test module per source module
  (`test_server_entry.py`, `test_registry_service.py`,
  `test_backup_service.py`, `test_hashing.py`), so a change under
  `src/minecraftmgr/services/backup_service.py` has an obvious
  corresponding test file rather than a shared catch-all test file.
- **Isolation via `tmp_path`**: the shared `settings` fixture
  (`tests/conftest.py`) builds a real `Settings` object pointed entirely at
  a pytest `tmp_path` sandbox (`data_root`, `backups_root`,
  `servers_json_path` all under the temp dir). Tests exercise the real
  registry/backup services against real files on disk rather than mocking
  the filesystem — deliberate, since both services are thin wrappers
  around file I/O (JSON read/write, tar, sha256) and mocking that away
  would mostly test the mocks.
- **Config discovery is not fixture-covered**: `find_config_file()`'s
  env-var / runtime-dir / user-fallback precedence chain
  (`config/settings.py`) has no dedicated test module yet — it was
  verified manually during scaffolding (`MINECRAFTMGR_CONFIG_FILE`,
  `MINECRAFTMGR_CONFIG_DIR` env vars) rather than under `tests/`.
- **Discovery config**: `pytest.ini` sets `testpaths = tests` and
  `pythonpath = src`, so `pytest` run from the repo root picks up the
  package without an editable install — CI and local runs don't need
  `pip install -e .` just to run the suite (though the dev workflow docs
  in [DOC](DOC.md) also set one up for running the CLI directly).

## Open work

- No test coverage for `cli.py`/`commands/` (typer's `CliRunner` isn't
  used anywhere yet) — current tests stop at the service layer, so a
  regression in argument parsing or option wiring wouldn't be caught by
  `pytest`.
- No test for `config/settings.py`'s `find_config_file()` precedence chain
  or `write_default_config()`.
- No CI workflow (`.github/workflows/`) running `pytest` on push/PR yet —
  `gh pr checks` in [GITHUB.md](../../tools/dev-docs/GITHUB.md) has
  nothing to report on until one exists.
