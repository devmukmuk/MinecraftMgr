#!/bin/bash
#===============================================================================
# Imported verbatim from oscar:/opt/mc/Scripts/scafold_new_minecraft_server.sh
# on 2026-08-18, for reference only — superseded by `minecraftmgr realm
# provision`/`realm activate` (see docs/epics/PROV-design.md), confirmed
# working live on oscar. See tools/scripts/README.md.
#===============================================================================
# Script:     scafold_new_minecraft_server.sh
# Version:    1.2.0
# Author:     Mike & ChatGPT
#
# Purpose:
#     Scaffold a new Minecraft server under /srv/minecraft/, optionally copying
#     select config files from a reference server.
#
# Example Usage:
#     sudo -u minecraft /opt/scripts/scafold_new_minecraft_server.sh sand_1_21_1
#
#     With overrides:
#     SERVER_VER=1.21.1 PORT=4462 SEED=789123456 \
#     USE=/srv/minecraft/river_1_21_1 \
#     sudo -u minecraft /opt/scripts/scafold_new_minecraft_server.sh sand_1_21_1
#===============================================================================

SERVER_NAME="${1:-new_server}"
SERVER_VER="${SERVER_VER:-1.21.1}"
SERVER_VER_SAFE="${SERVER_VER//./_}"  # e.g. "1.21.1" → "1_21_1"
PORT="${PORT:-4454}"
SEED="${SEED:-2342342342}"
USE="${USE:-}"

BASE_DIR="/srv/minecraft/$SERVER_NAME"
JAR_NAME="server_${SERVER_NAME}.jar"
TEMPLATE_JAR="/srv/minecraft/templates/server_${SERVER_VER_SAFE}.jar"

echo "📁 Creating Minecraft server: $SERVER_NAME"
mkdir -p "$BASE_DIR"/{world,logs,crash-reports,versions,libraries}

# Empty or default control JSON files
for file in banned-ips.json banned-players.json ops.json usercache.json whitelist.json; do
  echo "[]" > "$BASE_DIR/$file"
done

# eula.txt
cat > "$BASE_DIR/eula.txt" <<EOF
# By changing the setting below to TRUE you are indicating your agreement to the EULA.
# https://aka.ms/MinecraftEULA
eula=true
EOF

# log4j2.xml (placeholder)
cat > "$BASE_DIR/log4j2.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <Console name="Console" target="SYSTEM_OUT">
      <PatternLayout pattern="[%d{HH:mm:ss}] [%t/%level]: %msg%n" />
    </Console>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="Console" />
    </Root>
  </Loggers>
</Configuration>
EOF

# server.properties
cat > "$BASE_DIR/server.properties" <<EOF
motd=$SERVER_NAME
level-seed=$SEED
server-port=$PORT
enable-command-block=true
spawn-animals=true
spawn-monsters=true
EOF

# start.sh handling
if [[ -n "$USE" && -f "$USE/start.sh" ]]; then
  cp "$USE/start.sh" "$BASE_DIR/start.sh"

  # Replace NAME and PORT in copied start.sh
  sed -i "s/^NAME=.*/NAME=\"$SERVER_NAME\"/" "$BASE_DIR/start.sh"
  sed -i "s/^PORT=.*/PORT=$PORT/" "$BASE_DIR/start.sh"

  echo "✅ Copied and updated start.sh from $USE"
else
  # Fallback: generate default
  cat > "$BASE_DIR/start.sh" <<EOF
#!/bin/bash
umask 0027
cd "\$(dirname "\$0")"

NAME="$SERVER_NAME"
PORT=$PORT
MEM_MIN="2G"
MEM_MAX="4G"
JAR="server_\${NAME}.jar"

echo "Starting Minecraft server: \$NAME on port \$PORT"
java -Xms\$MEM_MIN -Xmx\$MEM_MAX -jar "\$JAR" nogui --port \$PORT
EOF
  echo "🛠️  Created default start.sh"
fi

chmod +x "$BASE_DIR/start.sh"

# Copy ops.json and whitelist.json from USE
for f in ops.json whitelist.json; do
  if [[ -n "$USE" && -f "$USE/$f" ]]; then
    cp "$USE/$f" "$BASE_DIR/$f"
    echo "✅ Copied $f from $USE"
  fi
done

# Copy version-specific jar
TARGET_JAR="$BASE_DIR/$JAR_NAME"

echo "🔍 Looking for template JAR at: $TEMPLATE_JAR"

if [[ -f "$TEMPLATE_JAR" ]]; then
  cp "$TEMPLATE_JAR" "$TARGET_JAR"
  echo "✅ Copied server JAR from $TEMPLATE_JAR"
else
  echo "// Placeholder jar - replace with actual server jar" > "$TARGET_JAR"
  echo "⚠️  No template JAR for $SERVER_VER found. Created placeholder: $TARGET_JAR"
fi

echo "✅ Done. Server $SERVER_NAME scaffolded at $BASE_DIR"
echo "🧠 Start it using:"
echo "   screen -S $SERVER_NAME $BASE_DIR/start.sh"
