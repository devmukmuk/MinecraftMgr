# Epic DOC — Documentation & Examples

Scope: `docs/`, `README.md`.

## Purpose

Everything that explains the system rather than implements it: the
architecture/runbook docs, the design/schema docs, this epic-design set,
and the dev-workflow docs that govern how changes get made in the first
place.

## Current design

`docs/` is split by what kind of question the reader has, not by epic:

- **`docs/PAPER.md`** — Paper vs. vanilla explainer plus the three
  jar-lifecycle workflows (where to get one, deploy, upgrade). Sits at the
  top level rather than under `architecture/`, `design/`, or `workflows/`
  since it's background knowledge those all lean on, not a fit for any one
  of them.
- **`docs/architecture/`** — how the deployed system is put together and
  operated: [oscar-realm-hosting.md](../architecture/oscar-realm-hosting.md)
  (proxy/DNS/systemd/firewall runbook, owned in spirit by [DEP](DEP.md))
  and [deployment-workflow.md](../architecture/deployment-workflow.md)
  (the edit → push → ssh → backup → pull → restart flow and the two-tree
  split rationale).
- **`docs/design/`** — data shape references, e.g.
  [servers-json-schema.md](../design/servers-json-schema.md) for the
  [REG](REG.md) registry format. Intended for anyone hand-editing
  `servers.json` or writing code against `ServerEntry`.
- **`docs/workflows/`** — runbooks for changing an *already-active* realm
  (rename, port change, backup/restore, jar update, whitelist/ops, delete),
  as opposed to creating one ([PROV](PROV-design.md)). Each doc states
  whether the workflow is automated yet, so it also doubles as the backlog
  for [PROV](PROV-design.md)'s "Future work" section — see
  [workflows/README.md](../workflows/README.md).
- **`docs/epics/`** (this folder) — one design doc per epic code in
  `config/git/epics.txt`, plus [README.md](README.md) which is the
  authoritative epic-code table and the commit/branch-naming convention
  enforced by `tools/git-hooks/`. Each epic doc covers current design and
  explicitly lists open work, so it doubles as a "what's left" reference
  instead of going stale the moment the code moves — reviewed here rather
  than only living in issue history.
- **`tools/dev-docs/`** — not architecture of the *product*, but of the
  *workflow*: `CHANGEIT.md`/`FINISHIT.md`/`POSTMERGE.md` define the
  assistant-driven issue → branch → commit → PR → merge → cleanup cycle,
  and `GITHUB.md` is the same cycle written out as copy/paste commands for
  a human running it by hand. Ported from a sibling project (CodeIt) and
  adapted to MinecraftMgr's own epic codes.
- **Root `README.md`** stays intentionally short — feature bullets, dev
  setup, run/test commands, and a doc-links section — deep detail lives in
  `docs/`, not the README.

## Open work

- `README.md`'s Features list (server restart, "Oscar deployment
  scripts") is ahead of the code — restart and `tools/scripts/` don't
  exist yet (tracked under [DEP](DEP.md)'s open work); the README should
  either get corrected or the features should get built.
- No top-level `docs/README.md` index — a reader has to already know
  `architecture/` vs `design/` vs `epics/` exist; there's no single page
  linking all three.
