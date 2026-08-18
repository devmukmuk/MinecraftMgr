#!/bin/bash
# Imported verbatim from oscar:/opt/mc/Scripts/stop_all_minecraft_servers.sh
# on 2026-08-18. Not yet rewritten — see tools/scripts/README.md for known
# issues (hardcoded servers= array) before relying on this for a new realm.

set -u

servers=("gravestone_26_1_2")
logfile="/srv/minecraft/logs/stop_all_minecraft_servers.log"

mkdir -p "$(dirname "$logfile")"

timestamp() {
    date "+%Y-%m-%d %H:%M:%S"
}

echo "$(timestamp) - Stopping Minecraft servers..." | tee -a "$logfile"

for server in "${servers[@]}"; do
    screen_name="${server}"
    jar_name="server_${server}.jar"

    if screen -list | grep -q "[.]${screen_name}[[:space:]]"; then
        echo "$(timestamp) - Sending shutdown to $screen_name" >> "$logfile"

        screen -S "$screen_name" -p 0 -X stuff "say Server shutting down...$(printf '\r')"
        sleep 2
        screen -S "$screen_name" -p 0 -X stuff "save-all$(printf '\r')"
        sleep 2
        screen -S "$screen_name" -p 0 -X stuff "stop$(printf '\r')"

        sleep 10

        if pgrep -af "$jar_name" >/dev/null; then
            echo "$(timestamp) - WARNING: $screen_name still running after stop command" >> "$logfile"
        else
            echo "$(timestamp) - OK: $screen_name stopped" >> "$logfile"
        fi
    else
        echo "$(timestamp) - SKIP: $screen_name not running" >> "$logfile"
    fi
done

echo "$(timestamp) - All done." >> "$logfile"
