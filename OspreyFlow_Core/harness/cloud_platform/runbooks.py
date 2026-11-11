"""The `cloud-platform` profile's two runbooks, rendered for the deployment (ADR-148 Amendment
5): `INSTALL.md`, the manual install, and `DECOMMISSION.md`, which removes everything the deployment
made. Each is written for the client's team to run end to end, in bash, from the release's
`OspreyFlow_Core` folder, with the deployment's own names already in it.

Every command is in a fenced block, and the blocks are the runbook: run in order, in one bash
shell, and stopped at the first command that fails. A block fenced `bash` runs wherever the
runbook is followed; a block fenced `bash platform` only on the client's platform (the Terraform
pull requests, the registry's sign-in and the AWS accounts' own commands), for which a rehearsal on
a local cluster supplies its stand-in instead (the files the platform's blocks would write) and
says so. `command_blocks` reads them back, so a rehearsal runs the text the client's team reads.
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
from schemas.deployment import OspreyConfig, generated_folder

RELEASE = "ospreyflow"
CHART = "deploy/helm/ospreyflow"
RENDER = '"$PY" -m harness.render --config "$CONFIG"'

_FENCE = re.compile(r"^```bash( platform)?\n(.*?)^```\n", re.S | re.M)


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
    rollouts = "\n".join(
        f'kubectl -n "$NS" rollout status {w["kind"].lower()}/{w["name"]} --timeout=900s'
        for w in values["workloads"]
    )
    hosts = [r["host"] for r in values["ingress"]["rules"]]
    glass = next(r["host"] for r in values["ingress"]["rules"] if r["service"] == "workspace")
    host = cp.registry.split("/")[0]
    return f"""# Install: OspreyFlow in `{cp.namespace}` ({cp.shape} shape)

Rendered for this deployment, before its images are pushed, by `PYTHONPATH=.:packages
.venv/bin/python -m harness.render --config osprey.yaml --allow-unpinned` (ADR-148 Amendment 5); step 4
renders it again, pinned.

**What it needs.** The release's `OspreyFlow_Core` folder, at the release's tag: `ospreyflow images
push` builds our images from its Dockerfiles and source, so it must be the release these files were
rendered from (`git describe --tags` names it). In it: the release's environment (`uv sync
--frozen`, which makes `.venv`), the `ospreyflow` command (`.venv/bin/ospreyflow`, or the release's
own install of it), and the deployment's `osprey.yaml` (or `CONFIG` naming it). Then `kubectl`
pointed at the namespace, `helm` 3.16 or later, Docker with `buildx`, the AWS command line (v2)
signed in to the namespace's account, and bash. Run each block in order, in one bash shell, from
that folder. If a command fails, stop there: put right what it says, then run its block again.
{_bare_connector_hosts(cp.connector_hosts)}
## 1. The settings and the namespace

{_settings(config, platform)}
```bash
command -v ospreyflow >/dev/null || {{ echo "no ospreyflow command: put .venv/bin on PATH"; false; }}
docker buildx version >/dev/null || {{ echo "Docker's buildx is needed to build the images"; false; }}
kubectl auth can-i create statefulsets -n "$NS"
kubectl auth can-i create persistentvolumeclaims -n "$NS"
```

## 2. The namespace's resources (the platform team's pull request)

Copy `$FOLDER/terraform/` into the namespace's folder in the environments repository and raise the
pull request. Once it is applied, the namespace holds the managed stores' Secrets, our Secret and the
service account the Conduit reads S3 as.

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

## 6. Sign-in and the first administrator

Sets the Conduit's client secret on its clients, its service account's roles and the realm's
sign-in settings, once Keycloak answers (P10 replaces this with the client's own sign-in), then makes
the first administrator, `admin`, and prints the one-time code they sign in with once.

```bash
"$PY" -m harness.cloud_platform.identity "$FOLDER/values.yaml"
```

## 7. Check

The doors answer through the platform's ingress ({", ".join(hosts)}).

```bash
curl -fsS ${{OSPREY_CURL_OPTS:-}} "https://{glass}/healthz" >/dev/null && echo "the Glass answers"
kubectl -n "$NS" get pods
```
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

**What it needs.** The release's `OspreyFlow_Core` folder with its environment (`.venv`) and this
deployment's rendered folder, `kubectl` pointed at the namespace, `helm`, the AWS command line (v2)
signed in to the namespace's account, and bash. Run each block in order, in one bash shell, from
that folder; if a command fails, stop there.

## 1. The settings

{_settings(config, platform)}
```bash
export PREFIX="$(kubectl -n "$NS" get secret {secrets.s3.name} -o jsonpath='{{.data.{secrets.s3.keys["prefix"]}}}' | base64 -d)"
test -n "$PREFIX" || {{ echo "no bucket prefix in {secrets.s3.name}"; false; }}
cp "$FOLDER/values.yaml" "$WORK/values.yaml" && rm -rf "$WORK/terraform" && cp -R "$FOLDER/terraform" "$WORK/terraform"
```

## 2. The last backup

Take it with the deployment's backup command (its backup and restore section, P9's), while the
deployment still runs, to a place **outside this deployment's buckets**, which step 6 empties; give
that place as `LAST_BACKUP`.

```bash
: "${{LAST_BACKUP:?where the last backup was written, outside the buckets this decommission empties}}"
case "$LAST_BACKUP" in "s3://$PREFIX"*) echo "$LAST_BACKUP is in a bucket this decommission empties: copy it elsewhere first"; false;; esac
```

## 3. The workloads

`helm uninstall` removes what the chart made, but keeps every claim: each store's own and the shared
ones (`helm.sh/resource-policy: keep`), which hold the data.

```bash
helm uninstall "$RELEASE" -n "$NS" --wait --timeout 15m || helm status "$RELEASE" -n "$NS" 2>&1 | grep -q 'not found'
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

Remove the deployment's resources (the files from `$FOLDER/terraform/`) from the namespace's folder
in the environments repository and raise the pull request; the folder's other resources are the
platform's and stay.

```bash platform
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
for b in {buckets}; do
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
"""
