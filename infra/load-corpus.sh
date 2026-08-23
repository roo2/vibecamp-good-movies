#!/usr/bin/env bash
# Replace the runner's corpus with a snapshot from S3, and leave every user
# record where it is.
#
# Runs ON THE RUNNER, as root, usually over SSM:
#
#   aws ssm send-command --region ap-southeast-2 \
#     --instance-ids "$(aws cloudformation describe-stacks --stack-name moral-atlas-dev \
#        --query "Stacks[0].Outputs[?OutputKey=='RunnerInstanceId'].OutputValue" --output text)" \
#     --document-name AWS-RunShellScript \
#     --parameters 'commands=["/opt/atlas/app/infra/load-corpus.sh"]'
#
# The snapshot it reads is written by `infra/export-corpus.sh` on a machine
# that has the store. Why two halves rather than one: the laptop holds the
# corpus, the runner holds the users, and neither should overwrite the other.
#
# The corpus tables are derived — a sweep can rebuild them. The user tables are
# not: they are the only record that somebody used the demo. So the corpus is
# replaced wholesale and the user tables are never written, only counted, and
# the counts are printed either side so the claim is checkable rather than
# asserted.
set -euo pipefail

REGION="${AWS_REGION:-ap-southeast-2}"
export AWS_DEFAULT_REGION="$REGION"
PROJECT="${PROJECT:-moral-atlas}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
STACK="${STACK:-$PROJECT-$ENVIRONMENT}"
LIVE="${ATLAS_DB:-/opt/atlas/data/atlas.sqlite}"
PYTHON="${ATLAS_PYTHON:-/opt/atlas/app/.venv/bin/python}"
SERVICE="${ATLAS_SERVICE:-atlas-api}"

# Where the bucket name comes from, in order. The instance role can read and
# write the data bucket but cannot call cloudformation:DescribeStacks — asking
# the stack is what a laptop does, and it fails with AccessDenied here. The
# runner already knows the answer: the template bakes it into atlas-snapshot at
# boot. Read it from there, and only fall back to the stack.
if [ -z "${DATA_BUCKET:-}" ] && [ -r /usr/local/bin/atlas-snapshot ]; then
  DATA_BUCKET=$(sed -n 's/^BUCKET="\(.*\)"$/\1/p' /usr/local/bin/atlas-snapshot | head -1)
fi
BUCKET="${DATA_BUCKET:-$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='DataBucketName'].OutputValue" --output text)}"
if [ -z "$BUCKET" ] || [ "$BUCKET" = "None" ]; then
  echo "could not work out the data bucket; pass DATA_BUCKET=..." >&2
  exit 1
fi
KEY="${CORPUS_KEY:-latest/atlas-corpus.sqlite}"
INCOMING=/opt/atlas/data/incoming-corpus.sqlite
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

test -f "$LIVE" || { echo "no store at $LIVE" >&2; exit 1; }
test -x "$PYTHON" || { echo "no interpreter at $PYTHON" >&2; exit 1; }

# Load into the file the API actually opens, or refuse to load at all.
#
# The API resolves its store ROOT-relative, as /opt/atlas/app/data/atlas.sqlite,
# and that path is a symlink to the mounted volume. A symlink is a fragile thing
# to rest a deployment on: check out any tracked file under data/ and git
# replaces the link with a real directory, after which `atlas init` quietly
# makes a second, empty store there. Everything then still "works" — the loader
# reports a successful swap of a file nobody reads, and the site serves an empty
# corpus with a straight face.
#
# So compare the two by inode rather than trusting the layout, and stop if they
# have come apart. Repairing it means merging the user rows written to the stray
# store before removing it, which is a judgement call and not a loader's job.
API_STORE=$("$PYTHON" -c 'from moral_atlas.config import settings; print(settings().db_path)' 2>/dev/null || true)
if [ -n "$API_STORE" ] && ! [ "$API_STORE" -ef "$LIVE" ]; then
  echo "the API reads $API_STORE, which is not $LIVE" >&2
  echo "the data/ symlink has been replaced by a real directory; the deployment is split in two." >&2
  echo "merge any user rows out of $API_STORE, delete it, then: ln -s /opt/atlas/data /opt/atlas/app/data" >&2
  exit 1
fi

# Stop the API first. SQLite would serialise the writes anyway, but a request
# that reads films halfway through the swap gets a coherent-looking answer that
# is half of each, which is worse than a moment of downtime.
echo "→ stopping $SERVICE"
systemctl stop "$SERVICE"
restart() { echo "→ starting $SERVICE"; systemctl start "$SERVICE"; }
trap restart EXIT

echo "→ backing up to $LIVE.bak-$STAMP"
cp -a "$LIVE" "$LIVE.bak-$STAMP"

echo "→ fetching s3://$BUCKET/$KEY"
aws s3 cp "s3://$BUCKET/$KEY" "$INCOMING"

echo "→ loading"
ATLAS_LIVE="$LIVE" ATLAS_INCOMING="$INCOMING" "$PYTHON" "$(dirname "$0")/load_corpus.py"

echo "→ done; the trap restarts $SERVICE"
