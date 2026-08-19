#!/bin/bash
# Imported verbatim from oscar:/opt/mc/Scripts/config_ufw_rules.sh on
# 2026-08-18 (byte-identical to the copy that also lived at
# /opt/scripts/config_ufw_rules.sh — only this one copy was imported). Not
# yet rewritten — see tools/scripts/README.md.
# Script:     config_ufw_rules.sh
# Purpose:    Configure UFW firewall rules for Minecraft, Samba (LAN-only), SSH, Web, Plex, and Docker services
# Usage:      sudo bash config_ufw_rules.sh

# === Helper Function for Standard Port Rules ===
# Allow one port/protocol through ufw, skipping if a matching rule already exists.
check_and_allow() {
    local port="$1"
    local proto="$2"
    local comment="$3"
    if sudo ufw status | grep -q "${port}/${proto}"; then
        echo "⏭️  Rule for ${port}/${proto} already exists — skipping."
    else
        echo "✅ Adding rule for ${port}/${proto} (${comment})"
        sudo ufw allow ${port}/${proto} comment "${comment}"
    fi
}

# === Helper Function for Docker → Host Access Rules ===
# Allow the Docker bridge subnet to reach one host port, skipping if already allowed.
check_and_allow_docker_access() {
    local docker_subnet="172.17.0.0/16"
    local port="$1"
    local comment="$2"

    if sudo ufw status | grep -q "${docker_subnet}.*${port}"; then
        echo "⏭️  Rule for Docker ${docker_subnet} to port ${port} already exists — skipping."
    else
        echo "✅ Allowing Docker ${docker_subnet} to access host port ${port} (${comment})"
        sudo ufw allow from ${docker_subnet} to any port ${port} proto tcp comment "${comment}"
    fi
}

# === Optional Full Reset ===
echo "⚠️  WARNING: This will reset all existing UFW rules!"
read -p "Do you want to reset all existing UFW rules? [y/N] " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    echo "🔁 Resetting UFW..."
    sudo ufw --force reset
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    echo "✅ UFW reset and default policies set."
else
    echo "❌ Skipping reset. Keeping existing rules."
fi

echo
echo "=== Setting UFW Rules ==="

# === Minecraft Server Ports ===
MINECRAFT_PORTS=(26005 26010)
for port in "${MINECRAFT_PORTS[@]}"; do
    check_and_allow "$port" "tcp" "Minecraft server port ${port}"
done

# === Samba Ports (LAN-only) ===
LAN_SUBNET="192.168.1.0/24"
echo "✅ Restricting Samba ports to LAN (${LAN_SUBNET})..."
sudo ufw delete allow 137/udp >/dev/null 2>&1
sudo ufw delete allow 138/udp >/dev/null 2>&1
sudo ufw delete allow 139/tcp >/dev/null 2>&1
sudo ufw delete allow 445/tcp >/dev/null 2>&1

sudo ufw allow from ${LAN_SUBNET} to any port 137 proto udp comment "Samba NetBIOS Name Service (LAN only)"
sudo ufw allow from ${LAN_SUBNET} to any port 138 proto udp comment "Samba NetBIOS Datagram Service (LAN only)"
sudo ufw allow from ${LAN_SUBNET} to any port 139 proto tcp comment "Samba NetBIOS Session Service (LAN only)"
sudo ufw allow from ${LAN_SUBNET} to any port 445 proto tcp comment "Samba SMB over TCP (LAN only)"

# === Plex Media Server (LAN-only) ===
echo "✅ Allowing Plex Media Server (port 32400) for LAN (${LAN_SUBNET})..."
sudo ufw allow from ${LAN_SUBNET} to any port 32400 proto tcp comment "Plex Media Server (LAN only)"

# === SSH Port ===
check_and_allow 22 tcp "SSH remote access"

# === Web Server Ports ===
check_and_allow 80 tcp "HTTP (web server)"
check_and_allow 443 tcp "HTTPS (secure web server)"

# === Docker → Host Access ===
check_and_allow_docker_access 8088 "NPM to entry-nginx backend"
check_and_allow_docker_access 32400 "Docker access to Plex Media Server"

# === Check and Enable UFW if Needed ===
echo
UFW_STATUS=$(sudo ufw status | grep -i "Status: inactive")
if [[ -n "$UFW_STATUS" ]]; then
    echo "🚫 UFW is currently disabled."
    read -p "Do you want to enable the UFW firewall now? [y/N] " enable_confirm
    if [[ "$enable_confirm" =~ ^[Yy]$ ]]; then
        echo "✅ Enabling UFW..."
        sudo ufw --force enable
    else
        echo "⚠️  UFW remains disabled. Rules won't apply until you enable it."
    fi
else
    echo "🔄 Reloading UFW to apply changes..."
    sudo ufw reload
fi

# === Show Current Rules ===
echo
echo "✅ Current UFW Rules:"
sudo ufw status numbered verbose
