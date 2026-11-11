"""The `cloud-platform` profile's two runbooks, rendered for the deployment (ADR-148 Amendment
5): `INSTALL.md`, the manual install, and `DECOMMISSION.md`, which removes everything the deployment
made. Each is written for the client's team to run end to end, from the release's `OspreyFlow_Core`
folder, with the deployment's own names already in it.

Every command is in a fenced block, and the blocks are the runbook: run in order, in one shell,
and stopped at the first command that fails. A block fenced `sh` runs wherever the runbook is
followed; a block fenced `sh platform` only on the client's platform (the Terraform pull request
and the AWS accounts' own commands), for which a rehearsal on a local cluster runs its stand-in
instead and says so. `command_blocks` reads them back, so the rehearsal runs exactly the text the
client's team reads.
"""

# ruff: noqa: E501 - the templates below are the runbooks' own text: each line is a command or a
# sentence as the operator reads it, not wrapped to this file's width.

from __future__ import annotations

import re
from typing import Any

from harness.cloud_platform.settings import PlatformSettings
from harness.cloud_platform.terraform import BUCKETS, ecr_repositories
from schemas.deployment import OspreyConfig

RELEASE = "ospreyflow"
FOLDER = "deploy/generated/cloud-platform"
CHART = "deploy/helm/ospreyflow"

_FENCE = re.compile(r"^```sh( platform)?\n(.*?)^```\n", re.S | re.M)


def command_blocks(text: str, *, on_the_platform: bool) -> list[str]:
    """A runbook's blocks in order: every `sh` block, and the `sh platform` blocks only when the
    runbook is followed on the client's platform."""
    return [body for platform, body in _FENCE.findall(text) if on_the_platform or not platform]


def _settings(config: OspreyConfig) -> str:
    cp = config.cloud_platform
    assert cp is not None and cp.namespace is not None
    return f"""```sh
export NS={cp.namespace} RELEASE={RELEASE} FOLDER={FOLDER} CHART={CHART}
export PY="${{PY:-.venv/bin/python}}" PYTHONPATH=.:packages
test "$(kubectl config view --minify -o jsonpath='{{..namespace}}')" = "$NS" \\
  || {{ echo "kubectl's context is not the namespace $NS: kubectl config set-context --current --namespace=$NS"; false; }}
```
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
    return f"""# Install: OspreyFlow in `{cp.namespace}` ({cp.shape} shape)

Rendered by `ospreyflow render` for this deployment (ADR-148 Amendment 5). Run each block in order,
from the release's `OspreyFlow_Core` folder, with `kubectl` pointed at the namespace, `helm` 3.16 or
later, Docker (for the images) and the AWS command line signed in to the namespace's account, all in
one shell. If a command fails, stop there: put right what it says, then run its block again.

## 1. The settings and the namespace

{_settings(config)}
```sh
kubectl auth can-i create statefulsets -n "$NS"
kubectl auth can-i create persistentvolumeclaims -n "$NS"
```

## 2. The namespace's resources (the platform team's pull request)

Copy `{FOLDER}/terraform/` into the namespace's folder in the environments repository and raise the
pull request. Once it is applied, the namespace holds the managed stores' Secrets, our Secret and the
service account the Conduit reads S3 as.

```sh platform
echo "Raise the pull request with $FOLDER/terraform/, and wait for it to be applied."
```

```sh
for secret in {theirs} {values["secrets"]["name"]}; do
  kubectl -n "$NS" get secret "$secret" -o name
done
kubectl -n "$NS" get serviceaccount {secrets.irsa.service_account} -o name
```

## 3. The images

Builds ours and copies the others, by digest, into `{cp.registry}`.

```sh
ospreyflow images push --registry "{cp.registry}" --from "$FOLDER"
```

## 4. The deployment

```sh
helm upgrade --install "$RELEASE" "$CHART" -n "$NS" -f "$FOLDER/values.yaml" --timeout 30m
{rollouts}
```

## 5. Sign-in

Sets the Conduit's client secret on its clients, its service account's roles and the realm's
sign-in settings, once Keycloak answers (P10 replaces this with the client's own sign-in).

```sh
"$PY" -m harness.cloud_platform.identity "$FOLDER/values.yaml"
```

## 6. Check

The doors answer through the platform's ingress ({", ".join(hosts)}).

```sh
curl -fsS ${{OSPREY_CURL_OPTS:-}} "https://{glass}/healthz" >/dev/null && echo "the Glass answers"
kubectl -n "$NS" get pods
```
"""


def render_decommission(
    config: OspreyConfig, platform: PlatformSettings, values: dict[str, Any]
) -> str:
    cp = config.cloud_platform
    assert cp is not None and cp.namespace is not None
    secrets = platform.secrets
    own = " ".join(f"ospreyflow-{c['name']}" for c in values["storage"].get("claims", []))
    buckets = " ".join(BUCKETS)
    assert cp.registry is not None
    repositories = " ".join(ecr_repositories(values, cp.registry))
    return f"""# Decommission: OspreyFlow in `{cp.namespace}`

Rendered by `ospreyflow render` for this deployment (ADR-148 Amendment 5). Removes everything the
deployment made: its workloads, its volumes and their disks, its Secret, its buckets and images, and
the namespace's resources. **It deletes the deployment's data for good**: take the last backup first.
The namespace itself is the platform team's and stays. Run each block in order, in one shell, from
the release's `OspreyFlow_Core` folder, as for the install; if a command fails, stop there.

## 1. The settings

{_settings(config)}
```sh
export PREFIX="$(kubectl -n "$NS" get secret {secrets.s3.name} -o jsonpath='{{.data.{secrets.s3.keys["prefix"]}}}' | base64 -d)"
test -n "$PREFIX" || {{ echo "no bucket prefix in {secrets.s3.name}"; false; }}
"$PY" -c "import yaml; yaml.safe_load(open('$FOLDER/values.yaml'))" && cp "$FOLDER/values.yaml" "${{TMPDIR:-/tmp}}/ospreyflow-$NS-values.yaml"
```

## 2. The workloads

`helm uninstall` removes what the chart made, but keeps every volume: each store's own claims and
the shared claims (`helm.sh/resource-policy: keep`), which hold the data.

```sh
helm uninstall "$RELEASE" -n "$NS" --wait --timeout 15m || helm status "$RELEASE" -n "$NS" 2>&1 | grep -q 'not found'
```

## 3. The volumes and their disks

```sh
kubectl -n "$NS" delete pvc -l app.kubernetes.io/instance="$RELEASE" --wait --timeout=10m
kubectl -n "$NS" delete pvc ospreyflow-shared {own} --ignore-not-found --wait --timeout=10m
for i in $(seq 1 60); do
  left=$(kubectl get pv -o jsonpath="{{range .items[?(@.spec.claimRef.namespace=='$NS')]}}{{.metadata.name}} {{end}}")
  [ -z "$left" ] && break
  sleep 10
done
test -z "$left" || {{ echo "volumes still held for $NS: $left (kubectl delete pv <name>, then its disk)"; false; }}
```

## 4. Our Secret

```sh
kubectl -n "$NS" delete secret {values["secrets"]["name"]} --ignore-not-found
```

## 5. The buckets and the images (the account's own commands)

Each bucket emptied of every object and every version (`media` keeps versions), then the
repositories emptied of their images: the namespace's Terraform cannot remove either while it holds
anything.

```sh platform
for b in {buckets}; do
  while :; do
    aws s3api list-object-versions --bucket "$PREFIX$b" --max-items 1000 --output json \\
      --query '{{Objects: [Versions, DeleteMarkers][][].{{Key: Key, VersionId: VersionId}}}}' > "${{TMPDIR:-/tmp}}/versions.json"
    grep -q '"Key"' "${{TMPDIR:-/tmp}}/versions.json" || break
    aws s3api delete-objects --bucket "$PREFIX$b" --delete "file://${{TMPDIR:-/tmp}}/versions.json" >/dev/null
  done
done
for repository in {repositories}; do
  ids=$(aws ecr list-images --repository-name "$repository" --query 'imageIds[*]' --output json)
  [ "$ids" = "[]" ] || aws ecr batch-delete-image --repository-name "$repository" --image-ids "$ids" >/dev/null
done
```

## 6. The namespace's resources (the platform team's pull request)

Remove the namespace's OspreyFlow resources from the environments repository (the files from
`{FOLDER}/terraform/`) and raise the pull request; once it is applied, its Terraform state lists
nothing of OspreyFlow's.

```sh platform
echo "Raise the pull request removing $FOLDER/terraform/'s files, and wait for it to be applied."
```

## 7. Check that nothing is left

Lists the namespace, the cluster's volumes, the Terraform state and the account's buckets, and names
anything of the deployment's still there. Give `STATE` the output of `tofu state list` in the
namespace's folder (the platform team's pipeline prints it).

```sh platform
aws s3api list-buckets --query 'Buckets[].Name' --output text | tr '\\t' '\\n' > "${{TMPDIR:-/tmp}}/buckets.txt"
: "${{STATE:?the output of tofu state list in the namespace folder, saved to a file}}"
cp "$STATE" "${{TMPDIR:-/tmp}}/state.txt"
```

```sh
kinds=$(kubectl api-resources --namespaced --verbs=list -o name | grep -v '^events' | paste -sd, -)
kubectl -n "$NS" get "$kinds" --ignore-not-found -o json > "${{TMPDIR:-/tmp}}/objects.json"
kubectl get pv -o json > "${{TMPDIR:-/tmp}}/volumes.json"
"$PY" -m harness.cloud_platform.decommission_check --values "${{TMPDIR:-/tmp}}/ospreyflow-$NS-values.yaml" \\
  --objects "${{TMPDIR:-/tmp}}/objects.json" --volumes "${{TMPDIR:-/tmp}}/volumes.json" \\
  --state "${{TMPDIR:-/tmp}}/state.txt" --buckets "${{TMPDIR:-/tmp}}/buckets.txt" --bucket-prefix "$PREFIX"
```
"""
