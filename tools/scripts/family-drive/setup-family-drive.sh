#!/bin/bash
# Script:     setup-family-drive.sh
# Purpose:    Set up the Family share on oscar (P: on the Utah PCs), reached
#             through Cloudflare Tunnel private routing + Cloudflare Access.
#             See docs/workflows/family-drive.md. Safe to run again.
# Usage:      cd /srv/mc && sudo bash tools/scripts/family-drive/setup-family-drive.sh
#             FAMILY_SIZE=200G sudo bash ...   (size of a NEW drive; default 100G)
set -euo pipefail

FAMILY_IP=10.77.77.1                       # oscar's address as the Utah PCs see it (on lo)
FAMILY_SIZE="${FAMILY_SIZE:-100G}"         # hard cap: the share is its own ext4 image
IMAGE=/mnt/overflow/family/family.img
MOUNT=/srv/family
SMB_USER=family
TUNNEL=oscar-family
OWNER=mike                                 # owns ~/.cloudflared (cert.pem, tunnel creds)
CF_DIR=/home/$OWNER/.cloudflared
CONFIG=$CF_DIR/$TUNNEL-config.yml
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"

[[ $EUID -eq 0 ]] || { echo "Run with sudo."; exit 1; }
as_owner() { sudo -u "$OWNER" -H "$@"; }

echo "== 1/6 Address $FAMILY_IP on lo (systemd unit, survives reboots)"
cp "$REPO/tools/systemd/oscar-family-ip.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now oscar-family-ip.service
ip -br addr show lo | grep -q "$FAMILY_IP" || { echo "!! $FAMILY_IP is not on lo"; exit 1; }

echo "== 2/6 Samba user '$SMB_USER' (no shell, no home)"
if ! id "$SMB_USER" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SMB_USER"
fi
if pdbedit -L | grep -q "^$SMB_USER:"; then
    echo "   already has a Samba password (change it: sudo smbpasswd $SMB_USER)"
else
    echo "   Choose the password Mom and Dad's PCs will save (write it down):"
    smbpasswd -a "$SMB_USER"
fi

echo "== 3/6 $FAMILY_SIZE drive image $IMAGE -> $MOUNT"
if [[ ! -f $IMAGE ]]; then
    mkdir -p "$(dirname "$IMAGE")"
    truncate -s "$FAMILY_SIZE" "$IMAGE"    # sparse: uses only what's written
    mkfs.ext4 -q -L family -m 0 "$IMAGE"
fi
mkdir -p "$MOUNT"
if ! grep -q "^$IMAGE " /etc/fstab; then
    cp /etc/fstab "/etc/fstab.bak-$(date +%Y%m%d-%H%M%S)"
    printf '\n# Family share (P:), docs/workflows/family-drive.md\n%s %s ext4 loop,nofail,x-systemd.requires-mounts-for=/mnt/overflow 0 2\n' \
        "$IMAGE" "$MOUNT" >> /etc/fstab
    systemctl daemon-reload
fi
mountpoint -q "$MOUNT" || mount "$MOUNT"
chown "$SMB_USER:$SMB_USER" "$MOUNT"
chmod 2775 "$MOUNT"
df -h "$MOUNT" | tail -1

echo "== 4/6 [Family] share in /etc/samba/smb.conf"
if ! grep -q '^\[Family\]' /etc/samba/smb.conf; then
    cp /etc/samba/smb.conf "/etc/samba/smb.conf.bak-$(date +%Y%m%d-%H%M%S)"
    cat >> /etc/samba/smb.conf <<EOF

# Family shared drive (P: on the Utah PCs), docs/workflows/family-drive.md
[Family]
   comment = Family shared drive
   path = $MOUNT
   valid users = $SMB_USER $OWNER
   force user = $SMB_USER
   force group = $SMB_USER
   create mask = 0664
   directory mask = 2775
   read only = No
   hosts allow = 127.0.0.1 $FAMILY_IP 192.168.1.0/24
   veto files = /lost+found/
   vfs objects = recycle
   recycle:repository = .recycle
   recycle:keeptree = yes
   recycle:versions = yes
   recycle:exclude_dir = .recycle
EOF
fi
testparm -s >/dev/null 2>&1 || { echo "!! testparm failed; smb.conf backup is beside it"; exit 1; }
systemctl reload smbd
cat > /etc/cron.daily/family-drive-recycle <<EOF
#!/bin/sh
# Empty the Family share's recycle bin of files deleted 30+ days ago.
[ -d $MOUNT/.recycle ] && find $MOUNT/.recycle -type f -ctime +30 -delete && find $MOUNT/.recycle -mindepth 1 -type d -empty -delete
exit 0
EOF
chmod 755 /etc/cron.daily/family-drive-recycle

echo "== 5/6 Tunnel '$TUNNEL' with a private route to $FAMILY_IP/32"
if ! as_owner cloudflared tunnel list --name "$TUNNEL" -o json | grep -q '"id"'; then
    as_owner cloudflared tunnel create "$TUNNEL"
fi
TID=$(as_owner cloudflared tunnel list --name "$TUNNEL" -o json \
      | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["id"])')
echo "   tunnel id: $TID"
if ! as_owner cloudflared tunnel route ip show 2>/dev/null | grep -q "$FAMILY_IP/32"; then
    as_owner cloudflared tunnel route ip add "$FAMILY_IP/32" "$TUNNEL"
fi
as_owner tee "$CONFIG" >/dev/null <<EOF
tunnel: $TID
credentials-file: $CF_DIR/$TID.json
warp-routing:
  enabled: true
ingress:
  - service: http_status:404
EOF

echo "== 6/6 Tunnel service"
cp "$REPO/tools/systemd/cloudflared-oscar-family.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cloudflared-oscar-family.service
sleep 5
systemctl is-active cloudflared-oscar-family.service
as_owner cloudflared tunnel info "$TUNNEL" | tail -3

echo
echo "Done on oscar. Next: the Cloudflare dashboard steps in docs/workflows/family-drive.md."
