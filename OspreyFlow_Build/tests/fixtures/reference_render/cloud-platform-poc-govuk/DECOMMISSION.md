# Decommission: OspreyFlow in `ospreyflow-poc`

Rendered for this deployment by `PYTHONPATH=.:packages .venv/bin/python -m harness.render` (ADR-148
Amendment 5). Removes everything the deployment made: its workloads, its claims and their disks,
its Secrets, its buckets and images, and the namespace's resources. **It deletes the deployment's
data for good**: step 2 takes the last backup first. The namespace itself, and every other resource
in it, is the platform team's and stays.

**Kept: the backups (retention).** The backups bucket (`<prefix>backups`) and its KMS key
(`alias/ospreyflow-poc-backups`) are the one exception (ADR-148 Amendment 7): kept, with the last
backup in them, until the retention you agree ends; section 9 removes them then.

**What it needs.** The release's `OspreyFlow_Core` folder with its environment (`.venv`) and this
deployment's rendered folder, `kubectl` pointed at the namespace, `helm`, the AWS command line (v2)
signed in to the namespace's account, and bash. Run each block in order, in one bash shell, from
that folder; if a command fails, stop there.
A block fenced `bash later` is not part of that order: the words before it say when, if ever, it is run.

## 1. The settings

The bucket prefix is read from `s3-bucket-output`, which step 7 removes, and kept in `$WORK/prefix`: a
shell opened after step 7 (to finish step 8, say) reads it back there. Give `PREFIX` yourself if that
file has gone too.

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
if [ -z "${PREFIX:-}" ]; then
  PREFIX="$(cat "$WORK/prefix" 2>/dev/null || kubectl -n "$NS" get secret s3-bucket-output -o jsonpath='{.data.bucket_prefix}' | base64 -d)"
fi
export PREFIX
test -n "$PREFIX" || { echo "no bucket prefix in s3-bucket-output nor in $WORK/prefix: give it, PREFIX=<the buckets' prefix>"; false; }
printf '%s
' "$PREFIX" > "$WORK/prefix"
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
kubectl -n "$NS" wait --for=jsonpath='{.status.conditions[0].status}'=True "job/ospreyflow-backup-$S" --timeout=6h
kubectl -n "$NS" get job "ospreyflow-backup-$S" -o jsonpath='{.status.succeeded}' | grep -qx 1 \
  || { echo "the last backup did not finish: read its log (kubectl -n $NS logs job/ospreyflow-backup-$S)"; false; }
export LAST_BACKUP="s3://${PREFIX}backups/sets/$("$PY" -c 'import datetime, sys; print(datetime.datetime.fromtimestamp(int(sys.argv[1]) * 60, datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))' "$S")/"
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
kubectl -n "$NS" delete pvc ospreyflow-shared ospreyflow-ingest --ignore-not-found --wait --timeout=10m
```

## 5. Our Secret

```bash
kubectl -n "$NS" delete secret ospreyflow-secrets --ignore-not-found
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
for b in media staging site-images tile-cache; do
  for kind in Versions DeleteMarkers; do
    : > "$WORK/versions.last.json"
    while :; do
      if ! aws s3api list-object-versions --region "$REGION" --bucket "$PREFIX$b" --max-items 500 --output json \
          --query "{Objects: $kind[:500].{Key: Key, VersionId: VersionId}}" > "$WORK/versions.json"; then
        echo "listing $PREFIX$b's $kind failed: stopped"; failed=1; break 3
      fi
      grep -q '"Key"' "$WORK/versions.json" || break
      if cmp -s "$WORK/versions.json" "$WORK/versions.last.json"; then
        echo "$PREFIX$b's $kind are the same after a delete: stopped"; failed=1; break 3
      fi
      cp "$WORK/versions.json" "$WORK/versions.last.json"
      if ! errors=$(aws s3api delete-objects --region "$REGION" --bucket "$PREFIX$b" --delete "file://$WORK/versions.json" \
          --query 'length(Errors || `[]`)' --output text); then
        echo "deleting from $PREFIX$b failed: stopped"; failed=1; break 3
      fi
      [ "$errors" = "0" ] || { echo "deleting from $PREFIX$b: $errors key(s) refused: stopped"; failed=1; break 3; }
    done
  done
done
test -z "$failed"
```

```bash platform
failed=
for repository in arcadedata/arcadedb clickhouse/clickhouse-server ospreyflow/api ospreyflow/laurium ospreyflow/litellm ospreyflow/ner ospreyflow/worker ospreyflow/workspace postgres; do
  for status in TAGGED UNTAGGED; do
    last=
    while :; do
      if ! ids=$(aws ecr list-images --region "$REGION" --repository-name "$repository" --filter "tagStatus=$status" \
          --max-items 100 --query 'imageIds[*]' --output json); then
        echo "listing $repository's images failed: stopped"; failed=1; break 3
      fi
      [ "$ids" = "[]" ] && break
      [ "$ids" = "$last" ] && { echo "$repository's images are the same after a delete: stopped"; failed=1; break 3; }
      last=$ids
      if ! refused=$(aws ecr batch-delete-image --region "$REGION" --repository-name "$repository" --image-ids "$ids" \
          --query 'length(failures)' --output text); then
        echo "deleting $repository's images failed: stopped"; failed=1; break 3
      fi
      [ "$refused" = "0" ] || { echo "deleting $repository's images: $refused refused: stopped"; failed=1; break 3; }
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
  own 34-day rule cannot expire the sets this decommission keeps (give it, in days, as
  `BACKUP_RETENTION_DAYS`). The sets stay readable: step 9 removes them when that retention ends,
  and step 10 restores one.
- **destroy**: every set goes now, and cannot be had back. The bucket's policy is removed, every
  version of every object, then the bucket; then the key's policy is replaced by one keeping the
  account's administration, and its deletion scheduled (thirty days, cancellable with
  `aws kms cancel-key-deletion` until then).

Either way the bucket and its key are then taken out of the state, in the namespace's folder, so the
removal does not meet their `prevent_destroy`. Then remove the deployment's resources (the files from
`$FOLDER/terraform/`) from the namespace's folder in the environments repository and raise the pull
request; the folder's other resources are the platform's and stay. The OpenSearch domain goes with them, and its index is not kept: it was never backed up, and a deployment made again rebuilds it from its graph.

```bash platform
: "${BACKUPS:?choose keep or destroy for the backups bucket and its key (there is no default)}"
case "$BACKUPS" in
  keep|destroy) ;;
  *) echo "BACKUPS: choose keep or destroy for the backups bucket and its key (there is no default)"; false ;;
esac
if [ "$BACKUPS" = keep ]; then
: "${BACKUP_RETENTION_DAYS:?the retention you agree for the kept backups, in days}"
printf '{"Rules": [{"ID": "abort-unfinished-uploads", "Status": "Enabled", "Filter": {"Prefix": ""}, "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7}}, {"ID": "retained-sets", "Status": "Enabled", "Filter": {"Prefix": "sets/"}, "Expiration": {"Days": %d}, "NoncurrentVersionExpiration": {"NoncurrentDays": 7}}, {"ID": "remove-expired-markers", "Status": "Enabled", "Filter": {"Prefix": "sets/"}, "Expiration": {"ExpiredObjectDeleteMarker": true}}]}' \
  "$BACKUP_RETENTION_DAYS" > "$WORK/retention.json"
aws s3api put-bucket-lifecycle-configuration --region "$REGION" --bucket "${PREFIX}backups" \
  --lifecycle-configuration "file://$WORK/retention.json"
aws s3api get-bucket-lifecycle-configuration --region "$REGION" --bucket "${PREFIX}backups" | grep -q retained-sets
fi
echo "$BACKUPS" > "$WORK/backups"
M="${TF_MODULE:+$TF_MODULE.}"   # the deployment's module in the environments repository, if any
removed=0
for kept in aws_kms_key.backups aws_kms_alias.backups aws_s3_bucket.backups aws_s3_bucket_versioning.backups aws_s3_bucket_public_access_block.backups aws_s3_bucket_server_side_encryption_configuration.backups aws_s3_bucket_lifecycle_configuration.backups aws_s3_bucket_policy.backups; do tofu state rm "$M$kept" >/dev/null 2>&1 && removed=$((removed + 1)); done
test "$removed" -gt 0 || { echo "no kept resource was in the state (is TF_MODULE right?): stop"; false; }
tofu state list | grep -E '(^|[.])(aws_kms_key\.backups|aws_kms_alias\.backups|aws_s3_bucket\.backups|aws_s3_bucket_versioning\.backups|aws_s3_bucket_public_access_block\.backups|aws_s3_bucket_server_side_encryption_configuration\.backups|aws_s3_bucket_lifecycle_configuration\.backups|aws_s3_bucket_policy\.backups)$' && { echo "a kept resource is still in the state: stop"; false; }
if [ "$BACKUPS" = destroy ]; then
B="${PREFIX}backups"
aws s3api delete-bucket-policy --region "$REGION" --bucket "$B"
while :; do
  aws s3api list-object-versions --region "$REGION" --bucket "$B" --max-items 500 --output json \
    --query '{Objects: [Versions, DeleteMarkers][][].{Key: Key, VersionId: VersionId}}' > "$WORK/versions.json"
  grep -q '"Key"' "$WORK/versions.json" || break
  aws s3api delete-objects --region "$REGION" --bucket "$B" --delete "file://$WORK/versions.json" >/dev/null
done
aws s3api delete-bucket --region "$REGION" --bucket "$B"
ACCOUNT=$(aws sts get-caller-identity --region "$REGION" --query Account --output text)
printf '{"Version": "2012-10-17", "Statement": [{"Sid": "Administer", "Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::%s:root"}, "Action": "kms:*", "Resource": "*"}]}' "$ACCOUNT" > "$WORK/key-policy.json"
KEY=$(aws kms describe-key --region "$REGION" --key-id "alias/ospreyflow-poc-backups" --query KeyMetadata.Arn --output text)
aws kms put-key-policy --region "$REGION" --key-id "$KEY" --policy-name default --policy "file://$WORK/key-policy.json"
aws kms schedule-key-deletion --region "$REGION" --key-id "$KEY" --pending-window-in-days 30
aws kms delete-alias --region "$REGION" --alias-name "alias/ospreyflow-poc-backups"

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
: "${STATE:?the output of tofu state list in the namespace folder, saved to a file}"
cp "$STATE" "$WORK/state.txt"
: > "$WORK/buckets.txt" && failed=
for b in media staging site-images tile-cache backups; do
  if out=$(aws s3api head-bucket --region "$REGION" --bucket "$PREFIX$b" 2>&1); then echo "$PREFIX$b" >> "$WORK/buckets.txt"
  elif echo "$out" | grep -q -e '404' -e 'Not Found'; then :
  else echo "$PREFIX$b could not be checked: $out"; failed=1; fi
done
test -z "$failed"
```

```bash platform
: "${CLUSTER_ACCOUNT:?the AWS account that holds the cluster disks}"
if [ -n "${DISKS:-}" ]; then cp "$DISKS" "$WORK/disks.json"; else
  aws ec2 describe-volumes --region "$REGION" --filters "Name=tag:kubernetes.io/created-for/pvc/namespace,Values=$NS" --output json > "$WORK/disks-listed.json"
  "$PY" -c 'import json, sys; d = json.load(open(sys.argv[1])); d.update(Account=sys.argv[2], Region=sys.argv[3]); json.dump(d, open(sys.argv[4], "w"))' \
    "$WORK/disks-listed.json" "$(aws sts get-caller-identity --region "$REGION" --query Account --output text)" "$REGION" "$WORK/disks.json"
fi
```

```bash
for listing in state.txt buckets.txt; do
  test -f "$WORK/$listing" || { echo "no $WORK/$listing: step 8's first block (the platform's) writes it"; false; }
done
test -f "$WORK/backups" || { echo "no $WORK/backups: step 7's platform block writes it"; false; }
objects=()
for kind in deployments.apps statefulsets.apps replicasets.apps pods jobs.batch cronjobs.batch services configmaps secrets persistentvolumeclaims serviceaccounts ingresses.networking.k8s.io networkpolicies.networking.k8s.io networkpolicies.projectcalico.org poddisruptionbudgets.policy; do
  if kubectl api-resources -o name | grep -qx "$kind"; then
    kubectl -n "$NS" get "$kind" -o json > "$WORK/objects-$kind.json"
    objects+=(--objects "$WORK/objects-$kind.json")
  fi
done
seen=()
[ -f "$WORK/disks.json" ] && seen+=(--disks "$WORK/disks.json" --disks-account "${CLUSTER_ACCOUNT:-}")
[ -f "$WORK/volumes.json" ] && seen+=(--volumes "$WORK/volumes.json")
test "${#seen[@]}" -gt 0 || { echo "no listing of the disks: give DISKS, or let the platform team run step 8's first block"; false; }
"$PY" -m harness.cloud_platform.decommission_check --values "$WORK/values.yaml" "${objects[@]}" "${seen[@]}" \
  ${TF_MODULE:+--module "$TF_MODULE"} --state "$WORK/state.txt" --terraform "$WORK/terraform" \
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
B="${PREFIX}backups"
aws s3api delete-bucket-policy --region "$REGION" --bucket "$B"
while :; do
  aws s3api list-object-versions --region "$REGION" --bucket "$B" --max-items 500 --output json \
    --query '{Objects: [Versions, DeleteMarkers][][].{Key: Key, VersionId: VersionId}}' > "$WORK/versions.json"
  grep -q '"Key"' "$WORK/versions.json" || break
  aws s3api delete-objects --region "$REGION" --bucket "$B" --delete "file://$WORK/versions.json" >/dev/null
done
aws s3api delete-bucket --region "$REGION" --bucket "$B"
ACCOUNT=$(aws sts get-caller-identity --region "$REGION" --query Account --output text)
printf '{"Version": "2012-10-17", "Statement": [{"Sid": "Administer", "Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::%s:root"}, "Action": "kms:*", "Resource": "*"}]}' "$ACCOUNT" > "$WORK/key-policy.json"
KEY=$(aws kms describe-key --region "$REGION" --key-id "alias/ospreyflow-poc-backups" --query KeyMetadata.Arn --output text)
aws kms put-key-policy --region "$REGION" --key-id "$KEY" --policy-name default --policy "file://$WORK/key-policy.json"
aws kms schedule-key-deletion --region "$REGION" --key-id "$KEY" --pending-window-in-days 30
aws kms delete-alias --region "$REGION" --alias-name "alias/ospreyflow-poc-backups"

```

## 10. Restoring a kept set, after the decommission (the platform team's)

A procedure of the platform team's and the account's administrators, who alone may change the kept
bucket's and key's policies; not yet rehearsed, so rehearse it before relying on it. Its steps:

1. **Into this namespace again:** the kept bucket (`${PREFIX}backups`) and alias
   (`alias/ospreyflow-poc-backups`) are taken, so the reinstall's Terraform must not make its own:
   before its first apply, the platform team imports them into its state
   (`tofu import aws_s3_bucket.backups "${PREFIX}backups"`, `tofu import aws_kms_key.backups <the key's ID>`,
   `tofu import aws_kms_alias.backups alias/ospreyflow-poc-backups`, and the bucket's settings likewise); that
   apply then writes the new roles into the kept bucket's and key's policies itself.
2. **Into another namespace:** the administrators replace the kept bucket's policy (`BackupRolesOnly`'s
   `aws:PrincipalArn`) and the key's policy (`UseThroughS3`'s principals) with the new deployment's two
   roles, as its `backups.tf` writes them, and set the new deployment's `ospreyflow-backup-output` Secret's
   `bucket` and `kms_key_arn` to the kept bucket and key, so its runner reads them.
3. The restore itself, by the recovery runbook's cloud-platform section.
