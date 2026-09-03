#!/usr/bin/env bash
# Rewrite the API's systemd unit, on the runner, as root.
#
#   aws ssm send-command --region ap-southeast-2 \
#     --instance-ids "$(aws cloudformation describe-stacks --stack-name moral-atlas-dev \
#        --query "Stacks[0].Outputs[?OutputKey=='RunnerInstanceId'].OutputValue" --output text)" \
#     --document-name AWS-RunShellScript \
#     --parameters 'commands=["/opt/atlas/app/infra/reconfigure-api.sh"]'
#
# The unit used to exist only on the instance, written by hand at some point and
# recorded nowhere, so its flags could not be reviewed and would not survive
# rebuilding the box. Two of them turned out to matter:
#
#   --workers 2          One worker serves one request at a time whenever that
#                        request is doing numpy work, and this API has an
#                        endpoint that spends twenty seconds in an eigenvalue
#                        loop on a cache miss. Somebody clicking through the
#                        survey while that runs waits behind it, and CloudFront
#                        gives up before they do. Two workers on two vCPUs, at
#                        roughly 256 MB each against 1.1 GB free.
#   --timeout-keep-alive The origin must not close a pooled connection while
#                        CloudFront still believes it is open, or the viewer
#                        gets a 502 that the origin never logs — because the
#                        request never arrived. uvicorn's default is 5 seconds
#                        and CloudFront's OriginKeepaliveTimeout is also 5, so
#                        they race. 75 is comfortably past CloudFront's 60
#                        second read timeout, which makes CloudFront always the
#                        side that closes.
set -euo pipefail

cat > /etc/systemd/system/atlas-api.service <<'UNIT'
[Unit]
Description=Moral Atlas API
After=network-online.target

[Service]
User=ec2-user
WorkingDirectory=/opt/atlas/app
# Bound to 0.0.0.0 rather than localhost because CloudFront has to reach it.
# The security group is what closes it: inbound 8000 only from the managed
# CloudFront origin-facing prefix list, exactly as /admin* is handled.
ExecStart=/opt/atlas/app/.venv/bin/uvicorn moral_atlas.api:app \
  --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*' \
  --workers 2 --timeout-keep-alive 75
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl restart atlas-api
sleep 3
echo "  service:  $(systemctl is-active atlas-api)"
echo "  workers:  $(pgrep -fc 'uvicorn moral_atlas.api:app' || true)"
