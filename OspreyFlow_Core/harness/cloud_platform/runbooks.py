"""The `cloud-platform` profile's two runbooks, rendered for the deployment (ADR-148 Amendment
5): `INSTALL.md`, the manual install, and `DECOMMISSION.md`, which removes everything the deployment
made. Each is written for the client's team to run end to end, in bash, from the release's
`OspreyFlow_Core` folder, with the deployment's own names already in it.

Every command is in a fenced block, and the blocks are the runbook: run in order, in one bash
shell, and stopped at the first command that fails. A block fenced `bash` runs wherever the
runbook is followed; a block fenced `bash platform` only on the client's platform (the Terraform
pull requests, the registry's sign-in and the AWS accounts' own commands), for which a rehearsal on
a local cluster supplies its stand-in instead (the files the platform's blocks would write) and
says so. A block fenced `bash later` is in no sequence (R1): the way back in when no administrator
is left, and the backups' removal when their retention ends, each run only when its words say. `command_blocks` reads them back, so a rehearsal runs the text the client's team reads.
Every command runs with the rights a namespace's tenant has: nothing cluster-wide is listed or
changed (the disks are the platform team's command), and every AWS call names its region.
"""

# ruff: noqa: E501 - the templates below are the runbooks' own text: each line is a command or a
# sentence as the operator reads it, not wrapped to this file's width.

from __future__ import annotations

import re
from typing import Any

from harness.cloud_platform.decommission_check import DISK_NAMESPACE_TAG, KINDS
from harness.cloud_platform.settings import PlatformSettings
from harness.cloud_platform.terraform import BUCKETS, ecr_repositories
from harness.cloud_platform_backups import BUCKET_SUFFIX, KEPT_AT_DECOMMISSION
from schemas.deployment import OspreyConfig, generated_folder

RELEASE = "ospreyflow"
CHART = "deploy/helm/ospreyflow"
RENDER = '"$PY" -m harness.render --config "$CONFIG"'

_FENCE = re.compile(r"^```bash( platform)?\n(.*?)^```\n", re.S | re.M)


#: The managed PostgreSQL's least `max_connections` (R1 on kind, finding 15). The Conduit's figures are
#: ADR-114 Amendment 43's (lane/admin-pg: `harness.profiles`, where a running Conduit's own pools hold
#: them; `test_cloud_platform_poc.py` holds these equal to them once it merges): one Conduit's pools at
#: their `max_size`, and the one connection each running load holds outside them.
CONDUIT_POOL_CEILING = 220
RUNNING_LOADS_ALLOWED = 20
GATEWAY_POOL_MAX = 10
OPERATOR_RESERVE = 20
#: Two Conduits (an update's old and new pods, side by side), the worker (which opens the same stores),
#: the gateway, and an operator's reserve. No Keycloak or Superset on this profile.
POSTGRES_MAX_CONNECTIONS = (
    3 * (CONDUIT_POOL_CEILING + RUNNING_LOADS_ALLOWED) + GATEWAY_POOL_MAX + OPERATOR_RESERVE
)


def command_blocks(text: str, *, on_the_platform: bool) -> list[str]:
    """A runbook's blocks in order: every `bash` block, and the `bash platform` blocks only when
    the runbook is followed on the client's platform."""
    return [body for platform, body in _FENCE.findall(text) if on_the_platform or not platform]


def _settings(config: OspreyConfig, platform: PlatformSettings) -> str:
    cp = config.cloud_platform
    assert cp is not None and cp.namespace is not None
    folder = f"deploy/generated/{generated_folder(config)}"
    return f"""```bash
export NS={cp.namespace} RELEASE={RELEASE} FOLDER={folder} CHART={CHART} REGION={platform.aws_region}
export CONFIG="${{CONFIG:-osprey.yaml}}" PY="${{PY:-.venv/bin/python}}" PYTHONPATH=.:packages
export WORK="${{TMPDIR:-/tmp}}/ospreyflow-$NS" && mkdir -p "$WORK"
test -n "$BASH_VERSION" || {{ echo "run these blocks in bash"; false; }}
test -x "$PY" || {{ echo "no $PY: make the release's environment first (uv sync --frozen)"; false; }}
command -v kubectl >/dev/null && command -v helm >/dev/null || {{ echo "kubectl and helm are needed"; false; }}
test "$(kubectl config view --minify -o jsonpath='{{..namespace}}')" = "$NS" \\
  || {{ echo "kubectl's context is not the namespace $NS: kubectl config set-context --current --namespace=$NS"; false; }}
```
"""


def _bare_connector_hosts(entries: list[str]) -> str:
    """The render's warning, in words, for each connector host named without a port (ADR-148
    Amendment 5 point 21): it is reached on 443 alone."""
    bare = [e for e in entries if ":" not in e]
    if not bare:
        return ""
    named = ", ".join(f"`{e}`" for e in bare)
    verb, them = ("is", "it") if len(bare) == 1 else ("are", "them")
    return f"""
**Connector hosts reached on 443 only.** {named} {verb} named in `cloud_platform.connector_hosts`
without a port, so the namespace reaches {them} on 443 alone. An API connection over HTTPS needs
nothing more; a SQL connection to one times out until its port is named there (`{bare[0]}:5432`)
and the deployment is rendered again.
"""


def render_install(config: OspreyConfig, platform: PlatformSettings, values: dict[str, Any]) -> str:
    cp = config.cloud_platform
    assert cp is not None and cp.namespace is not None and cp.registry is not None
    secrets = platform.secrets
    theirs = " ".join(s.name for s in (secrets.postgres, secrets.redis, secrets.s3))
    if cp.tls_secret:  # the certificate the platform's team makes for the deployment's name (R1)
        theirs += f" {cp.tls_secret}"
    rollouts = "\n".join(
        f'kubectl -n "$NS" rollout status {w["kind"].lower()}/{w["name"]} --timeout=900s'
        for w in values["workloads"]
    )
    hosts = [r["host"] for r in values["ingress"]["rules"]]
    glass = next(r["host"] for r in values["ingress"]["rules"] if r["service"] == "workspace")
    host = cp.registry.split("/")[0]
    claims = cp.claims
    assert claims is not None  # the render refuses this profile without them
    return f"""# Install: OspreyFlow in `{cp.namespace}` ({cp.shape} shape)

Rendered for this deployment, before its images are pushed, by `PYTHONPATH=.:packages
.venv/bin/python -m harness.render --config osprey.yaml --allow-unpinned` (ADR-148 Amendment 5); step 4
renders it again, pinned.

**What it needs.** The release's `OspreyFlow_Core` folder, at the release's tag: `ospreyflow images
push` builds our images from its Dockerfiles and source, so it must be the release these files were
rendered from (`git describe --tags` names it). In it: the release's environment (`uv sync
--frozen`, which makes `.venv`), the `ospreyflow` command (its own package: `uv tool install ./cli`
from that folder puts it in `~/.local/bin`, which must be on `PATH`), and the deployment's `osprey.yaml` (or `CONFIG` naming it). Then `kubectl`
pointed at the namespace, `helm` 3.16 or later, Docker with `buildx`, the AWS command line (v2)
signed in to the namespace's account, and bash. Run each block in order, in one bash shell, from
that folder. If a command fails, stop there: put right what it says, then run its block again.
A block fenced `bash later` is not part of that order: the words before it say when, if ever, it is run.

**Before step 5, from the client's Entra administrator** (ADR-148 Amendment 8; step 6 checks it):
two app registrations in tenant `{claims.tenant_id}`, the Glass (application id `{claims.client_id}`)
and this API (`{claims.api_client_id}`, exposing the scope `{claims.scope}`, which the Glass is
granted), with the claims `cloud_platform.claims` names.

**The managed PostgreSQL** allows a `max_connections` of at least {POSTGRES_MAX_CONNECTIONS}: two Conduits
side by side during an update, the worker, the gateway and a reserve (ADR-114 Amendment 43's figures). RDS
derives it from the instance's memory unless its parameter group sets it (a db.t3.medium gives about 410),
so set it there; with too few, the new Conduit of an update stops at `TooManyConnectionsError`.
{_bare_connector_hosts(cp.connector_hosts)}
## 1. The settings and the namespace

{_settings(config, platform)}
```bash
command -v ospreyflow >/dev/null || {{ echo "no ospreyflow command: uv tool install ./cli, and put ~/.local/bin on PATH"; false; }}
docker buildx version >/dev/null || {{ echo "Docker's buildx is needed to build the images"; false; }}
kubectl auth can-i create statefulsets -n "$NS"
kubectl auth can-i create persistentvolumeclaims -n "$NS"
```

## 2. The namespace's resources (the platform team's pull request)

Copy `$FOLDER/terraform/` into the namespace's folder in the environments repository and raise the
pull request. Once it is applied, the namespace holds the managed stores' Secrets, our Secret and the
service account the Conduit reads S3 as{f", and the platform's team has made the certificate's Secret, `{cp.tls_secret}`" if cp.tls_secret else ""}.

```bash platform
echo "Raise the pull request with $FOLDER/terraform/, and wait for it to be applied."
```

```bash
for secret in {theirs} {values["secrets"]["name"]}; do
  kubectl -n "$NS" get secret "$secret" -o name
done
kubectl -n "$NS" get serviceaccount {secrets.irsa.service_account} -o name
```

## 3. The images

Render the plan (ours are not in the registry yet, so the values are not pinned), sign in to the
registry, then build ours and copy the others, each by its digest, into `{cp.registry}`.

```bash
{RENDER} --allow-unpinned
```

```bash platform
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin {host}
```

```bash
ospreyflow images push --registry "{cp.registry}" --from "$FOLDER"
```

## 4. The values, pinned

Every image now by the digest the registry holds for it. The third-party ones keep the digest the
plan copied, even if a tag has moved since; delete `$FOLDER/images.yaml` before step 3 to take a
newer one.

```bash
{RENDER}
```

## 5. The deployment

```bash
helm upgrade --install "$RELEASE" "$CHART" -n "$NS" -f "$FOLDER/values.yaml" --timeout 30m
{rollouts}
```

## 6. Sign-in: Entra ID and the first administrators

People sign in with the client's own Entra ID (ADR-148 Amendment 8): there is no sign-in service of
ours to set up, only the two app registrations *What it needs* asks for, in tenant
`{claims.tenant_id}`. The first administrators ({", ".join(claims.first_administrators)}) were given the Admin role when the
Conduit first started; they give everyone else their roles in Admin › People. Check the Conduit reads
Entra's settings:

```bash
kubectl -n "$NS" exec deploy/api -- printenv OSPREY_IDENTITY_PROVIDER OIDC_ISSUER
```

**If no administrator is left** (nobody enabled who has signed in can manage people): add the Entra
object id of a person who is not disabled here to `cloud_platform.claims.first_administrators` in
`osprey.yaml`, render again (step 4) and install the new values: the list is in the deployment's
ConfigMap, so a restart alone would read the old one, and the install restarts the Conduit. At start, and only when nobody can
manage people, the Conduit adds the Admin role to each one named there, and audits it
(`grant_first_administrator`). While anyone can manage people, it changes nobody's roles.

```bash later
{RENDER}
helm upgrade --install "$RELEASE" "$CHART" -n "$NS" -f "$FOLDER/values.yaml" --timeout 30m
kubectl -n "$NS" rollout status deploy/api --timeout 10m
```

## 7. Check

The doors answer through the platform's ingress ({", ".join(hosts)}): `/healthz` is the Conduit's,
answered through the Glass. `OSPREY_CURL_OPTS` is curl's options for that door, if it needs any:
where the ingress's certificate is signed by a CA your machine does not trust, export
`OSPREY_CURL_OPTS="--cacert <that CA's file>"` first.

```bash
curl -fsS ${{OSPREY_CURL_OPTS:-}} "https://{glass}/healthz" >/dev/null && echo "the Glass answers"
kubectl -n "$NS" get pods
```

## 8. Against the client's real tenant (once, with the client's Entra administrator)

**This section is not a block to run: each item needs a person at a browser.** Our own acceptance
signed in through a stand-in for Entra ID, which can show how the Conduit treats a token but nothing
about how tenant `{claims.tenant_id}` is set up. Only the real tenant shows these. If any item fails,
stop and raise it with the client's Entra administrator before anyone else is told the service is ready.

1. **Token version.** With `token_version` 2.0, the API registration's manifest has
   `requestedAccessTokenVersion` set to 2. Without it, Entra issues v1.0 tokens with another issuer,
   and every sign-in is refused.
2. **The first administrator.** One of {", ".join(claims.first_administrators)} signs in at
   `https://{glass}`. Admin › People lists them with Admin, and their clearance (for example
   OFFICIAL-SENSITIVE), unit and handling codes are the ones their groups give. If they are not, the
   claims set in the registration (`claims_mapping_policy`, optional claims) do not send what
   `cloud_platform.claims` names.
3. **A person given no role.** A member of the tenant whom no administrator has given a role signs in,
   is listed in Admin › People with no role, and sees no case and no Admin.
4. **Who may sign in at all.** If the Glass's enterprise application has *Assignment required*, a person
   who is not assigned is refused by Entra itself (AADSTS50105) and never reaches the deployment. If it
   does not, every member of the tenant can sign in, with no role until given one: confirm which the
   client wants.
5. **A guest.** A guest (B2B) account signs in and is refused.
6. **Many groups.** A person in more than 200 groups is refused in words, because Entra then leaves the
   groups out of the token. Limit the claim to the groups assigned to the application.
7. **Keys.** Entra rolls its signing key unannounced. The Conduit fetches the tenant's keys again
   within five minutes. A sign-in still refused for an unknown key after that is a fault: report it.
"""


def render_decommission(
    config: OspreyConfig, platform: PlatformSettings, values: dict[str, Any]
) -> str:
    cp = config.cloud_platform
    assert cp is not None and cp.namespace is not None and cp.registry is not None
    secrets = platform.secrets
    own = " ".join(f"ospreyflow-{c['name']}" for c in values["storage"].get("claims", []))
    buckets = " ".join(BUCKETS)
    repositories = " ".join(ecr_repositories(values, cp.registry))
    kinds = " ".join(KINDS)
    return f"""# Decommission: OspreyFlow in `{cp.namespace}`

Rendered for this deployment by `PYTHONPATH=.:packages .venv/bin/python -m harness.render` (ADR-148
Amendment 5). Removes everything the deployment made: its workloads, its claims and their disks,
its Secrets, its buckets and images, and the namespace's resources. **It deletes the deployment's
data for good**: step 2 takes the last backup first. The namespace itself, and every other resource
in it, is the platform team's and stays.

**Kept: the backups (retention).** The backups bucket (`<prefix>{BUCKET_SUFFIX}`) and its KMS key
(`alias/{cp.namespace}-backups`) are the one exception (ADR-148 Amendment 7): kept, with the last
backup in them, until the retention you agree ends; section 9 removes them then.

**What it needs.** The release's `OspreyFlow_Core` folder with its environment (`.venv`) and this
deployment's rendered folder, `kubectl` pointed at the namespace, `helm`, the AWS command line (v2)
signed in to the namespace's account, and bash. Run each block in order, in one bash shell, from
that folder; if a command fails, stop there.
A block fenced `bash later` is not part of that order: the words before it say when, if ever, it is run.

## 1. The settings

{_settings(config, platform)}
```bash
export PREFIX="$(kubectl -n "$NS" get secret {secrets.s3.name} -o jsonpath='{{.data.{secrets.s3.keys["prefix"]}}}' | base64 -d)"
test -n "$PREFIX" || {{ echo "no bucket prefix in {secrets.s3.name}"; false; }}
cp "$FOLDER/values.yaml" "$WORK/values.yaml" && rm -rf "$WORK/terraform" && cp -R "$FOLDER/terraform" "$WORK/terraform"
```

## 2. The last backup

Taken while the deployment still runs, by its own two backup runs for one slot (the set is named by
the slot), into the backups bucket, which this decommission keeps. Wait for both; the set is
finished when its `manifest.json` is there.

```bash
S=$(( $(date +%s) / 60 ))
kubectl -n "$NS" create job "ospreyflow-backup-$S" --from=cronjob/ospreyflow-backup
if kubectl -n "$NS" get cronjob ospreyflow-backup-claims >/dev/null 2>&1; then
  kubectl -n "$NS" create job "ospreyflow-backup-claims-$S" --from=cronjob/ospreyflow-backup-claims
fi
kubectl -n "$NS" wait --for=jsonpath='{{.status.conditions[0].status}}'=True "job/ospreyflow-backup-$S" --timeout=6h
kubectl -n "$NS" get job "ospreyflow-backup-$S" -o jsonpath='{{.status.succeeded}}' | grep -qx 1 \\
  || {{ echo "the last backup did not finish: read its log (kubectl -n $NS logs job/ospreyflow-backup-$S)"; false; }}
export LAST_BACKUP="s3://${{PREFIX}}{BUCKET_SUFFIX}/sets/$("$PY" -c 'import datetime, sys; print(datetime.datetime.fromtimestamp(int(sys.argv[1]) * 60, datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))' "$S")/"
echo "the last backup: $LAST_BACKUP"
```

## 3. The workloads

`helm uninstall` removes what the chart made, but keeps every claim: each store's own and the shared
ones (`helm.sh/resource-policy: keep`), which hold the data. A restore's Jobs were applied from `helm
template`, not installed, so they stay: their finished pods still name the claims, and Kubernetes keeps a
claim while any pod names it (`kubernetes.io/pvc-protection`), so step 4 would wait and fail. They are
removed here, their pods with them.

```bash
helm uninstall "$RELEASE" -n "$NS" --wait --timeout 15m || helm status "$RELEASE" -n "$NS" 2>&1 | grep -q 'not found'
kubectl -n "$NS" delete job -l app.kubernetes.io/instance="$RELEASE" --cascade=foreground --ignore-not-found --wait --timeout=10m
```

## 4. The claims

The stores' claims carry the release's label (their StatefulSets' selectors); the shared ones are
removed by name. Their disks go with them on a class that deletes them (step 8 checks).

```bash
kubectl -n "$NS" delete pvc -l app.kubernetes.io/instance="$RELEASE" --wait --timeout=10m
kubectl -n "$NS" delete pvc ospreyflow-shared {own} --ignore-not-found --wait --timeout=10m
```

## 5. Our Secret

```bash
kubectl -n "$NS" delete secret {values["secrets"]["name"]} --ignore-not-found
```

## 6. The buckets and the images (the account's own commands)

Each bucket emptied of every object version and every delete marker (`media` keeps versions), five
hundred keys a call (the listing sliced to five hundred, since `--max-items` counts the versions
alone), then each repository emptied of its images, a hundred a call, the tagged ones (buildx's
indexes) before the untagged ones they hold: the namespace's Terraform cannot remove either while it
holds anything. Each block stops on a listing that fails, a call that answers with per-key errors or
failures, and a listing that comes back the same after a delete, and ends on whether it stopped.

```bash platform
failed=
for b in {buckets}; do
  for kind in Versions DeleteMarkers; do
    : > "$WORK/versions.last.json"
    while :; do
      if ! aws s3api list-object-versions --region "$REGION" --bucket "$PREFIX$b" --max-items 500 --output json \\
          --query "{{Objects: $kind[:500].{{Key: Key, VersionId: VersionId}}}}" > "$WORK/versions.json"; then
        echo "listing $PREFIX$b's $kind failed: stopped"; failed=1; break 3
      fi
      grep -q '"Key"' "$WORK/versions.json" || break
      if cmp -s "$WORK/versions.json" "$WORK/versions.last.json"; then
        echo "$PREFIX$b's $kind are the same after a delete: stopped"; failed=1; break 3
      fi
      cp "$WORK/versions.json" "$WORK/versions.last.json"
      if ! errors=$(aws s3api delete-objects --region "$REGION" --bucket "$PREFIX$b" --delete "file://$WORK/versions.json" \\
          --query 'length(Errors || `[]`)' --output text); then
        echo "deleting from $PREFIX$b failed: stopped"; failed=1; break 3
      fi
      [ "$errors" = "0" ] || {{ echo "deleting from $PREFIX$b: $errors key(s) refused: stopped"; failed=1; break 3; }}
    done
  done
done
test -z "$failed"
```

```bash platform
failed=
for repository in {repositories}; do
  for status in TAGGED UNTAGGED; do
    last=
    while :; do
      if ! ids=$(aws ecr list-images --region "$REGION" --repository-name "$repository" --filter "tagStatus=$status" \\
          --max-items 100 --query 'imageIds[*]' --output json); then
        echo "listing $repository's images failed: stopped"; failed=1; break 3
      fi
      [ "$ids" = "[]" ] && break
      [ "$ids" = "$last" ] && {{ echo "$repository's images are the same after a delete: stopped"; failed=1; break 3; }}
      last=$ids
      if ! refused=$(aws ecr batch-delete-image --region "$REGION" --repository-name "$repository" --image-ids "$ids" \\
          --query 'length(failures)' --output text); then
        echo "deleting $repository's images failed: stopped"; failed=1; break 3
      fi
      [ "$refused" = "0" ] || {{ echo "deleting $repository's images: $refused refused: stopped"; failed=1; break 3; }}
    done
  done
done
test -z "$failed"
```

## 7. The namespace's resources (the platform team's pull request)

First the kept bucket's lifecycle rule is set to the retention you agree, so the deployment's own
35-day rule cannot expire the sets this decommission keeps; then, in the namespace's folder, the
backups bucket and its key are taken out of the state, so the removal keeps them (`prevent_destroy`
holds only while their file is there). Give the retention, in days, as `BACKUP_RETENTION_DAYS`. Then remove the
deployment's resources (the files from `$FOLDER/terraform/`) from the namespace's folder in the
environments repository and raise the pull request; the folder's other resources are the
platform's and stay.

```bash platform
: "${{BACKUP_RETENTION_DAYS:?the retention you agree for the kept backups, in days}}"
printf '{{"Rules": [{{"ID": "abort-unfinished-uploads", "Status": "Enabled", "Filter": {{"Prefix": ""}}, "AbortIncompleteMultipartUpload": {{"DaysAfterInitiation": 7}}}}, {{"ID": "retained-sets", "Status": "Enabled", "Filter": {{"Prefix": "sets/"}}, "Expiration": {{"Days": %d}}, "NoncurrentVersionExpiration": {{"NoncurrentDays": 7}}}}, {{"ID": "remove-expired-markers", "Status": "Enabled", "Filter": {{"Prefix": "sets/"}}, "Expiration": {{"ExpiredObjectDeleteMarker": true}}}}]}}' \\
  "$BACKUP_RETENTION_DAYS" > "$WORK/retention.json"
aws s3api put-bucket-lifecycle-configuration --region "$REGION" --bucket "${{PREFIX}}{BUCKET_SUFFIX}" \\
  --lifecycle-configuration "file://$WORK/retention.json"
aws s3api get-bucket-lifecycle-configuration --region "$REGION" --bucket "${{PREFIX}}{BUCKET_SUFFIX}" | grep -q retained-sets
M="${{TF_MODULE:+$TF_MODULE.}}"   # the deployment's module in the environments repository, if any
removed=0
for kept in {" ".join(KEPT_AT_DECOMMISSION)}; do tofu state rm "$M$kept" >/dev/null 2>&1 && removed=$((removed + 1)); done
test "$removed" -gt 0 || {{ echo "no kept resource was in the state (is TF_MODULE right?): stop"; false; }}
tofu state list | grep -E '(^|[.])({"|".join(re.escape(k) for k in KEPT_AT_DECOMMISSION)})$' && {{ echo "a kept resource is still in the state: stop"; false; }}
echo "Raise the pull request removing $FOLDER/terraform/'s files, and wait for it to be applied."
```

## 8. Check that nothing is left

Lists the namespace (each kind the deployment makes), the disks made for its claims, the Terraform
state and each of the deployment's buckets by name, and names anything of the deployment's still
there.

- `STATE`: the output of `tofu state list` in the namespace's folder (the platform team's pipeline
  prints it), saved to a file; give `TF_MODULE` too if the environments repository puts the
  deployment's files in a module of their own.
- The disks are in the cluster's account: the platform team runs that line with its own credentials
  and names its account as `CLUSTER_ACCOUNT` (the check refuses a listing from any other account or
  region), or gives its output as `DISKS` in the form this block writes (`describe-volumes`' answer
  with the `Account` and `Region` it was asked in; the check refuses any other).

```bash platform
: "${{STATE:?the output of tofu state list in the namespace folder, saved to a file}}"
cp "$STATE" "$WORK/state.txt"
: > "$WORK/buckets.txt" && failed=
for b in {buckets} {BUCKET_SUFFIX}; do
  if out=$(aws s3api head-bucket --region "$REGION" --bucket "$PREFIX$b" 2>&1); then echo "$PREFIX$b" >> "$WORK/buckets.txt"
  elif echo "$out" | grep -q -e '404' -e 'Not Found'; then :
  else echo "$PREFIX$b could not be checked: $out"; failed=1; fi
done
test -z "$failed"
```

```bash platform
: "${{CLUSTER_ACCOUNT:?the AWS account that holds the cluster disks}}"
if [ -n "${{DISKS:-}}" ]; then cp "$DISKS" "$WORK/disks.json"; else
  aws ec2 describe-volumes --region "$REGION" --filters "Name=tag:{DISK_NAMESPACE_TAG},Values=$NS" --output json > "$WORK/disks-listed.json"
  "$PY" -c 'import json, sys; d = json.load(open(sys.argv[1])); d.update(Account=sys.argv[2], Region=sys.argv[3]); json.dump(d, open(sys.argv[4], "w"))' \\
    "$WORK/disks-listed.json" "$(aws sts get-caller-identity --region "$REGION" --query Account --output text)" "$REGION" "$WORK/disks.json"
fi
```

```bash
for listing in state.txt buckets.txt; do
  test -f "$WORK/$listing" || {{ echo "no $WORK/$listing: step 8's first block (the platform's) writes it"; false; }}
done
objects=()
for kind in {kinds}; do
  if kubectl api-resources -o name | grep -qx "$kind"; then
    kubectl -n "$NS" get "$kind" -o json > "$WORK/objects-$kind.json"
    objects+=(--objects "$WORK/objects-$kind.json")
  fi
done
seen=()
[ -f "$WORK/disks.json" ] && seen+=(--disks "$WORK/disks.json" --disks-account "${{CLUSTER_ACCOUNT:-}}")
[ -f "$WORK/volumes.json" ] && seen+=(--volumes "$WORK/volumes.json")
test "${{#seen[@]}}" -gt 0 || {{ echo "no listing of the disks: give DISKS, or let the platform team run step 8's first block"; false; }}
"$PY" -m harness.cloud_platform.decommission_check --values "$WORK/values.yaml" "${{objects[@]}}" "${{seen[@]}}" \\
  ${{TF_MODULE:+--module "$TF_MODULE"}} --state "$WORK/state.txt" --terraform "$WORK/terraform" \\
  --buckets "$WORK/buckets.txt" --bucket-prefix "$PREFIX"
```

The check names the backups bucket and its key as kept (`kept: the backups (retention)`), never as
left behind, and fails on anything else.

## 9. When the retention ends: the backups bucket, then its key

Your decision, when the retention you agreed ends; the account's administrators run it. The bucket's
policy lets only the deployment's backup roles (removed in step 7) touch its objects, so the policy
goes first; every version of every object is removed (the bucket is versioned), then the bucket.
Only then the key: its own policy refuses everyone its deletion, so that policy is replaced first,
by one keeping the account's administration, and the deletion scheduled (thirty days, cancellable).
A key deleted while the bucket still held a set would leave that set unreadable.

```bash later
B="${{PREFIX}}{BUCKET_SUFFIX}"
aws s3api delete-bucket-policy --region "$REGION" --bucket "$B"
while :; do
  aws s3api list-object-versions --region "$REGION" --bucket "$B" --max-items 500 --output json \\
    --query '{{Objects: [Versions, DeleteMarkers][][].{{Key: Key, VersionId: VersionId}}}}' > "$WORK/versions.json"
  grep -q '"Key"' "$WORK/versions.json" || break
  aws s3api delete-objects --region "$REGION" --bucket "$B" --delete "file://$WORK/versions.json" >/dev/null
done
aws s3api delete-bucket --region "$REGION" --bucket "$B"
ACCOUNT=$(aws sts get-caller-identity --region "$REGION" --query Account --output text)
printf '{{"Version": "2012-10-17", "Statement": [{{"Sid": "Administer", "Effect": "Allow", "Principal": {{"AWS": "arn:aws:iam::%s:root"}}, "Action": "kms:*", "Resource": "*"}}]}}' "$ACCOUNT" > "$WORK/key-policy.json"
KEY=$(aws kms describe-key --region "$REGION" --key-id "alias/{cp.namespace}-backups" --query KeyMetadata.Arn --output text)
aws kms put-key-policy --region "$REGION" --key-id "$KEY" --policy-name default --policy "file://$WORK/key-policy.json"
aws kms schedule-key-deletion --region "$REGION" --key-id "$KEY" --pending-window-in-days 30
aws kms delete-alias --region "$REGION" --alias-name "alias/{cp.namespace}-backups"
```

## 10. Restoring a kept set, after the decommission (the platform team's)

A procedure of the platform team's and the account's administrators, who alone may change the kept
bucket's and key's policies; not yet rehearsed, so rehearse it before relying on it. Its steps:

1. **Into this namespace again:** the kept bucket (`${{PREFIX}}{BUCKET_SUFFIX}`) and alias
   (`alias/{cp.namespace}-backups`) are taken, so the reinstall's Terraform must not make its own:
   before its first apply, the platform team imports them into its state
   (`tofu import aws_s3_bucket.backups "${{PREFIX}}{BUCKET_SUFFIX}"`, `tofu import aws_kms_key.backups <the key's ID>`,
   `tofu import aws_kms_alias.backups alias/{cp.namespace}-backups`, and the bucket's settings likewise); that
   apply then writes the new roles into the kept bucket's and key's policies itself.
2. **Into another namespace:** the administrators replace the kept bucket's policy (`BackupRolesOnly`'s
   `aws:PrincipalArn`) and the key's policy (`UseThroughS3`'s principals) with the new deployment's two
   roles, as its `backups.tf` writes them, and set the new deployment's `ospreyflow-backup-output` Secret's
   `bucket` and `kms_key_arn` to the kept bucket and key, so its runner reads them.
3. The restore itself, by the recovery runbook's cloud-platform section.
"""
