#!/usr/bin/env bash
# Delete the AWS stack. Everything it holds is gone afterwards.
#
#   ./infra/teardown-aws.sh --dry-run     # what it would delete, and the bill
#   ./infra/teardown-aws.sh               # do it, after one confirmation
#
# About the data on it, which is not being kept.
#
# The runner held 217 accounts and 1,988 ratings — the demo's whole history,
# which `atlas corpus-push` never carried because it never writes user tables.
# It is testing: the owner and a few friends over eight days before going live.
# The shape says so plainly. 95 of the 217 accounts rated nothing at all; of the
# 122 that did, 58 rated exactly twenty — one full deck — and 26 rated exactly
# five and stopped. There is no sign-in, so every browser that opened the site
# became another account, and one person testing on three devices is three
# users. It is not a sample of anybody.
#
# A copy is at data/archive/aws-production-final.sqlite if you want it (185MB,
# integrity checked, ignored by git because data/ is). Deleting it is `rm`.
# Nothing else refers to it.
#
# Worth recording once, because a later count will be tempting: the nightly S3
# snapshots were LOSSY. A file copy that never folded in the write-ahead log —
# the last one held 208 and 1,951 against the box's 217 and 1,988. The archive
# above was taken with VACUUM INTO, which does fold it in.
#
# Order matters. CloudFormation cannot delete a bucket with anything in it, and
# the data bucket is versioned, so "empty" means every version and every delete
# marker. The EBS volume is `DeletionPolicy: Retain` and survives the stack on
# purpose — it goes last, by hand, once you are sure.
set -euo pipefail

export AWS_PROFILE="${ATLAS_AWS_PROFILE:-ai-sandbox}"
REGION="${AWS_REGION:-ap-southeast-2}"
STACK="${STACK:-moral-atlas-dev}"
VOLUME="${VOLUME:-vol-0041356cab7920a76}"

DRY=false
[ "${1:-}" = "--dry-run" ] && DRY=true

buckets() {
  aws cloudformation list-stack-resources --stack-name "$STACK" --region "$REGION" \
    --query "StackResourceSummaries[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" \
    --output text
}

echo "stack   $STACK  ($REGION)"
echo "buckets $(buckets | tr '\t' ' ')"
echo "volume  $VOLUME  (retained by the template; deleted separately below)"
echo
echo "Roughly what this stops paying for, per month:"
cat <<'COST'
  t4g.small, running                        ~US$12
  public IPv4 address                       ~US$3.60
  20GB gp3 volume                           ~US$1.90
  Secrets Manager secret                    ~US$0.40
  S3, CloudFront, CloudWatch                ~US$0.50
                                            --------
                                            ~US$18
COST
echo

if [ "$DRY" = true ]; then
  echo "(dry run — nothing deleted)"
  exit 0
fi

read -r -p "Delete $STACK and everything in it? Type the stack name to confirm: " typed
[ "$typed" = "$STACK" ] || { echo "not confirmed"; exit 1; }

for bucket in $(buckets); do
  echo "→ emptying $bucket (every version and delete marker)"
  while true; do
    payload=$(aws s3api list-object-versions --bucket "$bucket" --region "$REGION" \
      --max-items 500 --output json \
      --query '{Objects: [Versions[].{Key:Key,VersionId:VersionId}, DeleteMarkers[].{Key:Key,VersionId:VersionId}][] , Quiet: `true`}')
    count=$(printf '%s' "$payload" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("Objects") or []))')
    [ "$count" = "0" ] && break
    aws s3api delete-objects --bucket "$bucket" --region "$REGION" --delete "$payload" >/dev/null
    echo "   removed $count"
  done
done

echo "→ deleting the stack (this takes ~15 minutes; CloudFront is the slow part)"
aws cloudformation delete-stack --stack-name "$STACK" --region "$REGION"
aws cloudformation wait stack-delete-complete --stack-name "$STACK" --region "$REGION"
echo "   stack gone"

# Retained on purpose by the template, so that replacing the instance never took
# the database with it. Nothing replaces it now.
echo "→ deleting the retained data volume $VOLUME"
aws ec2 delete-volume --volume-id "$VOLUME" --region "$REGION" || \
  echo "   (already gone, or still detaching — retry in a minute)"

cat <<'AFTER'

Done. Two things the stack deletion does that are worth knowing about:

  The GitHub OIDC provider is account-level and this stack created it, so it
  goes too. Only moral-atlas-dev-github-deploy trusted it — checked, at the
  time this was written — but this is a shared account, so if another project
  later wants OIDC into it, it will have to be recreated.

  The Secrets Manager secret is SCHEDULED for deletion, not deleted, with a
  recovery window of up to 30 days. It goes on costing about 40 cents a month
  until then. To finish it now:

    aws secretsmanager delete-secret --region ap-southeast-2 \
      --secret-id moral-atlas/dev/config --force-delete-without-recovery

Then delete .github/workflows/deploy.yml, infra/deploy.sh, infra/deploy-site.sh,
infra/reconfigure-*.sh, infra/moral-atlas.yaml, infra/README.md and this script:
they describe a thing that no longer exists.
AFTER
