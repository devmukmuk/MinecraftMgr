# Epic CLI — Project Setup & CLI Framework

Scope: `constants.py`, `config/`, `cli.py`, `__main__.py`.

## Purpose

Everything needed to invoke MinecraftMgr as a command — the typer app
skeleton, config discovery, and the entry point — but none of the
domain logic itself (that's [REG](REG.md) and [BAK](BAK.md)).

## Current design

- **Entry point**: `python -m minecraftmgr` → `__main__.py` → `cli.app`
  (a `typer.Typer`). Subcommand apps (`server`, `backup`) are mounted with
  `app.add_typer(...)` in `cli.py`, so each epic's commands live in their
  own module under `commands/` instead of growing `cli.py`.
- **No-subcommand behavior**: `invoke_without_command=True` means running
  `minecraftmgr` with no args runs `about()` rather than printing typer's
  default help — `about` is the fastest way to sanity-check config
  resolution, so it doubles as the default view.
- **Config discovery** (`config/settings.py`): resolved in order —
  1. `MINECRAFTMGR_CONFIG_FILE` env var, exact path, error if missing
  2. `MINECRAFTMGR_CONFIG_DIR` env var, looks for `minecraftmgr.yaml`/`.yml`
  3. the runtime dir (repo root in dev, exe folder when frozen)
  4. a per-user fallback (`%LOCALAPPDATA%\MinecraftMgr` on Windows,
     `~/.minecraftmgr` elsewhere), auto-created with defaults if nothing
     else matched
  This mirrors MineOps's discovery order deliberately, so the two tools
  behave the same way operationally even though they're separate codebases.
- **What `minecraftmgr.yaml` holds vs. `servers.json`**: `minecraftmgr.yaml`
  is machine-local (`data_root`, `backups_root`) and is never committed —
  `data_root` differs between the Windows dev box and oscar. `servers.json`
  is the tracked registry and is always resolved relative to the repo root
  (`resolve_servers_json_path()`), independent of which config file loaded.
  See [servers-json-schema.md](../design/servers-json-schema.md).

## Open work

- No `--version` flag or `constants.VERSION` surfaced anywhere in the CLI
  output yet — `about()` doesn't print it.
- No shell completion wiring (typer supports it via `--install-completion`
  but it isn't documented for this project).
