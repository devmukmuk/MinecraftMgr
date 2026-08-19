#!/bin/bash
# Imported verbatim from oscar:/opt/mc/Scripts/start_all_minecraft_servers.sh
# on 2026-08-18. Not yet rewritten — see tools/scripts/README.md for known
# issues (hardcoded servers= array) before relying on this for a new realm.
#
# Script:  start_all_minecraft_servers.sh
# Purpose: Start every server listed in the hardcoded `servers` array that
#          isn't already running (checked via `screen` and `pgrep`), logging
#          each decision.
# Usage:   ./start_all_minecraft_servers.sh

set -u

servers=("gravestone_26_1_2")
base_dir="/srv/minecraft"
logfile="/srv/minecraft/logs/start_all_minecraft_servers.log"

mkdir -p "$(dirname "$logfile")"

# Current local timestamp, used to prefix every log line.
timestamp() {
    date "+%Y-%m-%d %H:%M:%S"
}

echo "$(timestamp) - Starting Minecraft servers..." | tee -a "$logfile"

for server in "${servers[@]}"; do
    server_path="${base_dir}/${server}"
    screen_name="${server}"
    jar_name="server_${server}.jar"

    if screen -list | grep -q "[.]${screen_name}[[:space:]]"; then
        echo "$(timestamp) - SKIP: $screen_name already running" | tee -a "$logfile"
        continue
    fi

    if pgrep -f "$jar_name" >/dev/null; then
        echo "$(timestamp) - SKIP: Java process for $jar_name already running" | tee -a "$logfile"
        continue
    fi

    if [ ! -x "${server_path}/start.sh" ]; then
        echo "$(timestamp) - ERROR: ${server_path}/start.sh missing or not executable" | tee -a "$logfile"
        continue
    fi

    echo "$(timestamp) - Starting $server..." | tee -a "$logfile"

    (
        cd "$server_path" || exit 1
        exec screen -dmS "$screen_name" ./start.sh
    )

    echo "$(timestamp) - Launch command sent for $screen_name" | tee -a "$logfile"
done

echo "$(timestamp) - All done." | tee -a "$logfile"
exit 0
