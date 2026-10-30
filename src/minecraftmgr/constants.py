APP_NAME = "MinecraftMgr"
VERSION = "0.1.0"
REALM_DOMAIN = "gamenightbymike.com"
SITE_URL = f"https://minecraft.{REALM_DOMAIN}"
TRIGGER_URL = f"https://trigger.{REALM_DOMAIN}"
SCREENSHOTS_URL = f"https://shots.{REALM_DOMAIN}/report/"
# oscar's reserved LAN IP. The AT&T gateway can't reliably hairpin LAN clients through the
# public IP, so PCs at home map each realm's hostname here (modify-local-hosts-override.md).
OSCAR_LAN_IP = "192.168.1.113"

# Velocity proxy: the one public Minecraft port on oscar, routing to every realm.
VELOCITY_PORT = 25565

# Realm statuses in servers.json. "archived" realms live in <data_root>/_archive/<data_dir>
# (tools/scripts/minecraft_archive_world.sh) and are left out of the page, Autostart and backups.
REALM_STATUSES = ("active", "inactive", "archived")
ARCHIVE_DIR_NAME = "_archive"

# Realm game modes in servers.json. "hardcore" realms (hardcore=true in server.properties)
# get their own card on the page and an Archive & Reset action once every player has died.
REALM_MODES = ("survival", "hardcore")

COMPANY_NAME = "Game Night by Mike"
COMPANY_YEAR = 2026
LOGO_VERSION = 1
