# Infrastructure

Enough AWS to collaborate and to demo, and deliberately not more.

The repository is in two halves, so the infrastructure is too:

| | What it is | Where it runs |
|---|---|---|
| **The atlas** | a batch pipeline that spends money on LLM calls and writes a DuckDB file | one EC2 runner, reachable only through SSM |
| **The interface** | static screens plus one JSON payload | S3 behind CloudFront, on a private URL |

One template builds both: [`moral-atlas.yaml`](moral-atlas.yaml).

```bash
SITE_PASSWORD='pick-something' ./infra/deploy.sh
./infra/deploy-site.sh
```

Default region is `ap-southeast-2`; override with `AWS_REGION`.

## Why this shape

**The pipeline is not a service.** `atlas score` is a long batch job holding a
write lock on a file, not a request handler. Containers and autoscaling would
add moving parts to something that wants exactly one machine, so it gets one
machine — and the thing that actually matters, the database file, lives on a
separate EBS volume that survives the instance being replaced.

**DuckDB means one writer.** A DuckDB file admits a single read-write process
at a time; readers cannot attach while a sweep holds it. That is fine for how
this work happens, but it is the reason the design is the way it is:

- The runner is the only writer. Two people should not start sweeps at once —
  the second gets a lock error, not corruption, but it is still a wasted run.
- Colleagues read a **copy**, not the live file. `atlas-snapshot` puts one in
  S3; pull it down and point your own checkout at it.
- The demo site never touches the database. It reads `/api/session.json`,
  which the runner publishes. That seam is already in
  `design/INTERFACE-CONTRACT.md`, so this only makes the contract real.

If several people ever need to write concurrently, that is the moment to move
to a server database — not before.

**No SSH, no bastion, no open port.** The runner's security group has no
ingress rules at all. Shell access is SSM Session Manager, which dials out.

**No NAT gateway.** The runner sits in a public subnet with a public IP and no
way in. That is ~$32/month cheaper than a private subnet with NAT, and no less
closed.

## What gets built

- **VPC** — one public subnet, internet gateway, egress-only security group.
- **EC2 runner** — `t4g.small` (Graviton), Amazon Linux 2023, Python 3.11, the
  project installed into a venv at `/opt/atlas/app`.
- **EBS data volume** — encrypted gp3, mounted at `/opt/atlas/data`, with
  `data/` in the checkout symlinked to it. `DeletionPolicy: Retain`, because a
  UserData edit replaces the instance and the DuckDB file must not go with it.
- **S3 data bucket** — versioned, for database snapshots and bank exports.
- **S3 site bucket + CloudFront** — private bucket, origin access control, the
  bucket reachable only through the distribution.
- **Secrets Manager** — one JSON secret with the API keys.
- **CloudWatch** — a log group for bootstrap and snapshot logs, and an alarm
  that stops the runner after 4 idle hours.

## First deploy

```bash
SITE_PASSWORD='pick-something' ./infra/deploy.sh
```

Then fill in the credentials. They are not template parameters on purpose:
parameter values persist in stack history and in every `describe-stacks` call.

```bash
aws secretsmanager put-secret-value \
  --secret-id moral-atlas/dev/config \
  --secret-string '{
    "ANTHROPIC_API_KEY": "sk-ant-...",
    "TMDB_READ_TOKEN": "...",
    "OPENSUBTITLES_API_KEY": "",
    "OPENSUBTITLES_USERNAME": "",
    "OPENSUBTITLES_PASSWORD": "",
    "github_token": "ghp_..."
  }'
```

`github_token` is only used to clone a private repository on first boot. Leave
it empty and the machine still comes up fully prepared — clone by hand inside
the session instead.

Pick the keys up on the runner:

```bash
aws ssm start-session --target <RunnerInstanceId>
sudo su - ec2-user          # the project lives here, not under ssm-user
atlas-refresh-env           # rewrites .env from the secret
atlas init && atlas status
```

## Working on it

```bash
aws ssm start-session --target <RunnerInstanceId>
sudo su - ec2-user
```

You land in `/opt/atlas/app` with the venv on `PATH`. Long sweeps outlive the
session if you start them under `tmux` — an SSM session that drops otherwise
takes the run with it.

Three helpers are installed:

| Command | What it does |
|---|---|
| `atlas-refresh-env` | rewrite `.env` from Secrets Manager; run after rotating a key |
| `atlas-snapshot` | copy the DuckDB file and `bank.jsonl` to S3 (also nightly at 03:00 UTC) |
| `atlas-publish <file.json>` | push a session payload to `/api/session.json` and invalidate the edge cache |
| `atlas-update [branch]` | pull, reinstall, re-init — what CI runs after a push |

`atlas-update` discards local changes. The runner is a deployment target, not
somewhere to edit code.

**Take a snapshot when no sweep is running.** Copying the file mid-write gives
a torn snapshot that looks fine until the day you need it.

### Getting the data onto your own machine

```bash
# The bucket name is generated by CloudFormation, so read it from the stack
# rather than guessing — it is not moral-atlas-dev-data-<account>.
BUCKET=$(aws cloudformation describe-stacks --stack-name moral-atlas-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`DataBucketName`].OutputValue' --output text)

aws s3 cp "s3://$BUCKET/latest/atlas.duckdb" data/atlas.duckdb

# Pushing local work up is the same command reversed:
aws s3 cp data/atlas.duckdb "s3://$BUCKET/latest/atlas.duckdb"
```

That is the whole local setup for someone picking up the front end or the
analysis — real scores, no API key, no sweep of their own.

## Publishing the interface

```bash
./infra/deploy-site.sh                    # publishes design/
SITE_DIR=web/dist ./infra/deploy-site.sh  # once a real front end exists
```

`/api/session.json` is seeded from `design/fixtures/session.json` and served
uncached, so the runner can overwrite it with real output at any time and the
next reload picks it up. That behaviour is the contract's "swap the fixture for
a live endpoint later", already wired.

## Deploying from a GitHub push

`.github/workflows/deploy.yml` runs on every push to `main`. It does not blindly
redeploy everything:

| Changed | What runs |
|---|---|
| anything | tests, then publish the site |
| `infra/**` | `deploy.sh` as well — the stack itself |
| `src/**`, `seeds/**`, `pyproject.toml` | `atlas-update` on the runner, over SSM |

That split matters: a template change can replace the EC2 instance, and doing
that because someone edited a design file would be a bad afternoon. Run the
stack deploy manually any time from the Actions tab — **Run workflow → Deploy
the CloudFormation stack**.

### Wiring it up, once

There is no AWS access key involved. GitHub presents a short-lived OIDC token
naming the repository, the branch and the run; AWS trades it for temporary
credentials. The trust policy is pinned to `main` of the repo named in the
`GitHubRepo` parameter, so a push to another branch — or a pull request from a
fork — cannot reach the account.

```bash
./infra/deploy.sh                    # creates the OIDC provider and the role

gh variable set AWS_DEPLOY_ROLE \
  --body "$(aws cloudformation describe-stacks --stack-name moral-atlas-dev \
    --query "Stacks[0].Outputs[?OutputKey=='DeployRoleArn'].OutputValue" \
    --output text)"
```

A repository **variable**, not a secret — it is an ARN, and pretending it is
confidential only makes it harder to debug.

The OIDC provider is account-wide and can exist only once. If another stack in
the account already created it, deploy with
`CreateGitHubOidcProvider=false`.

### The part to think about before you turn it on

The `manage-stack` policy on the deploy role is broad, and there is no honest
way to make it narrow: the template creates IAM roles, so whatever deploys it
must be able to create IAM roles, which is close to administrator. **Write
access to `main` is therefore write access to this AWS account.** Protect the
branch — require a pull request, and do not let the workflow file be edited
without review, since a workflow can run whatever it likes with that role.

If that trade is not worth it, delete the `manage-stack` policy from the
template and the `stack` job from the workflow. Run `./infra/deploy.sh` by hand
and let CI publish only the site, which needs nothing but S3 and CloudFront.

## Cost

Rough, `ap-southeast-2`, and worth checking against the calculator rather than
trusting a number in a README:

| | Idle (runner stopped) | Runner always on |
|---|---|---|
| EC2 `t4g.small` | $0 | ~$15 |
| EBS, 20 GB root + 20 GB data | ~$4 | ~$4 |
| Secrets Manager | ~$0.40 | ~$0.40 |
| S3 + CloudFront at demo traffic | cents | cents |
| **Total / month** | **~$5** | **~$20** |

The idle alarm stops the runner after 4 consecutive hours below 3% CPU, so the
common failure — someone demos on a Friday and remembers in March — costs
almost nothing. Restart it with `aws ec2 start-instances`; the data volume is
untouched either way. Set `IdleShutdownHours=0` to disable.

LLM calls are not in this table and will dominate it. `atlas` prints a running
cost estimate.

## Things worth knowing before you rely on them

**Basic auth on the site is a doormat, not a lock.** The credential is compiled
into the CloudFront function, so anyone with CloudFront read access in the
account can read it, and it is visible in the console. It keeps unfinished work
off search engines and out of casual reach. It is not a security boundary, and
nothing sensitive should go behind it on the strength of it. `SITE_AUTH=false`
turns it off if the demo is meant to be open.

**Deleting the stack does not delete the data.** The data bucket and the EBS
volume are both `Retain`. That is deliberate — and it means a re-deploy after
a delete leaves orphans behind that you have to clean up by hand.

**The runner is a shared machine, not a dev environment each.** One checkout,
one database file, one writer. It is the right size for two or three people
coordinating; it is not a build farm.

## Not included, on purpose

- **A custom domain.** The CloudFront URL works today. A domain needs an ACM
  certificate in `us-east-1` and a hosted zone — add `Aliases` and
  `ViewerCertificate` when there is a name worth using.
- **CI/CD.** `deploy-site.sh` from a laptop is honest at this size.
- **An API server.** Nothing needs one yet: the interface is a pure function of
  one payload, and a static file serves it. When `session.json` has to be built
  per pair of users, that is a Lambda with a Function URL, not a rewrite.
- **Multi-AZ anything.** This is a demo and a workbench. An hour of downtime
  costs a conversation, not money.
