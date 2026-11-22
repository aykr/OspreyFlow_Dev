# Install: OspreyFlow in `ospreyflow-poc` (poc shape)

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
two app registrations in tenant `00000000-1111-4222-8333-444444444444`: the Glass (application id `bbbbbbbb-cccc-4ddd-8eee-ffffffffffff`)
and this API (`aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee`, exposing the scope `access_as_user`, which the Glass is
granted), with the claims `cloud_platform.claims` names.

**For an orchestrator that runs pipelines** (ADR-141 decision 10, ADR-148 Amendment 20): on this API's
registration, an app role `OspreyFlow.Run` (allowed member types: Applications). The orchestrator's
own app registration, the client's and not one of this deployment's counted registrations, signs in
with the client-credentials grant and is granted `OspreyFlow.Run` as an application permission with
admin consent; without it the run API refuses its token, in words saying where to grant it.
`ospreyflow run` signs it in with its own application id and secret (`OSPREY_CLIENT_ID`,
`OSPREY_CLIENT_SECRET`), `OSPREY_TOKEN_URL` set to
`https://login.microsoftonline.com/00000000-1111-4222-8333-444444444444/oauth2/v2.0/token` and `OSPREY_TOKEN_SCOPE` to
`api://aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/.default`, the API's application ID URI and `/.default`, without which Entra ID issues
no token.

**The managed PostgreSQL** allows a `max_connections` of 1000. The least it must allow in this
shape is 834: two Conduits side by side during an update, the worker, the gateway and a reserve (ADR-114
Amendment 43's figures), with Superset and the report sync (as many copies as this shape renders)
doubled by an upgrade in progress. 1000 is set for every shape, the production shape's least
(918) among them, so this shape has more room: 166 to spare. The Terraform
renders it as a db.t4g.large (8 GiB) with a parameter group setting it. In the environments repository,
with `cloud-platform-terraform-rds-instance`, set it on the module:
`db_parameter = [{ name = "max_connections", value = "1000", apply_method = "pending-reboot" }]`.
`max_connections` is static in PostgreSQL: it takes effect at creation, and on an existing instance only at
its next reboot. With too few, the new Conduit of an update stops at `TooManyConnectionsError`.
**The OpenSearch domain** (OpenSearch 2.17, two `t3.medium.search` data nodes with 50 GiB each, one in each of two availability zones) needs two private subnets, in two availability zones, in `subnet_ids`, and is reached inside the VPC on 443. Every request is signed with SigV4 as the namespace's IAM role (IRSA): the domain's access policy admits that role alone, with no fine-grained access control, so there is no user or master password to keep. The index is not backed up: it is rebuilt from the graph, and a restore ends with that rebuild.

## 1. The settings and the namespace

```bash
export NS=ospreyflow-poc RELEASE=ospreyflow FOLDER=deploy/generated/cloud-platform CHART=deploy/helm/ospreyflow REGION=eu-west-2
export CONFIG="${CONFIG:-osprey.yaml}" PY="${PY:-.venv/bin/python}" PYTHONPATH=.:packages
export WORK="${TMPDIR:-/tmp}/ospreyflow-$NS" && mkdir -p "$WORK"
test -n "$BASH_VERSION" || { echo "run these blocks in bash"; false; }
test -x "$PY" || { echo "no $PY: make the release's environment first (uv sync --frozen)"; false; }
command -v kubectl >/dev/null && command -v helm >/dev/null || { echo "kubectl and helm are needed"; false; }
test "$(kubectl config view --minify -o jsonpath='{..namespace}')" = "$NS" \
  || { echo "kubectl's context is not the namespace $NS: kubectl config set-context --current --namespace=$NS"; false; }
```

```bash
command -v ospreyflow >/dev/null || { echo "no ospreyflow command: uv tool install ./cli, and put ~/.local/bin on PATH"; false; }
docker buildx version >/dev/null || { echo "Docker's buildx is needed to build the images"; false; }
kubectl auth can-i create statefulsets -n "$NS"
kubectl auth can-i create persistentvolumeclaims -n "$NS"
```

This runbook installs a new deployment, or moves one already in the namespace to this release.
v0.6.0 is installed fresh: a namespace holding a deployment of an earlier release is not moved onto
it, and the next block stops there, saying so, before anything is changed.

```bash
if helm status "$RELEASE" -n "$NS" >/dev/null 2>&1; then
  "$PY" -m harness.fresh_only --installing dev-0123456 \
    --installed "$(kubectl -n "$NS" get configmap ospreyflow-env -o jsonpath='{.data.OSPREY_RELEASE_VERSION}' 2>/dev/null)"
fi
```

## 2. The namespace's resources (the platform team's pull request)

Copy `$FOLDER/terraform/` into the namespace's folder in the environments repository and raise the
pull request. Once it is applied, the namespace holds the managed stores' Secrets, our Secret and the
service account the Conduit reads S3 as.

```bash platform
echo "Raise the pull request with $FOLDER/terraform/, and wait for it to be applied."
```

```bash
for secret in rds-postgresql-instance-output elasticache-redis s3-bucket-output ospreyflow-secrets; do
  kubectl -n "$NS" get secret "$secret" -o name
done
kubectl -n "$NS" get serviceaccount ospreyflow -o name
```

## 3. The images

Render the plan (ours are not in the registry yet, so the values are not pinned), sign in to the
registry, then build ours and copy the others, each by its digest, into `123456789012.dkr.ecr.eu-west-2.amazonaws.com`.

```bash
"$PY" -m harness.render --config "$CONFIG" --allow-unpinned
```

```bash platform
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin 123456789012.dkr.ecr.eu-west-2.amazonaws.com
```

```bash
ospreyflow images push --registry "123456789012.dkr.ecr.eu-west-2.amazonaws.com" --from "$FOLDER"
```

## 4. The values, pinned

Every image now by the digest the registry holds for it. The third-party ones keep the digest the
plan copied, even if a tag has moved since; delete `$FOLDER/images.yaml` before step 3 to take a
newer one.

```bash
"$PY" -m harness.render --config "$CONFIG"
```

## 5. The deployment

```bash
helm upgrade --install "$RELEASE" "$CHART" -n "$NS" -f "$FOLDER/values.yaml" --timeout 30m
kubectl -n "$NS" rollout status deployment/workspace --timeout=900s
kubectl -n "$NS" rollout status deployment/api --timeout=900s
kubectl -n "$NS" rollout status deployment/ner --timeout=900s
kubectl -n "$NS" rollout status statefulset/arcadedb --timeout=900s
kubectl -n "$NS" rollout status deployment/litellm --timeout=900s
kubectl -n "$NS" rollout status statefulset/clickhouse --timeout=900s
kubectl -n "$NS" rollout status deployment/laurium --timeout=900s
kubectl -n "$NS" rollout status deployment/worker --timeout=900s
# The search index rebuilt from the graph as it stands (ADR-150 decision 4): five minutes to start,
# 30 to finish, deleted and named if it does not.
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
```

## 6. Sign-in: Entra ID and the first administrators

People sign in with the client's own Entra ID (ADR-148 Amendment 8): there is no sign-in service of
ours to set up, only the two app registrations *What it needs* asks for, in tenant
`00000000-1111-4222-8333-444444444444`. The first administrators (50000000-0000-4000-8000-000000000001) were given the Admin role when the
Conduit first started; they give everyone else their roles in Admin › People and roles. Check the Conduit reads
Entra's settings:

```bash
kubectl -n "$NS" exec deploy/api -- printenv OSPREY_IDENTITY_PROVIDER OIDC_ISSUER
```

**The token version** (ADR-148 Amendment 18). The Conduit expects v2.0 access tokens
(`cloud_platform.claims.token_version`). If the API registration issues the other version, every sign-in is
refused, and the Conduit says why, once, in its log: which version the registration issues and what to set
(`requestedAccessTokenVersion` in the API registration's manifest, or `token_version`). Run this after the
first administrator's first sign-in (section 8, item 2). Before anyone has signed in it can only say that no
sign-in has been refused for this so far.

```bash
# Every api pod's log, whole (`logs deploy/api` reads one pod; `-l` alone reads ten lines a pod).
said="$(kubectl -n "$NS" logs -l app.kubernetes.io/name=api --since=24h --tail=-1 --prefix 2>/dev/null | grep -m1 -F "token version: " || true)"
if [ -n "$said" ]; then
  echo "$said"; echo "sign-in is refused for the token version: fix it as said, render again (step 4) and install"; false
else
  echo "no sign-in refused for its token version so far"
fi
```

**If no administrator is left** (nobody enabled who has signed in can manage people): add the Entra
object id of a person who is not disabled here to `cloud_platform.claims.first_administrators` in
`osprey.yaml`, render again (step 4) and install the new values: the list is in the deployment's
ConfigMap, so a restart alone would read the old one, and the install restarts the Conduit. At start, and only when nobody can
manage people, the Conduit adds the Admin role to each one named there, and audits it
(`grant_first_administrator`). While anyone can manage people, it changes nobody's roles.

```bash later
"$PY" -m harness.render --config "$CONFIG"
helm upgrade --install "$RELEASE" "$CHART" -n "$NS" -f "$FOLDER/values.yaml" --timeout 30m
kubectl -n "$NS" rollout status deploy/api --timeout 10m
```

## 7. Check

The doors answer through the platform's ingress (ospreyflow-poc.apps.example.org): `/healthz` is the Conduit's,
answered through the Glass. `OSPREY_CURL_OPTS` is curl's options for that door, if it needs any:
where the ingress's certificate is signed by a CA your machine does not trust, export
`OSPREY_CURL_OPTS="--cacert <that CA's file>"` first.

```bash
curl -fsS ${OSPREY_CURL_OPTS:-} "https://ospreyflow-poc.apps.example.org/healthz" >/dev/null && echo "the Glass answers"
kubectl -n "$NS" get pods
```

## 8. Against the client's real tenant (once, with the client's Entra administrator)

**This section is not a block to run: each item needs a person at a browser.** Our own acceptance
signed in through a stand-in for Entra ID, which can show how the Conduit treats a token but nothing
about how tenant `00000000-1111-4222-8333-444444444444` is set up. Only the real tenant shows these. If any item fails,
stop and raise it with the client's Entra administrator before anyone else is told the service is ready.

1. **Token version.** With `token_version` 2.0, the API registration's manifest has
   `requestedAccessTokenVersion` set to 2. Without it, Entra issues v1.0 tokens with another issuer,
   and every sign-in is refused, in words that say so: step 6's token-version check, run after this
   first sign-in, shows them.
2. **The first administrator.** One of 50000000-0000-4000-8000-000000000001 signs in at
   `https://ospreyflow-poc.apps.example.org`. Admin › People and roles lists them with Admin, and their clearance (for example
   OFFICIAL-SENSITIVE), unit and handling codes are the ones their groups give. If they are not, the
   claims set in the registration (`claims_mapping_policy`, optional claims) do not send what
   `cloud_platform.claims` names.
3. **A person given no role.** A member of the tenant whom no administrator has given a role signs in,
   is listed in Admin › People and roles with no role, and sees no case and no Admin.
4. **Who may sign in at all.** If the Glass's enterprise application has *Assignment required*, a person
   who is not assigned is refused by Entra itself (AADSTS50105) and never reaches the deployment. If it
   does not, every member of the tenant can sign in, with no role until given one: confirm which the
   client wants.
5. **A guest.** A guest (B2B) account signs in and is refused.
6. **Many groups.** A person in more than 200 groups is refused in words, because Entra then leaves the
   groups out of the token. Limit the claim to the groups assigned to the application.
7. **Keys.** Entra rolls its signing key unannounced. The Conduit fetches the tenant's keys again
   within five minutes. A sign-in still refused for an unknown key after that is a fault: report it.

## 9. Optional: spec 08's acceptance data (a POC alone)

**Not part of the order, and never on a deployment holding real data.** For a proof of concept that is
to be shown with spec 08's synthetic acceptance data: the HMP fixture, Fixture Corp and the acceptance
scenarios, into one case named *Acceptance scenarios (spec 08)* whose first Author is the first
administrator (the first of `cloud_platform.claims.first_administrators`), in that administrator's own unit. Run it after step 7, once, after the first
administrator has signed in (step 6): the seed is refused before it writes anything if they have not.
Spec 08's data holds SECRET items (HMP's and Fixture Corp's), above this profile's default ceiling of
OFFICIAL-SENSITIVE. So a POC shown with it declares `deployment.highest_marking: SECRET` in its
osprey.yaml, rendered and applied before this step. That is the client's choice, for a POC holding
synthetic data alone; otherwise the seed is refused before it writes anything, naming both values.
It holds the daily backups and stops the Conduit and the worker for its length (a few
minutes; the door answers 503 meanwhile), puts them all back whether or not it succeeded, and ends by
naming what failed, if anything. A seed Job that did not finish is deleted before the Conduit is back.

```bash later
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
  kubectl -n "$NS" rollout status deployment/api --timeout=10m \
    && kubectl -n "$NS" rollout status deployment/worker --timeout=10m \
    || echo "the Conduit or the worker is not back yet: kubectl -n $NS scale deployment/api --replicas=$api, deployment/worker --replicas=$worker"
}
trap finish EXIT
# The daily backups held for the seed's length, so none catches it halfway; then the Conduit and the
# worker to none (the seed writes the stores they hold open).
for c in ospreyflow-backup ospreyflow-backup-claims; do
  kubectl -n "$NS" patch cronjob "$c" -p '{"spec":{"suspend":true}}' 2>/dev/null || true
done
kubectl -n "$NS" scale deployment/api deployment/worker --replicas=0
kubectl -n "$NS" wait --for=delete pod -l 'app.kubernetes.io/name in (api,worker)' --timeout=10m \
  || { echo "the Conduit's or the worker's pods are still running: no seed beside them"; exit 1; }
kubectl -n "$NS" create job --from=cronjob/ospreyflow-seed "$J" \
  || { echo "$J could not be started (kubectl create job above says why)"; exit 1; }
for i in $(seq 60); do   # started (or already ended) within five minutes
  phase=$(kubectl -n "$NS" get pod -l job-name="$J" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || true)
  case "$phase" in Running|Succeeded|Failed) break ;; esac
  sleep 5
done
case "$phase" in Running|Succeeded|Failed) ;;
  *) echo "$J did not start in five minutes (kubectl -n $NS describe pod -l job-name=$J says why); deleted"; exit 1 ;;
esac
kubectl -n "$NS" wait --for=jsonpath='{.status.conditions[0].status}'=True "job/$J" --timeout=30m \
  || { echo "$J ran past 30 minutes; deleted"; exit 1; }
kubectl -n "$NS" get job "$J" -o jsonpath='{.status.succeeded}' | grep -qx 1 \
  || { echo "$J failed: its log above"; exit 1; }
kubectl -n "$NS" logs "job/$J"   # every line the seeds report
seeded=1
)
# The block ends with the seed's outcome: a seed that did not succeed is named last, nothing runs
# after it, and the block ends failed.
if [ "$?" != 0 ]; then
  echo "the seed did not succeed: what it says above. Nothing after it was run."
  false
else
# The search index rebuilt from the graph as it stands (ADR-150 decision 4): five minutes to start,
# 30 to finish, deleted and named if it does not.
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
fi
```
