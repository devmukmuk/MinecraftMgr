
# MinecraftMgr

Minecraft server lifecycle management and oscar deployment toolkit.

## Features

* Server registry (add / list / remove realms)
* World backups with sha256 verification
* Server jar/version updates
* Realm restart (oscar/systemd)
* Oscar deployment scripts

## Development

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

## Run

```bash
python -m minecraftmgr about
```

## Test

```bash
pytest
```

## Docs

* [docs/architecture/oscar-realm-hosting.md](docs/architecture/oscar-realm-hosting.md) — proxy/DNS/systemd/firewall runbook for hosting realms on oscar
* [docs/architecture/deployment-workflow.md](docs/architecture/deployment-workflow.md) — Windows-edit -> push -> ssh -> backup -> pull -> restart flow
* [docs/architecture/oscar-migration-plan.md](docs/architecture/oscar-migration-plan.md) — migrating oscar's real `/srv/minecraft` layout to the `/srv` (git) + `/opt/mc` (data) split
* [docs/PAPER.md](docs/PAPER.md) — Paper vs. vanilla, and where to get/deploy/upgrade a Paper server jar
* [docs/design/servers-json-schema.md](docs/design/servers-json-schema.md) — servers.json registry schema
* [docs/workflows/README.md](docs/workflows/README.md) — runbooks for changing an already-active realm (rename, port, backup/restore, jar update, whitelist/ops, delete)
* [docs/epics/README.md](docs/epics/README.md) — epic codes, commit/branch conventions, and links to each epic's design doc
