#!/bin/bash
# Imported verbatim from oscar:/opt/scripts/minecraft_all_in_one_backup_v1.sh
# on 2026-08-18 — CORRECTED 2026-08-18 during the redeploy runbook's diff
# check: this is the actually-cron'd, fixed copy (BASE_DIR=/opt/mc, weekly
# Sun 3am as `minecraft`, confirmed live via its own log output scanning
# /opt/mc/*). The copy at /opt/mc/Scripts/minecraft_all_in_one_backup_v1.sh
# is the stale, unused duplicate (still BASE_DIR=/srv/minecraft) — an
# earlier version of this comment had the two backwards. Superseded in
# spirit by `minecraftmgr backup run --all` but still cron'd — see
# tools/scripts/README.md before retiring it.
#
# 2026-10-05: first real change since the import — skip unchanged worlds,
# include the Nether/End folders, only treat folders with server.properties
# as servers, skip _-prefixed folders (e.g. _archive), check zip's exit code.

###############################################################################
# Script: minecraft_all_in_one_backup.sh
# Version: v1.1
#
# Purpose:
# Run a backup cycle for every Minecraft server under $BASE_DIR:
#   1. Find servers: every folder with a server.properties, except names
#      starting with "_" (_archive, _proxy, _jarcache, ...).
#   2. Decide which need a backup: running servers always; stopped servers
#      only if a world or config file changed since their newest zip.
#      Unchanged servers are not stopped, zipped or rotated.
#   3. Gracefully stop the running servers and wait for a clean shutdown.
#   4. Zip config files + world, world_nether, world_the_end into
#      $BACKUP_DIR/<server>_<timestamp>.zip.
#   5. Keep the newest $MAX_BACKUPS zips per server (each one is a different
#      world state, since unchanged worlds don't get a new zip).
#   6. Restart the servers that were running.
#   7. Log everything to $BACKUP_DIR/logs.
#
# Retired worlds: minecraft_archive_world.sh moves a server to
# $BASE_DIR/_archive/ with a final zip in $BACKUP_DIR/archive/, so this
# script stops seeing it.
#
# Usage (as `minecraft`, from cron Sun 03:00):
#   /srv/mc/tools/scripts/minecraft_all_in_one_backup_v1.sh
# MC_BASE_DIR / MC_BACKUP_DIR override the paths (for testing).
###############################################################################

SCRIPT_NAME=$(basename "$0")
SCRIPT_VERSION="v1.1"
TIMESTAMP=$(date +%Y%m%dT%H%M%S)

BASE_DIR="${MC_BASE_DIR:-/opt/mc}"
BACKUP_DIR="${MC_BACKUP_DIR:-/mnt/backup/minecraft}"
LOG_DIR="${BACKUP_DIR}/logs"
LOG_FILE="${LOG_DIR}/minecraft_all_in_one_${TIMESTAMP}.log"
MAX_BACKUPS=3
CONFIG_FILES=(server.properties eula.txt ops.json whitelist.json banned-ips.json banned-players.json usercache.json log4j2.xml start.sh)
# <server>_YYYYMMDDTHHMMSS.zip — exact, so arbor_1_21_1 never matches arbor_1_21_10's zips.
ZIP_STAMP="[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]"

mkdir -p "$BACKUP_DIR"
mkdir -p "$LOG_DIR"

log() { echo "$*" | tee -a "$LOG_FILE"; }

# Print the files/folders to back up for the server in the current directory.
backup_targets() {
  local f level
  for f in "${CONFIG_FILES[@]}"; do
    [ -f "$f" ] && echo "$f"
  done
  level=$(sed -n 's/^level-name=//p' server.properties 2>/dev/null | tr -d '\r')
  level="${level:-world}"
  for f in "$level" "${level}_nether" "${level}_the_end"; do
    [ -d "$f" ] && echo "$f"
  done
}

# Print the newest rotating zip for a server, if any.
newest_zip() {
  ls -t "${BACKUP_DIR}/${1}_"${ZIP_STAMP}.zip 2>/dev/null | head -n 1
}

is_running() {
  screen -ls 2>/dev/null | grep -qE "[0-9]+\.${1}[[:space:]]"
}

log "🛠 Running $SCRIPT_NAME ($SCRIPT_VERSION)"
log "Timestamp: $TIMESTAMP"
log ""

# 1. Find servers
SERVERS=()
for SERVER_DIR in "$BASE_DIR"/*/ ; do
  name=$(basename "$SERVER_DIR")
  [[ "$name" == _* ]] && continue
  [ -f "$SERVER_DIR/server.properties" ] || continue
  SERVERS+=("$name")
done

# 2. Decide which servers need a backup
RUNNING_SERVERS=()
TO_BACKUP=()
SKIPPED=()
log "🔍 Checking ${#SERVERS[@]} servers for changes..."
for name in "${SERVERS[@]}"; do
  if is_running "$name"; then
    RUNNING_SERVERS+=("$name")
    TO_BACKUP+=("$name")
    log "▶️  $name: running, will back up"
    continue
  fi
  last=$(newest_zip "$name")
  if [ -z "$last" ]; then
    TO_BACKUP+=("$name")
    log "🆕 $name: no zip yet, will back up"
    continue
  fi
  mapfile -t targets < <(cd "$BASE_DIR/$name" && backup_targets)
  changed=$(cd "$BASE_DIR/$name" && find "${targets[@]}" -newer "$last" -print -quit 2>/dev/null)
  if [ -n "$changed" ]; then
    TO_BACKUP+=("$name")
    log "✏️  $name: changed since $(basename "$last") ($changed), will back up"
  else
    SKIPPED+=("$name")
    log "⏭  $name: unchanged since $(basename "$last"), skipping"
  fi
done
log ""

# 3. Stop running servers and wait for clean shutdown (max 30 seconds each)
for name in "${RUNNING_SERVERS[@]}"; do
  log "🛑 Stopping $name..."
  screen -S "$name" -X stuff "say Server is stopping for weekly backup...\nstop\n"
done
for name in "${RUNNING_SERVERS[@]}"; do
  tries=0
  while is_running "$name"; do
    if (( tries >= 6 )); then
      log "⚠️  $name did not shut down — forcing screen quit"
      screen -S "$name" -X quit
      break
    fi
    log "⌛ Waiting for $name to exit... (${tries} x 5s)"
    sleep 5
    ((tries++))
  done
done

# 4. Zip each server that needs it, then rotate
FAILED=()
for name in "${TO_BACKUP[@]}"; do
  cd "$BASE_DIR/$name" || { FAILED+=("$name"); continue; }
  ZIP_FILE="${BACKUP_DIR}/${name}_${TIMESTAMP}.zip"
  mapfile -t targets < <(backup_targets)

  log "📦 Backing up: $name (${targets[*]})"
  if ! zip -r -q "$ZIP_FILE" "${targets[@]}" >>"$LOG_FILE" 2>&1; then
    log "❌ zip failed for $name — removing partial zip, keeping older zips"
    rm -f "$ZIP_FILE"
    FAILED+=("$name")
    log ""
    continue
  fi
  log "✅ $(basename "$ZIP_FILE") ($(du -h "$ZIP_FILE" | cut -f1))"

  # Retention: keep only latest $MAX_BACKUPS
  BACKUPS=( $(ls -t "${BACKUP_DIR}/${name}_"${ZIP_STAMP}.zip 2>/dev/null) )
  if [ "${#BACKUPS[@]}" -gt "$MAX_BACKUPS" ]; then
    for file in "${BACKUPS[@]:$MAX_BACKUPS}"; do
      log "🗑 Removing old backup: $file"
      rm -f "$file"
    done
  fi
  log ""
done

# 5. Restart servers that were previously running
log "🚀 Restarting previously running servers..."
for name in "${RUNNING_SERVERS[@]}"; do
  cd "$BASE_DIR/$name" || continue
  log "🔄 Restarting $name"
  screen -dmS "$name" ./start.sh
done

log ""
log "Summary: backed up $(( ${#TO_BACKUP[@]} - ${#FAILED[@]} )), skipped ${#SKIPPED[@]} unchanged, failed ${#FAILED[@]}${FAILED:+ (${FAILED[*]})}"
log "✅ All done at $(date)"
[ "${#FAILED[@]}" -eq 0 ]
