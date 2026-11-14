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

from harness.cloud_platform.connections import (  # noqa: F401 - the figures, read from here too
    CONDUIT_POOL_CEILING,
    GATEWAY_POOL_MAX,
    OPERATOR_RESERVE,
    POSTGRES_MAX_CONNECTIONS,
    REPORT_SYNC_POOL,
    RUNNING_LOADS_ALLOWED,
    SQLALCHEMY_POOL,
    SUPERSET_MART_QUERIES,
    SUPERSET_WORKERS,
    UPGRADE_OVERLAP,
    least_connections,
    least_for,
)
from harness.cloud_platform.decommission_check import DISK_NAMESPACE_TAG, KINDS
from harness.cloud_platform.settings import PlatformSettings
from harness.cloud_platform.terraform import BUCKETS, RDS_INSTANCE_CLASS, ecr_repositories
from harness.cloud_platform_backups import BUCKET_SUFFIX, EXPIRE_DAYS, KEPT_AT_DECOMMISSION
from schemas.deployment import OspreyConfig, SearchBackend, generated_folder

RELEASE = "ospreyflow"
CHART = "deploy/helm/ospreyflow"
RENDER = '"$PY" -m harness.render --config "$CONFIG"'

_FENCE = re.compile(r"^```bash( platform)?\n(.*?)^```\n", re.S | re.M)


def _bi(values: dict[str, Any]) -> str | None:
    return next((r["host"] for r in values["ingress"]["rules"] if r["service"] == "superset"), None)


def _reporting_registrations(config: OspreyConfig, values: dict[str, Any]) -> str:
    """ADR-148 Amendments 9 and 10: what the client's Entra administrator registers for Superset and
    the report sync, before step 2 (whose Terraform asks for their secrets)."""
    cp = config.cloud_platform
    assert cp is not None and cp.claims is not None
    claims, parts = cp.claims, []
    if config.reporting.superset:
        parts.append(
            f"**For Superset, before step 2** (ADR-148 Amendment 9): a third app registration, Superset's own (application id\n"
            f"`{claims.superset_client_id}`), a web application whose redirect URI is\n"
            f"`https://{_bi(values)}/oauth-authorized/entra`, with a client secret, and granted this API's\n"
            f"delegated scope `{claims.scope}` with admin consent. Its secret is step 2's\n"
            f"`superset_oidc_client_secret`. Superset reads who signed in from the Conduit, so its roles are\n"
            f"the person's rights here: `administer_system` is Superset's Admin, `manage_dashboards` its\n"
            f"builder (Alpha), `read_reports` its read-only Gamma, and a person with none of them is not let in."
        )
    if config.reporting.sync:
        parts.append(
            "**For the report sync, before step 2** (ADR-148 Amendment 10): on this API's registration, an app role\n"
            "`Dashboard.Read` (allowed member types: Applications). Each dashboard identity is an app\n"
            "registration of its own with a client secret, granted `Dashboard.Read` with admin consent;\n"
            "step 6a registers it here. Until there is one, step 2's `report_sync_dashboards` is `[]`."
        )
    return ("\n" + "\n\n".join(parts) + "\n") if parts else ""


def _reporting_section(config: OspreyConfig, values: dict[str, Any]) -> str:
    """ADR-148 Amendment 11: reports on this profile, after sign-in."""
    if not (config.reporting.superset or config.reporting.sync):
        return ""
    lines = ["## 6a. Reports\n"]
    if config.reporting.superset:
        lines.append(
            f"Superset answers at `https://{_bi(values)}`, signing people in with Entra ID as its own\n"
            "registration; its settings live in its own database, `superset`, which it makes on the managed\n"
            "PostgreSQL at its first start, beside `ospreyflow` and the gateway's `litellm`. The reports\n"
            "themselves are the schema `osprey_reports` inside `ospreyflow`, as on Small.\n"
        )
    if config.reporting.sync:
        lines.append(
            "**A dashboard identity**, for each dashboard the report sync fills: once its app registration\n"
            "exists and holds `Dashboard.Read` (*What it needs*), an administrator registers it in\n"
            "Admin › Dashboards by its application id, with a name (the dashboard's, lower case letters,\n"
            "digits and hyphens), its clearance, unit and handling codes: it reads no more than those allow.\n"
            "Then add it to the Terraform's `report_sync_dashboards`, a JSON list, as\n"
            "`{\"client_id\": \"<its application id>\", \"secret\": \"<its client secret>\"}`, apply, and restart\n"
            "the report sync:\n\n"
            "```bash later\n"
            'kubectl -n "$NS" rollout restart deploy/report-sync\n'
            'kubectl -n "$NS" rollout status deploy/report-sync --timeout 10m\n'
            "```\n"
        )
    lines.append(
        "**Power BI, if the client uses it** (an option, not a step): Power BI reads the schema\n"
        "`osprey_reports` in `ospreyflow` through a read-only login of its own, made on the managed\n"
        "PostgreSQL by the platform's team (`GRANT USAGE ON SCHEMA osprey_reports` and `SELECT ON ALL\n"
        "TABLES IN SCHEMA osprey_reports`, nothing else), reached from wherever Power BI's gateway runs.\n"
        "It reads every row of the mart: who may hold that login is the client's decision.\n"
    )
    return "\n".join(lines) + "\n"


def _opensearch_needs(config: OspreyConfig, platform: PlatformSettings) -> str:
    """v0.5.2 step 3a: what the namespace's OpenSearch needs of the client, where the deployment
    searches with it."""
    if config.components.search is not SearchBackend.OPENSEARCH:
        return ""
    signing = (
        "Every request is signed with SigV4 as the namespace's IAM role (IRSA): the domain's access "
        "policy admits that role alone, with no fine-grained access control, so there is no user or "
        "master password to keep."
        if platform.opensearch_signing == "sigv4"
        else "The platform's own proxy signs the requests to it (`opensearch_signing: none`), so the "
        "pods send them unsigned to the address its secret names."
    )
    return (
        "**The OpenSearch domain** (OpenSearch 2.17, two `t3.medium.search` data nodes with 50 GiB each, "
        "one in each of two availability zones) needs two private subnets, in two availability zones, "
        "in `subnet_ids`, and is reached inside the VPC on 443. " + signing + " The index is not "
        "backed up: it is rebuilt from the graph, and a restore ends with that rebuild.\n"
    )


def _opensearch_goes(config: OspreyConfig) -> str:
    if config.components.search is not SearchBackend.OPENSEARCH:
        return ""
    return (
        " The OpenSearch domain goes with them, and its index is not kept: it was never backed up,"
        " and a deployment made again rebuilds it from its graph."
    )


def _destroy_backups(namespace: str) -> str:
    """The backups bucket emptied of every version and removed, then its key's deletion scheduled:
    step 7 with `BACKUPS=destroy`, and step 9 when a kept retention ends (one text, so the two cannot
    differ)."""
    return f"""\
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
KEY=$(aws kms describe-key --region "$REGION" --key-id "alias/{namespace}-backups" --query KeyMetadata.Arn --output text)
aws kms put-key-policy --region "$REGION" --key-id "$KEY" --policy-name default --policy "file://$WORK/key-policy.json"
aws kms schedule-key-deletion --region "$REGION" --key-id "$KEY" --pending-window-in-days 30
aws kms delete-alias --region "$REGION" --alias-name "alias/{namespace}-backups"
"""


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
    least = least_for(cp.environment == "production")
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
{_reporting_registrations(config, values)}
**The managed PostgreSQL** allows a `max_connections` of {POSTGRES_MAX_CONNECTIONS}. The least it must allow in this
shape is {least}: two Conduits side by side during an update, the worker, the gateway and a reserve (ADR-114
Amendment 43's figures), with Superset and the report sync (from v0.5.2, as many copies as this shape renders)
doubled by an upgrade in progress. {POSTGRES_MAX_CONNECTIONS} is set for every shape, the production shape's least
({least_for(True)}) among them, so this shape has more room: {POSTGRES_MAX_CONNECTIONS - least} to spare. The Terraform
renders it as a {RDS_INSTANCE_CLASS} (8 GiB) with a parameter group setting it. In the environments repository,
with `cloud-platform-terraform-rds-instance`, set it on the module:
`db_parameter = [{{ name = "max_connections", value = "{POSTGRES_MAX_CONNECTIONS}", apply_method = "pending-reboot" }}]`.
`max_connections` is static in PostgreSQL: it takes effect at creation, and on an existing instance only at
its next reboot. With too few, the new Conduit of an update stops at `TooManyConnectionsError`.
{_opensearch_needs(config, platform)}{_bare_connector_hosts(cp.connector_hosts)}
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

{_reporting_section(config, values)}## 7. Check

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
{_seed_section(values)}"""


#: The POC seed path's optional block (ADR-148 Amendment 14), run after step 7 if at all. Plain text,
#: not an f-string: `<rebuild>` is the search index's rebuild where the deployment has one.
_SEED_BLOCK = """\
(
set -e
# The Conduit's and the worker's copies now, to put back. Either at none (a run cut short before, or
# stopped by hand) is refused: start them at their copy counts first, so "back" means back.
api=$(kubectl -n "$NS" get deployment/api -o jsonpath='{.spec.replicas}')
worker=$(kubectl -n "$NS" get deployment/worker -o jsonpath='{.spec.replicas}')
for n in "$api" "$worker"; do
  case "$n" in ''|*[!0-9]*|0) echo "the Conduit or the worker is at none now (api $api, worker $worker): start them first; no seed"; exit 1 ;; esac
done
J="seed-$(date -u +%Y%m%dt%H%M%S)"
seeded=0
finish() {   # whatever happened, on the way out: a Job that did not succeed deleted, then all put back
  set +e
  if [ "$seeded" != 1 ]; then
    kubectl -n "$NS" logs "job/$J" 2>/dev/null
    kubectl -n "$NS" delete job "$J" --ignore-not-found --cascade=foreground --wait --timeout=5m
  fi
  kubectl -n "$NS" scale deployment/api --replicas="$api"
  kubectl -n "$NS" scale deployment/worker --replicas="$worker"
  for c in ospreyflow-backup ospreyflow-backup-claims; do
    kubectl -n "$NS" patch cronjob "$c" -p '{"spec":{"suspend":false}}' 2>/dev/null
  done
  kubectl -n "$NS" rollout status deployment/api --timeout=10m \\
    && kubectl -n "$NS" rollout status deployment/worker --timeout=10m \\
    || echo "the Conduit or the worker is not back yet: kubectl -n $NS scale deployment/api --replicas=$api, deployment/worker --replicas=$worker"
}
trap finish EXIT
# The daily backups held for the seed's length, so none catches it halfway; then the Conduit and the
# worker to none (the seed writes the stores they hold open).
for c in ospreyflow-backup ospreyflow-backup-claims; do
  kubectl -n "$NS" patch cronjob "$c" -p '{"spec":{"suspend":true}}' 2>/dev/null || true
done
kubectl -n "$NS" scale deployment/api deployment/worker --replicas=0
kubectl -n "$NS" wait --for=delete pod -l 'app.kubernetes.io/name in (api,worker)' --timeout=10m \\
  || { echo "the Conduit's or the worker's pods are still running: no seed beside them"; exit 1; }
kubectl -n "$NS" create job --from=cronjob/ospreyflow-seed "$J" \\
  || { echo "$J could not be started (kubectl create job above says why)"; exit 1; }
for i in $(seq 60); do   # started (or already ended) within five minutes
  phase=$(kubectl -n "$NS" get pod -l job-name="$J" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || true)
  case "$phase" in Running|Succeeded|Failed) break ;; esac
  sleep 5
done
case "$phase" in Running|Succeeded|Failed) ;;
  *) echo "$J did not start in five minutes (kubectl -n $NS describe pod -l job-name=$J says why); deleted"; exit 1 ;;
esac
kubectl -n "$NS" wait --for=jsonpath='{.status.conditions[0].status}'=True "job/$J" --timeout=30m \\
  || { echo "$J ran past 30 minutes; deleted"; exit 1; }
kubectl -n "$NS" get job "$J" -o jsonpath='{.status.succeeded}' | grep -qx 1 \\
  || { echo "$J failed: its log above"; exit 1; }
kubectl -n "$NS" logs "job/$J"   # every line the seeds report
seeded=1
)
<rebuild>"""

_SEED_REBUILD = """\
# The search index rebuilt from the seeded graph (the seed writes the graph alone): five minutes to
# start, 30 to finish, deleted and named if it does not.
J="search-rebuild-$(date -u +%Y%m%dt%H%M%S)"
kubectl -n "$NS" create job --from=cronjob/ospreyflow-search-rebuild "$J"
for i in $(seq 60); do
  phase=$(kubectl -n "$NS" get pod -l job-name="$J" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || true)
  case "$phase" in Running|Succeeded|Failed) break ;; esac
  sleep 5
done
ok=1
case "$phase" in Running|Succeeded|Failed) ;; *) ok=0 ;; esac
[ "$ok" = 1 ] && { kubectl -n "$NS" wait --for=jsonpath='{.status.conditions[0].status}'=True "job/$J" --timeout=30m || ok=0; }
[ "$ok" = 1 ] && { kubectl -n "$NS" get job "$J" -o jsonpath='{.status.succeeded}' | grep -qx 1 || ok=0; }
kubectl -n "$NS" logs "job/$J" --tail=1 2>/dev/null || true
[ "$ok" = 1 ] || { kubectl -n "$NS" delete job "$J" --ignore-not-found --wait=false; echo "$J failed (it did not start, ran past 30 minutes or failed); deleted"; false; }
"""


def _seed_section(values: dict[str, Any]) -> str:
    """Step 9 of a poc's install runbook (ADR-148 Amendment 14): spec 08's acceptance data, if the
    POC wants it. Not part of the order (`bash later`); nothing where the shape renders no seed."""
    if "seed" not in values:
        return ""
    rebuild = _SEED_REBUILD if "searchIndex" in values else ""
    return """
## 9. Optional: spec 08's acceptance data (a POC alone)

**Not part of the order, and never on a deployment holding real data.** For a proof of concept that is
to be shown with spec 08's synthetic acceptance data: the HMP fixture, Fixture Corp and the acceptance
scenarios, into one case named *Acceptance scenarios (spec 08)* whose first Author is the first
administrator ({first}), in that administrator's own unit. Run it after step 7, once, after the first
administrator has signed in (step 6): the seed is refused before it writes anything if they have not.
Spec 08's data holds SECRET items (HMP's and Fixture Corp's), above this profile's default ceiling of
OFFICIAL-SENSITIVE. So a POC shown with it declares `deployment.highest_marking: SECRET` in its
osprey.yaml, rendered and applied before this step. That is the client's choice, for a POC holding
synthetic data alone; otherwise the seed is refused before it writes anything, naming both values.
It holds the daily backups and stops the Conduit and the worker for its length (a few
minutes; the door answers 503 meanwhile), puts them all back whether or not it succeeded, and ends by
naming what failed, if anything. A seed Job that did not finish is deleted before the Conduit is back.

```bash later
{block}```
""".format(
        first="the first of `cloud_platform.claims.first_administrators`",
        block=_SEED_BLOCK.replace("<rebuild>", rebuild),
    )


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

The bucket prefix is read from `{secrets.s3.name}`, which step 7 removes, and kept in `$WORK/prefix`: a
shell opened after step 7 (to finish step 8, say) reads it back there. Give `PREFIX` yourself if that
file has gone too.

{_settings(config, platform)}
```bash
if [ -z "${{PREFIX:-}}" ]; then
  PREFIX="$(cat "$WORK/prefix" 2>/dev/null || kubectl -n "$NS" get secret {secrets.s3.name} -o jsonpath='{{.data.{secrets.s3.keys["prefix"]}}}' | base64 -d)"
fi
export PREFIX
test -n "$PREFIX" || {{ echo "no bucket prefix in {secrets.s3.name} nor in $WORK/prefix: give it, PREFIX=<the buckets' prefix>"; false; }}
printf '%s\n' "$PREFIX" > "$WORK/prefix"
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

**First, choose what happens to the backups bucket and its key: there is no default.** Give
`BACKUPS=keep` or `BACKUPS=destroy`; the block refuses anything else, and touches nothing until you
have. The choice is written to `$WORK/backups`, and step 8's record states it.

- **keep**: the kept bucket's lifecycle rule is set to the retention you agree, so the deployment's
  own {EXPIRE_DAYS}-day rule cannot expire the sets this decommission keeps (give it, in days, as
  `BACKUP_RETENTION_DAYS`). The sets stay readable: step 9 removes them when that retention ends,
  and step 10 restores one.
- **destroy**: every set goes now, and cannot be had back. The bucket's policy is removed, every
  version of every object, then the bucket; then the key's policy is replaced by one keeping the
  account's administration, and its deletion scheduled (thirty days, cancellable with
  `aws kms cancel-key-deletion` until then).

Either way the bucket and its key are then taken out of the state, in the namespace's folder, so the
removal does not meet their `prevent_destroy`. Then remove the deployment's resources (the files from
`$FOLDER/terraform/`) from the namespace's folder in the environments repository and raise the pull
request; the folder's other resources are the platform's and stay.{_opensearch_goes(config)}

```bash platform
: "${{BACKUPS:?choose keep or destroy for the backups bucket and its key (there is no default)}}"
case "$BACKUPS" in
  keep|destroy) ;;
  *) echo "BACKUPS: choose keep or destroy for the backups bucket and its key (there is no default)"; false ;;
esac
if [ "$BACKUPS" = keep ]; then
: "${{BACKUP_RETENTION_DAYS:?the retention you agree for the kept backups, in days}}"
printf '{{"Rules": [{{"ID": "abort-unfinished-uploads", "Status": "Enabled", "Filter": {{"Prefix": ""}}, "AbortIncompleteMultipartUpload": {{"DaysAfterInitiation": 7}}}}, {{"ID": "retained-sets", "Status": "Enabled", "Filter": {{"Prefix": "sets/"}}, "Expiration": {{"Days": %d}}, "NoncurrentVersionExpiration": {{"NoncurrentDays": 7}}}}, {{"ID": "remove-expired-markers", "Status": "Enabled", "Filter": {{"Prefix": "sets/"}}, "Expiration": {{"ExpiredObjectDeleteMarker": true}}}}]}}' \\
  "$BACKUP_RETENTION_DAYS" > "$WORK/retention.json"
aws s3api put-bucket-lifecycle-configuration --region "$REGION" --bucket "${{PREFIX}}{BUCKET_SUFFIX}" \\
  --lifecycle-configuration "file://$WORK/retention.json"
aws s3api get-bucket-lifecycle-configuration --region "$REGION" --bucket "${{PREFIX}}{BUCKET_SUFFIX}" | grep -q retained-sets
fi
echo "$BACKUPS" > "$WORK/backups"
M="${{TF_MODULE:+$TF_MODULE.}}"   # the deployment's module in the environments repository, if any
removed=0
for kept in {" ".join(KEPT_AT_DECOMMISSION)}; do tofu state rm "$M$kept" >/dev/null 2>&1 && removed=$((removed + 1)); done
test "$removed" -gt 0 || {{ echo "no kept resource was in the state (is TF_MODULE right?): stop"; false; }}
tofu state list | grep -E '(^|[.])({"|".join(re.escape(k) for k in KEPT_AT_DECOMMISSION)})$' && {{ echo "a kept resource is still in the state: stop"; false; }}
if [ "$BACKUPS" = destroy ]; then
{_destroy_backups(cp.namespace)}
fi
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
test -f "$WORK/backups" || {{ echo "no $WORK/backups: step 7's platform block writes it"; false; }}
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
  --buckets "$WORK/buckets.txt" --bucket-prefix "$PREFIX" --backups "$(cat "$WORK/backups")"
```

The check states the choice step 7 recorded (`backups: kept (the operator chose keep)`, or
`backups: destroyed (the operator chose destroy)`). With keep, it names the backups bucket and its key
as kept (`kept: the backups (retention)`), never as left behind; with destroy, either still there is
left behind. It fails on anything else.

## 9. When the retention ends: the backups bucket, then its key

Your decision, when the retention you agreed ends; the account's administrators run it. The bucket's
policy lets only the deployment's backup roles (removed in step 7) touch its objects, so the policy
goes first; every version of every object is removed (the bucket is versioned), then the bucket.
Only then the key: its own policy refuses everyone its deletion, so that policy is replaced first,
by one keeping the account's administration, and the deletion scheduled (thirty days, cancellable).
A key deleted while the bucket still held a set would leave that set unreadable.

```bash later
{_destroy_backups(cp.namespace)}
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
