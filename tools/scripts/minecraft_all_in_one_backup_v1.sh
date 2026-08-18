#!/bin/bash
# Imported verbatim from oscar:/opt/mc/Scripts/minecraft_all_in_one_backup_v1.sh
# on 2026-08-18 — this copy has BASE_DIR already fixed to /opt/mc (the
# now-stale /opt/scripts/ copy still says /srv/minecraft and was not
# imported). Nightly all-realms backup, superseded in spirit by
# `minecraftmgr backup run --all` but still cron'd — see
# tools/scripts/README.md before retiring it.

###############################################################################
# Script: minecraft_all_in_one_backup.sh
# Version: v1
#
# Purpose:
# Run a complete backup cycle for all Minecraft servers:
#   1. Detect running servers (by screen session)
#   2. Gracefully stop each running server
#   3. Wait for clean shutdown and confirm
#   4. Zip server folders (world + config) into /mnt/backup/minecraft
#   5. Retain only last 3 backups per server
#   6. Restart only those servers that were originally running
#   7. Log the entire process to /mnt/backup/minecraft/logs
#
# Usage:
#   Run manually as `minecraft` or via crontab:
#     0 3 * * * /opt/scripts/backup/minecraft_all_in_one_backup.sh
###############################################################################

SCRIPT_NAME=$(basename "$0")
SCRIPT_VERSION="v1"
TIMESTAMP=$(date +%Y%m%dT%H%M%S)

BASE_DIR="/opt/mc"
BACKUP_DIR="/mnt/backup/minecraft"
LOG_DIR="${BACKUP_DIR}/logs"
LOG_FILE="${LOG_DIR}/minecraft_all_in_one_${TIMESTAMP}.log"
MAX_BACKUPS=3

mkdir -p "$BACKUP_DIR"
mkdir -p "$LOG_DIR"

echo "🛠 Running $SCRIPT_NAME ($SCRIPT_VERSION)" | tee -a "$LOG_FILE"
echo "Timestamp: $TIMESTAMP" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

RUNNING_SERVERS=()

# 1. Detect running screen sessions
echo "🔍 Checking for running Minecraft servers..." | tee -a "$LOG_FILE"
for sid in $(screen -ls | awk '/Detached|Attached/ {print $1}'); do
  name="${sid#*.}"
  if [[ -d "$BASE_DIR/$name" && -f "$BASE_DIR/$name/start.sh" ]]; then
    RUNNING_SERVERS+=("$name")
    echo "🛑 Marking $name for shutdown..." | tee -a "$LOG_FILE"
    screen -S "$name" -X stuff "say Server is stopping for nightly backup...\nstop\n"
  fi
done

# 2. Wait for clean shutdown (max 30 seconds)
echo "⏳ Waiting for shutdown..." | tee -a "$LOG_FILE"
for name in "${RUNNING_SERVERS[@]}"; do
  tries=0
  while screen -ls | grep -q "\.${name}"; do
    if (( tries >= 6 )); then
      echo "⚠️  $name did not shut down — forcing screen quit" | tee -a "$LOG_FILE"
      screen -S "$name" -X quit
      break
    fi
    echo "⌛ Waiting for $name to exit... (${tries} x 5s)" | tee -a "$LOG_FILE"
    sleep 5
    ((tries++))
  done
done

# 3. Perform backup of each server
for SERVER_DIR in "$BASE_DIR"/*/ ; do
  BASENAME=$(basename "$SERVER_DIR")

  # Skip non-server folders
  if [[ "$BASENAME" == "lost+found" || "$BASENAME" == "backups" ]]; then
    continue
  fi

  [ -d "$SERVER_DIR" ] || continue
  cd "$SERVER_DIR" || continue

  ZIP_FILE="${BACKUP_DIR}/${BASENAME}_${TIMESTAMP}.zip"
  echo "📦 Backing up: $BASENAME" | tee -a "$LOG_FILE"

  FILES_TO_BACKUP=()
  for f in server.properties eula.txt ops.json whitelist.json banned-ips.json banned-players.json usercache.json log4j2.xml start.sh; do
    [ -f "$f" ] && FILES_TO_BACKUP+=("$f")
  done
  [ -d world ] && FILES_TO_BACKUP+=("world")

  if [ "${#FILES_TO_BACKUP[@]}" -eq 0 ]; then
    echo "⚠️  No backup targets found in $BASENAME" | tee -a "$LOG_FILE"
  else
    echo "🗜 Creating zip: $ZIP_FILE" | tee -a "$LOG_FILE"
    zip -r "$ZIP_FILE" "${FILES_TO_BACKUP[@]}" 2>&1 | tee -a "$LOG_FILE"
    echo "✅ Backup complete for $BASENAME" | tee -a "$LOG_FILE"
  fi

  # Retention: keep only latest $MAX_BACKUPS
  BACKUPS=( $(ls -t "${BACKUP_DIR}/${BASENAME}_"*.zip 2>/dev/null) )
  if [ "${#BACKUPS[@]}" -gt "$MAX_BACKUPS" ]; then
    TO_DELETE=("${BACKUPS[@]:$MAX_BACKUPS}")
    for file in "${TO_DELETE[@]}"; do
      echo "🗑 Removing old backup: $file" | tee -a "$LOG_FILE"
      rm -f "$file"
    done
  fi

  echo "" | tee -a "$LOG_FILE"
done

# 4. Restart servers that were previously running
echo "🚀 Restarting previously running servers..." | tee -a "$LOG_FILE"
for name in "${RUNNING_SERVERS[@]}"; do
  cd "$BASE_DIR/$name" || continue
  echo "🔄 Restarting $name" | tee -a "$LOG_FILE"
  screen -dmS "$name" ./start.sh
done

echo "✅ All done at $(date)" | tee -a "$LOG_FILE"
