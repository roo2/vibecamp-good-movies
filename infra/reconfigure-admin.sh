#!/bin/bash
# Reconfigure the sqlite-web admin on a RUNNING instance to match the template.
#
# Needed because a CloudFormation update that changes UserData does not re-run
# it on an instance CloudFormation chose not to replace. The template is the
# source of truth; this brings an existing box into line with it.
#
# On the bind address: sqlite-web listens on 0.0.0.0 rather than 127.0.0.1 so
# that CloudFront can reach it as an origin. The port is NOT open to the
# internet — RunnerSecurityGroup permits inbound 8002 only from the managed
# prefix list com.amazonaws.global.cloudfront.origin-facing, and the /admin*
# CloudFront behaviour sits behind the basic-auth function. Verify with:
#
#   aws ec2 describe-security-groups --group-ids <sg> \
#     --query 'SecurityGroups[0].IpPermissions'
#
set -uo pipefail

cat > /etc/systemd/system/atlas-sqliteweb.service <<'UNIT'
[Unit]
Description=sqlite-web admin over the atlas store
After=network-online.target
[Service]
User=ec2-user
WorkingDirectory=/opt/atlas/app
ExecStart=/opt/atlas/app/.venv/bin/sqlite_web /opt/atlas/data/atlas.sqlite --host 0.0.0.0 --port 8002 --no-browser --url-prefix /admin
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl restart atlas-sqliteweb
sleep 4

echo "  service:      $(systemctl is-active atlas-sqliteweb)"
echo "  listening:    $(ss -tln 2>/dev/null | grep -c ':8002') socket(s) on 8002"
echo "  local /admin: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8002/admin/)"
