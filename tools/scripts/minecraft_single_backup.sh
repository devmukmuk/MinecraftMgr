#!/bin/bash
# Imported verbatim from oscar:/opt/scripts/minecraft_single_backup.sh on
# 2026-08-18. Note: BASE_DIR below still says /srv/minecraft, which is stale
# post-migration (real path is /opt/mc) — left as-is per "bring it over
# first, clean up later". See tools/scripts/README.md.

###############################################################################
# Script: minecraft_single_backup.sh
# Version: v1-mcuser
#
# Run as the "minecraft" user. No sudo required.
#
# Purpose:
#   Backup ONE server inside /srv/minecraft/<server_name>
#   - Detect if running (screen)
#   - Gracefully stop if running
#   - Create zip backup in /mnt/backup/minecraft
#   - Keep only last 3 backups
#   - Restart server only if it was running
#   - Log actions under /mnt/backup/minecraft/logs
###############################################################################

SERVER_NAME="$1"
TIMESTAMP=$(date +%Y%m%dT%H%M%S)

BASE_DIR="/srv/minecraft"
BACKUP_DIR="/mnt/backup/minecraft"
LOG_DIR="${BACKUP_DIR}/logs"
LOG_FILE="${LOG_DIR}/single_${SERVER_NAME}_${TIMESTAMP}.log"

MAX_BACKUPS=3

mkdir -p "$BACKUP_DIR" "$LOG_DIR"

echo "=== Single Server Backup (${SERVER_NAME}) ===" | tee -a "$LOG_FILE"
echo "Timestamp: $TIMESTAMP" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# --- Validate input ---
if [ -z "$SERVER_NAME" ]; then
    echo "ERROR: No server name supplied." | tee -a "$LOG_FILE"
    echo "Usage: minecraft_single_backup.sh <server_folder>" | tee -a "$LOG_FILE"
    exit 1
fi

SERVER_DIR="${BASE_DIR}/${SERVER_NAME}"

if [ ! -d "$SERVER_DIR" ]; then
    echo "ERROR: Server directory not found: $SERVER_DIR" | tee -a "$LOG_FILE"
    exit 1
fi

cd "$SERVER_DIR"

# --- Check if server is running ---
RUNNING=0
if screen -ls | grep -q "\.${SERVER_NAME}"; then
    RUNNING=1
    echo "Stopping running server: $SERVER_NAME" | tee -a "$LOG_FILE"
    screen -S "$SERVER_NAME" -X stuff "say Backup starting... server stopping...\nstop\n"
fi

# --- Wait for shutdown ---
if [ "$RUNNING" -eq 1 ]; then
    echo "Waiting for shutdown..." | tee -a "$LOG_FILE"
    tries=0
    while screen -ls | grep -q "\.${SERVER_NAME}"; do
        if (( tries >= 6 )); then
            echo "Force closing screen session!" | tee -a "$LOG_FILE"
            screen -S "$SERVER_NAME" -X quit
            break
        fi
        echo "Still running... (${tries} x 5s)" | tee -a "$LOG_FILE"
        sleep 5
        ((tries++))
    done
fi

# --- Build backup list ---
FILES=()
for f in server.properties eula.txt ops.json whitelist.json banned-ips.json banned-players.json usercache.json log4j2.xml start.sh; do
    [ -f "$f" ] && FILES+=("$f")
done
[ -d world ] && FILES+=("world")

ZIP_FILE="${BACKUP_DIR}/${SERVER_NAME}_${TIMESTAMP}.zip"

echo "Creating backup ZIP: ${ZIP_FILE}" | tee -a "$LOG_FILE"
zip -r "$ZIP_FILE" "${FILES[@]}" 2>&1 | tee -a "$LOG_FILE"

# --- Apply backup retention ---
BACKUPS=( $(ls -t "${BACKUP_DIR}/${SERVER_NAME}_"*.zip 2>/dev/null) )
if [ "${#BACKUPS[@]}" -gt "$MAX_BACKUPS" ]; then
    echo "Trimming backups to last $MAX_BACKUPS copies." | tee -a "$LOG_FILE"
    for b in "${BACKUPS[@]:$MAX_BACKUPS}"; do
        echo "Deleting old backup: $b" | tee -a "$LOG_FILE"
        rm -f "$b"
    done
fi

# --- Restart if needed ---
if [ "$RUNNING" -eq 1 ]; then
    echo "Restarting server: $SERVER_NAME" | tee -a "$LOG_FILE"
    screen -dmS "$SERVER_NAME" ./start.sh
fi

echo "Backup completed: $(date)" | tee -a "$LOG_FILE"
