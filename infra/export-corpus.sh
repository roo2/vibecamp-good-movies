#!/usr/bin/env bash
# Publish the corpus — and only the corpus — from a machine that has the store.
#
#   ./infra/export-corpus.sh                 # build and upload
#   ./infra/export-corpus.sh --no-upload     # build the file and stop
#
# Two audiences, one file.
#
#   the runner       infra/load-corpus.sh pulls it and swaps the derived tables
#                    in, leaving the demo's user records alone.
#   a collaborator   pulls the same object and points a checkout at it:
#
#                      aws s3 cp s3://<data-bucket>/latest/atlas-corpus.sqlite \
#                        data/atlas.sqlite
#
#                    and then has every film, skeleton, item and score without
#                    an API key or a sweep of their own. `atlas dataset`,
#                    Datasette and the interface all read it as-is.
#
# The user tables are dropped rather than filtered, so sharing the file cannot
# leak who used the demo — there is no row to leak. That is also why this is not
# `atlas export`, which copies the store whole for moving between your own
# machines.
set -euo pipefail

if [ -z "${CI:-}" ]; then
  export AWS_PROFILE="${ATLAS_AWS_PROFILE:-ai-sandbox}"
fi

REGION="${AWS_REGION:-ap-southeast-2}"
PROJECT="${PROJECT:-moral-atlas}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
STACK="${STACK:-$PROJECT-$ENVIRONMENT}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ATLAS_DB:-$ROOT/data/atlas.sqlite}"
OUT="${OUT:-$ROOT/dist/atlas-corpus.sqlite}"
KEY="${CORPUS_KEY:-latest/atlas-corpus.sqlite}"

UPLOAD=true
[ "${1:-}" = "--no-upload" ] && UPLOAD=false

# Keep this list and the one in load_corpus.py saying the same thing.
USER_TABLES="users user_sessions movie_ratings test_results group_sessions \
session_members shortlist_reactions session_shortlist_films"

test -f "$SRC" || { echo "no store at $SRC" >&2; exit 1; }
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"

# VACUUM INTO, not cp: it folds in the write-ahead log and takes a consistent
# snapshot, so this is safe to run while something else is reading. Copying the
# file by hand mid-write gives you a torn database that looks fine for months.
echo "→ snapshotting $SRC"
sqlite3 "$SRC" "VACUUM INTO '$OUT';"

echo "→ dropping user tables"
for table in $USER_TABLES; do
  sqlite3 "$OUT" "DROP TABLE IF EXISTS $table;"
done
sqlite3 "$OUT" "VACUUM;"

# Belt and braces. A typo in the list above would otherwise publish user records
# to a file whose whole purpose is not having any.
LEFT=$(sqlite3 "$OUT" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN \
('users','user_sessions','movie_ratings','test_results','group_sessions',\
'session_members','shortlist_reactions','session_shortlist_films');")
if [ "$LEFT" != "0" ]; then
  echo "refusing: $LEFT user table(s) survived the drop" >&2
  exit 1
fi

echo
printf '%-22s %8s\n' TABLE ROWS
for table in $(sqlite3 "$OUT" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"); do
  printf '%-22s %8s\n' "$table" "$(sqlite3 "$OUT" "SELECT COUNT(*) FROM \"$table\";")"
done
echo
echo "→ wrote $OUT ($(du -h "$OUT" | cut -f1))"

if [ "$UPLOAD" = false ]; then
  exit 0
fi

BUCKET="${DATA_BUCKET:-$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --region "$REGION" --query "Stacks[0].Outputs[?OutputKey=='DataBucketName'].OutputValue" \
  --output text)}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

echo "→ uploading to s3://$BUCKET/$KEY"
aws s3 cp "$OUT" "s3://$BUCKET/$KEY" --region "$REGION"
aws s3 cp "$OUT" "s3://$BUCKET/snapshots/$STAMP/atlas-corpus.sqlite" --region "$REGION"

cat <<NOTE

Collaborators:

  aws s3 cp s3://$BUCKET/$KEY data/atlas.sqlite

The runner:

  aws ssm send-command --region $REGION \\
    --instance-ids "\$(aws cloudformation describe-stacks --stack-name $STACK \\
       --query "Stacks[0].Outputs[?OutputKey=='RunnerInstanceId'].OutputValue" --output text)" \\
    --document-name AWS-RunShellScript \\
    --parameters 'commands=["/opt/atlas/app/infra/load-corpus.sh"]'
NOTE
