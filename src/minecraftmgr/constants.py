APP_NAME = "MinecraftMgr"
VERSION = "0.1.0"
REALM_DOMAIN = "gamenightbymike.com"
SITE_URL = f"https://minecraft.{REALM_DOMAIN}"
TRIGGER_URL = f"https://trigger.{REALM_DOMAIN}"
SCREENSHOTS_URL = f"https://shots.{REALM_DOMAIN}/report/"

# Realm statuses in servers.json. "archived" realms live in <data_root>/_archive/<data_dir>
# (tools/scripts/minecraft_archive_world.sh) and are left out of the page, Autostart and backups.
REALM_STATUSES = ("active", "inactive", "archived")
ARCHIVE_DIR_NAME = "_archive"

COMPANY_NAME = "Game Night by Mike"
COMPANY_YEAR = 2026
LOGO_VERSION = 1
