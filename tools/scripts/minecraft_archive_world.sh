#!/bin/bash
###############################################################################
# Script: minecraft_archive_world.sh
#
# Retire a server that isn't played any more, so the weekly backup stops
# zipping it:
#   1. Refuses if the server is running.
#   2. Zips the whole server folder (minus cache/, libraries/, versions/,
#      which Paper re-downloads) to
#      $BACKUP_DIR/archive/<server>/<server>_<timestamp>_final.zip
#   3. Tests the zip and checks its file count against the folder.
#   4. Moves the server's rotating weekly zips into that archive folder too.
#   5. Moves the server folder to $BASE_DIR/_archive/<server>
#      (the weekly backup skips _-prefixed folders). Nothing is deleted.
#
# Bring it back: move the folder back from _archive/ (or unzip the final zip
# into $BASE_DIR/<server>/), then start it as usual.
#
# Usage (as `minecraft`, so running servers are visible to screen):
#   sudo -u minecraft /srv/mc/tools/scripts/minecraft_archive_world.sh <server_folder> [--dry-run]
# e.g. cave_1_20_4. MC_BASE_DIR / MC_BACKUP_DIR override the paths (for testing).
###############################################################################

set -uo pipefail

BASE_DIR="${MC_BASE_DIR:-/opt/mc}"
BACKUP_DIR="${MC_BACKUP_DIR:-/mnt/backup/minecraft}"
ZIP_STAMP="[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]"
EXCLUDES=("cache/*" "libraries/*" "versions/*")

name="${1:-}"
dry_run=0
[ "${2:-}" = "--dry-run" ] && dry_run=1
if [ -z "$name" ] || [[ "$name" == */* ]]; then
  echo "Usage: $(basename "$0") <server_folder> [--dry-run]" >&2
  exit 2
fi

SERVER_DIR="$BASE_DIR/$name"
ARCHIVE_DIR="$BACKUP_DIR/archive/$name"
PARKED_DIR="$BASE_DIR/_archive/$name"
TIMESTAMP=$(date +%Y%m%dT%H%M%S)
ZIP_FILE="$ARCHIVE_DIR/${name}_${TIMESTAMP}_final.zip"
LOG_FILE="$BACKUP_DIR/logs/archive_${name}_${TIMESTAMP}.log"

die() { echo "ERROR: $*" >&2; exit 1; }

[ -f "$SERVER_DIR/server.properties" ] || die "$SERVER_DIR is not a server folder (no server.properties)"
[ -e "$PARKED_DIR" ] && die "$PARKED_DIR already exists"
if screen -ls 2>/dev/null | grep -qE "[0-9]+\.${name}[[:space:]]"; then
  die "$name is running; stop it first"
fi
[ "$(id -un)" = "minecraft" ] || echo "WARNING: not running as minecraft; can't see its screen sessions to check $name is stopped" >&2

files=$(cd "$SERVER_DIR" && find . -type f -not -path "./cache/*" -not -path "./libraries/*" -not -path "./versions/*" | wc -l)
size=$(du -sh --exclude=cache --exclude=libraries --exclude=versions "$SERVER_DIR" | cut -f1)
weekly=( $(ls "$BACKUP_DIR/${name}_"${ZIP_STAMP}.zip 2>/dev/null) )
newest=$(cd "$SERVER_DIR" && find . -type f -not -path "./cache/*" -printf "%TY-%Tm-%Td\n" | sort | tail -n 1)

echo "Archive $name: $files files, $size, last changed $newest"
echo "  final zip:    $ZIP_FILE"
echo "  weekly zips:  ${#weekly[@]} moved to $ARCHIVE_DIR/"
echo "  server folder moved to $PARKED_DIR"
[ "$dry_run" -eq 1 ] && { echo "(dry run, nothing changed)"; exit 0; }

mkdir -p "$ARCHIVE_DIR" "$BACKUP_DIR/logs" "$BASE_DIR/_archive"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "== zip"
(cd "$SERVER_DIR" && zip -r -q "$ZIP_FILE" . -x "${EXCLUDES[@]}") || { rm -f "$ZIP_FILE"; die "zip failed"; }

echo "== verify"
unzip -tq "$ZIP_FILE" || { rm -f "$ZIP_FILE"; die "zip test failed"; }
in_zip=$(unzip -Z1 "$ZIP_FILE" | grep -vc '/$')
[ "$in_zip" -eq "$files" ] || { rm -f "$ZIP_FILE"; die "zip has $in_zip files, folder has $files"; }
echo "OK: $in_zip files, $(du -h "$ZIP_FILE" | cut -f1)"

echo "== move"
for z in "${weekly[@]}"; do
  mv -v "$z" "$ARCHIVE_DIR/"
done
mv -v "$SERVER_DIR" "$PARKED_DIR"

echo "== done: $name archived."
echo "If it's a realm in servers.json, on the dev box run (then PR, merge, git pull on oscar):"
echo "  minecraftmgr server update <server_id> --status archived && minecraftmgr web build"
