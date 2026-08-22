#!/usr/bin/env bash
# Publish the interface to the demo URL.
#
#   ./infra/deploy-site.sh              # the design screens, as they stand
#   SITE_DIR=web/dist ./infra/deploy-site.sh   # once a real front end exists
#
# Until something is built, this publishes design/ — which is genuinely the
# thing worth showing, since the fourteen screens run offline and the fixture
# is a working payload.
set -euo pipefail

# Pinned for the same reason as deploy.sh, and skipped in CI for the same
# reason too — see the note there.
if [ -z "${CI:-}" ]; then
  export AWS_PROFILE="${ATLAS_AWS_PROFILE:-ai-sandbox}"
fi

PROJECT="${PROJECT:-moral-atlas}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
REGION="${AWS_REGION:-ap-southeast-2}"
STACK="${STACK:-$PROJECT-$ENVIRONMENT}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SITE_DIR="${SITE_DIR:-}"

out() {
  aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

BUCKET=$(out SiteBucketName)
DIST=$(out DistributionId)
URL=$(out SiteUrl)
if [ -z "$BUCKET" ] || [ "$BUCKET" = "None" ]; then
  echo "no stack named $STACK in $REGION — run ./infra/deploy.sh first" >&2
  exit 1
fi

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

if [ -n "$SITE_DIR" ]; then
  echo "→ staging $SITE_DIR"
  if [ ! -d "$ROOT/$SITE_DIR" ]; then
    echo "SITE_DIR=$SITE_DIR does not exist under $ROOT — build it first" >&2
    exit 1
  fi
  cp -R "$ROOT/$SITE_DIR/." "$STAGE/"
  # The sync below deletes whatever it does not stage, so the design screens
  # would vanish the first time a real front end is published. They run
  # offline and cost nothing to carry, so keep them reachable under /design.
  if [ ! -d "$STAGE/design" ]; then
    echo "→ staging design/ alongside it"
    mkdir -p "$STAGE/design"
    cp -R "$ROOT/design/." "$STAGE/design/"
  fi
else
  echo "→ staging design/ (no SITE_DIR given)"
  mkdir -p "$STAGE/design"
  cp -R "$ROOT/design/." "$STAGE/design/"
  # The screen flow is the demo. Make it the front door.
  cp "$ROOT/design/parable-screen-flow.html" "$STAGE/index.html"
fi

# /api/session.json is the one payload the bucket still answers — CloudFront
# sends the rest of /api/* to the runner. Seed it from the fixture so the site
# is never serving a 404 there; `atlas-publish` on the runner overwrites it with
# real output later. The explorer's dataset is NOT here: it is published under
# /data, which the sync above carries, precisely so it is served by the bucket
# rather than by an API that has no route for it.
mkdir -p "$STAGE/api"
if [ ! -f "$STAGE/api/session.json" ]; then
  cp "$ROOT/design/fixtures/session.json" "$STAGE/api/session.json"
fi

echo "→ uploading to s3://$BUCKET"
# Everything except the payloads gets a long cache; CloudFront is invalidated
# below, so a stale copy never outlives a deploy.
aws s3 sync "$STAGE" "s3://$BUCKET" --region "$REGION" --delete \
  --exclude "api/*" --cache-control "public,max-age=300"
# The payloads, uncached, so a fresh publish shows up on the next reload. No
# --delete here: the runner publishes into this prefix too, and a site deploy
# has no business removing what it wrote.
aws s3 sync "$STAGE/api" "s3://$BUCKET/api" --region "$REGION" \
  --content-type application/json --cache-control "no-cache"

echo "→ invalidating the edge cache"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths '/*' \
  --query 'Invalidation.Id' --output text

echo
echo "live: $URL"
