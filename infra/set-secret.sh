#!/usr/bin/env bash
# Set one or more keys in the stack secret, leaving the others alone.
#
#   ./infra/set-secret.sh github_token=ghp_xxx
#   ./infra/set-secret.sh ANTHROPIC_API_KEY=sk-ant-xxx TMDB_READ_TOKEN=eyJ...
#
# Why this exists: `aws secretsmanager put-secret-value` replaces the entire
# secret. Adding a github_token by hand with it is the obvious move, and it
# silently deletes the Anthropic key at the same time. This reads, merges and
# writes back.
#
# Values are read from the arguments, so they land in your shell history. For
# anything long-lived, prefer:
#   ./infra/set-secret.sh github_token="$(cat /path/to/token)"
set -euo pipefail

if [ -z "${CI:-}" ]; then
  export AWS_PROFILE="${ATLAS_AWS_PROFILE:-ai-sandbox}"
fi

PROJECT="${PROJECT:-moral-atlas}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
REGION="${AWS_REGION:-ap-southeast-2}"
SECRET_ID="$PROJECT/$ENVIRONMENT/config"

if [ $# -eq 0 ]; then
  echo "usage: $0 KEY=VALUE [KEY=VALUE ...]" >&2
  echo "keys: ANTHROPIC_API_KEY TMDB_READ_TOKEN TMDB_API_KEY" >&2
  echo "      OPENSUBTITLES_API_KEY OPENSUBTITLES_USERNAME" >&2
  echo "      OPENSUBTITLES_PASSWORD github_token" >&2
  exit 1
fi

CURRENT=$(aws secretsmanager get-secret-value --region "$REGION" \
  --secret-id "$SECRET_ID" --query SecretString --output text)

MERGED="$CURRENT"
for pair in "$@"; do
  case "$pair" in
    *=*) ;;
    *) echo "not a KEY=VALUE pair: $pair" >&2; exit 1 ;;
  esac
  key=${pair%%=*}
  value=${pair#*=}
  MERGED=$(printf '%s' "$MERGED" | jq --arg k "$key" --arg v "$value" '.[$k] = $v')
  echo "  set $key (${#value} chars)"
done

aws secretsmanager put-secret-value --region "$REGION" \
  --secret-id "$SECRET_ID" --secret-string "$MERGED" \
  --query 'VersionId' --output text >/dev/null

echo "updated $SECRET_ID"
echo
echo "Now pick it up on the runner:"
echo "  aws ssm send-command --region $REGION \\"
echo "    --instance-ids \$(aws cloudformation describe-stacks --region $REGION \\"
echo "      --stack-name $PROJECT-$ENVIRONMENT \\"
echo "      --query \"Stacks[0].Outputs[?OutputKey=='RunnerInstanceId'].OutputValue\" \\"
echo "      --output text) \\"
echo "    --document-name AWS-RunShellScript \\"
echo "    --parameters 'commands=[\"/usr/local/bin/atlas-update main\"]'"
