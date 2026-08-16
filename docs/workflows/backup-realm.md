# Back up a realm

**Automation status:** Full — one command, already deployed and used before
every deploy (see [deployment-workflow.md](../architecture/deployment-workflow.md)'s
step 5).

## When to use

Before any risky manual edit — [changing a port](change-port.md),
[updating a jar](update-jar-version.md), or just periodically as a safety
net. This is also the *actual* source of truth for realm config history,
since [those files aren't in git](README.md#why-realm-config-files-serverproperties-whitelistjson-opsjson-startsh--arent-in-git).

## Steps

On oscar (either user — `backup_service` only reads the realm's data
directory and writes to `backups_root`, no process control involved):

```bash
cd /srv/minecraft
python -m minecraftmgr backup run <server_id>
# or, for everything:
python -m minecraftmgr backup run --all
```

## Verify

```bash
ls -la <backups_root>/<server_id>-*.tar.gz*
sha256sum -c <server_id>-<timestamp>.tar.gz.sha256
```

Each archive is a full tar of the realm's data directory — jar, `start.sh`,
`server.properties`, every control file, `world/` — with a `.sha256`
checksum file alongside it, written by `backup_service.backup_server()`.

## Notes

Backing up doesn't require stopping the realm first — `tarfile.add()` reads
whatever's on disk at the moment it runs, so a backup taken mid-session can
catch a `world/` directory being actively written to. For a guaranteed
consistent snapshot before something destructive, stop the realm first (see
[stop-restart-server.md](stop-restart-server.md)), then back up, then make
the change.
