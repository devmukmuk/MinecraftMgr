# MinecraftMgr Epics

The canonical **Epic** codes used for issue tracking on
[github.com/devmukmuk/MinecraftMgr](https://github.com/devmukmuk/MinecraftMgr)
(see `gh label list --search "Epic"` for the live source of truth). These
codes are also the registry read by `config/git/epics.txt` and enforced by
the `commit-msg` and `pre-push` git hooks in `tools/git-hooks/` — see that
folder's `install.sh`.

| Code | Epic | Design doc |
|------|------|------------|
| CLI | Project Setup & CLI Framework — `constants.py`, `config/`, `cli.py`, `__main__.py` | [CLI.md](CLI.md) |
| REG | Realm Registry — `servers.json`, `models/server_entry.py`, `services/registry_service.py`, `commands/server.py` | [REG.md](REG.md) |
| BAK | Backup & Restore — `models/backup_result.py`, `services/backup_service.py`, `commands/backup.py` | [BAK.md](BAK.md) |
| DEP | Oscar Deployment & Hosting — Velocity proxy, systemd, Cloudflare DNS, `docs/architecture/` | [DEP.md](DEP.md) |
| TST | Testing & Validation — `tests/` | [TST.md](TST.md) |
| DOC | Documentation & Examples — `docs/`, `README.md` | [DOC.md](DOC.md) |

## Conventions enforced by the git hooks

**Commit subject:**
```
<type>(<CODE>): <short description>
```
Example: `feat(REG): add server remove command`

**Branch name:**
```
<type>/<issue>-<CODE>-<short-description>
```
Example: `feat/12-REG-add-server-remove-command`

**Allowed types:** `feat fix docs test refactor perf build chore`

Adding a new epic: create its `Epic-NN-CODE-Name` label on GitHub, append the
code to `config/git/epics.txt`, and add a row to the table above.
