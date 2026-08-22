#!/usr/bin/env bash
# Create or update the stack, then print what you need to use it.
#
#   SITE_PASSWORD='...' ./infra/deploy.sh      # first time
#   ./infra/deploy.sh                          # after that
#   ENVIRONMENT=staging ./infra/deploy.sh      # a second, independent copy
#
# Safe to re-run: CloudFormation works out the difference, and any parameter
# you do not pass keeps the value the stack already has.
set -euo pipefail

# Pinned to the project's account, deliberately overriding whatever AWS_PROFILE
# the shell already carries — `${AWS_PROFILE:-...}` would inherit a `prod` left
# exported by an earlier command, which is the one mistake worth engineering
# out. Override consciously with ATLAS_AWS_PROFILE, never by accident.
#
# Not in CI: GitHub Actions has no profiles at all — it receives temporary
# credentials in the environment from OIDC, and naming a profile there would
# send the SDK looking for a config file that does not exist.
if [ -z "${CI:-}" ]; then
  export AWS_PROFILE="${ATLAS_AWS_PROFILE:-ai-sandbox}"
fi
EXPECTED_ACCOUNT="${ATLAS_AWS_ACCOUNT:-615854521724}"

PROJECT="${PROJECT:-moral-atlas}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
REGION="${AWS_REGION:-ap-southeast-2}"
STACK="${STACK:-$PROJECT-$ENVIRONMENT}"
TEMPLATE="$(cd "$(dirname "$0")" && pwd)/moral-atlas.yaml"

# Unset, not defaulted. The rule below has to tell "the caller asked for this"
# apart from "the caller said nothing", and a default erases the difference.
SITE_AUTH="${SITE_AUTH:-}"
SITE_USERNAME="${SITE_USERNAME:-}"
SITE_PASSWORD="${SITE_PASSWORD:-}"

PARAMS=(
  "ProjectName=$PROJECT"
  "EnvironmentName=$ENVIRONMENT"
)

stack_exists() {
  aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
    >/dev/null 2>&1
}

if stack_exists; then EXISTS=true; else EXISTS=false; fi

# SitePassword has always worked this way — an omitted parameter keeps the
# value the stack already has — and the other two now match it. They did not,
# and CI deploys with neither variable set, so passing the defaults every time
# silently turned basic auth back on for a demo whose owner had deliberately
# turned it off, and would have reverted a changed username the same way. A
# deploy nobody asked to change the front door should not change the front door.
if [ -n "$SITE_AUTH" ]; then
  PARAMS+=("EnableSiteAuth=$SITE_AUTH")
elif [ "$EXISTS" = false ]; then
  SITE_AUTH=true
  PARAMS+=("EnableSiteAuth=$SITE_AUTH")
  echo "→ first deploy: enabling basic auth"
else
  echo "→ keeping the existing basic-auth setting"
fi

if [ -n "$SITE_USERNAME" ]; then
  PARAMS+=("SiteUsername=$SITE_USERNAME")
elif [ "$EXISTS" = false ]; then
  PARAMS+=("SiteUsername=parable")
fi

if [ -n "$SITE_PASSWORD" ]; then
  PARAMS+=("SitePassword=$SITE_PASSWORD")
elif [ "$EXISTS" = true ]; then
  echo "→ keeping the existing site password"
elif [ "$SITE_AUTH" = "true" ]; then
  # No current value to keep, and the default is empty — which would publish
  # unfinished work behind a lock that opens on the return key. Refuse instead.
  echo "SITE_PASSWORD is required on the first deploy while SITE_AUTH=true." >&2
  echo "  SITE_PASSWORD='something' $0" >&2
  echo "  SITE_AUTH=false $0        # to publish the demo openly instead" >&2
  exit 1
fi

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
IDENTITY=$(aws sts get-caller-identity --query Arn --output text)
echo "→ profile ${AWS_PROFILE:-<none: environment credentials>} — account $ACCOUNT — $IDENTITY"
if [ "$ACCOUNT" != "$EXPECTED_ACCOUNT" ]; then
  echo "refusing: expected account $EXPECTED_ACCOUNT, got $ACCOUNT." >&2
  echo "  Set ATLAS_AWS_ACCOUNT if this stack really belongs somewhere else." >&2
  exit 1
fi

echo "→ validating"
aws cloudformation validate-template --region "$REGION" \
  --template-body "file://$TEMPLATE" >/dev/null

echo "→ deploying $STACK to $REGION"
aws cloudformation deploy \
  --region "$REGION" \
  --stack-name "$STACK" \
  --template-file "$TEMPLATE" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides "${PARAMS[@]}"

echo
echo "→ outputs"
aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query 'Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}' \
  --output table

RUNNER=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`RunnerInstanceId`].OutputValue' --output text)

cat <<NOTE

If this was the first deploy, the runner has no credentials yet:

  1. Put the keys in (github_token only if the repo is private):
       aws secretsmanager put-secret-value --region $REGION \\
         --secret-id $PROJECT/$ENVIRONMENT/config \\
         --secret-string '{"ANTHROPIC_API_KEY":"sk-ant-...","TMDB_READ_TOKEN":"...","github_token":""}'

  2. Pick them up on the runner:
       aws ssm start-session --region $REGION --target $RUNNER
       sudo su - ec2-user
       atlas-refresh-env && atlas init && atlas status

  3. Put the interface up:
       ./infra/deploy-site.sh
NOTE
