#!/usr/bin/env bash
# P9's kind cluster on the test server (ADR-148 Amendment 7): the backups' round trip and their refusals,
# against the S3 stand-in (tests/fixtures/cloud_platform/s3_standin.py) as a pod, which refuses what S3, STS
# and KMS refuse. Set up as P7's (process/lanes/platform/gates/p7_kind.sh): Calico enforcing policy, the
# platform's one class `gp2-expand` (ReadWriteOnce), 8 GB for its nodes together. Named osprey-p9-* and
# nothing else; its registry on a port found free (`ss -ltn`), never P7's 5001.
#
# Only what a backup touches is deployed: ArcadeDB, ClickHouse and its Keeper, and the backups (the CronJob,
# the restore Job). The render is the profile's own, its `backups` from harness.cloud_platform_backups as
# P9_render.diff calls it; the kind-only patches (p9_kind.py's `patch`) are what EKS gives and kind has not:
# IRSA (the projected token for sts.amazonaws.com, AWS_ROLE_ARN, the stand-in's endpoints and CA) and the
# stand-in's CA in ClickHouse's openSSL client.
#
# Run on the server, from OspreyFlow_Core, through
#   OspreyFlow_Build/scripts/stack_lease.sh offline case -- bash ../OspreyFlow_Build/process/lanes/case/gates/p9_kind.sh up|deploy|roundtrip|reds|down
# and the timed restore under a lease (rule 14), the lease named in the record it writes:
#   stack_lease.sh acquire case "P9 restore timing" && stack_lease.sh remote case -- bash …/p9_kind.sh roundtrip
set -euo pipefail
NAME=osprey-p9
STATE="$HOME/osprey-runs/case.tools"
TOOLS="$STATE/bin"
KIND_VERSION=v0.27.0
NODE_IMAGE=kindest/node:v1.32.2
KUBECTL_VERSION=v1.32.2
CALICO_VERSION=v3.29.3
export PATH="$TOOLS:$PATH" KUBECONFIG="$STATE/kubeconfig"
export OSPREY_PLATFORM_FOLDERS="$(cd "$(dirname "$0")/../../../.." && pwd)/tests/fixtures/cloud_platform/platforms"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$STATE/render"
NS=ospreyflow-dev
PY() { PYTHONPATH=.:packages:../OspreyFlow_Build .venv/bin/python "$@"; }
DRIVER() { PY "$HERE/p9_kind.py" --state "$STATE" --namespace "$NS" "$@"; }

registry_port() {  # the registry's port: the one chosen at `up`, else the first free from 5002
  if [ -s "$STATE/registry-port" ]; then cat "$STATE/registry-port"; return; fi
  local p
  for p in $(seq 5002 5099); do
    ss -ltn "( sport = :$p )" | grep -q ":$p" || { mkdir -p "$STATE"; echo "$p" > "$STATE/registry-port"; echo "$p"; return; }
  done
  echo "no free port for the registry in 5002-5099" >&2; return 1
}

tools() {
  mkdir -p "$TOOLS"
  [ -x "$TOOLS/kind" ] || { curl -fsSLo "$TOOLS/kind" "https://kind.sigs.k8s.io/dl/$KIND_VERSION/kind-linux-amd64"; chmod +x "$TOOLS/kind"; }
  if [ ! -x "$TOOLS/kubectl" ]; then
    curl -fsSLo "$TOOLS/kubectl" "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/amd64/kubectl"
    echo "$(curl -fsSL "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/amd64/kubectl.sha256")  $TOOLS/kubectl" | sha256sum -c -
    chmod +x "$TOOLS/kubectl"
  fi
  kind version; kubectl version --client | head -1
}

up() {
  tools
  local port; port=$(registry_port)
  if ! kind get clusters | grep -qx "$NAME"; then
    cat > "$STATE/kind.yaml" <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  disableDefaultCNI: true   # Calico instead, which enforces policy
  podSubnet: 192.168.0.0/16
containerdConfigPatches:
  - |-
    [plugins."io.containerd.grpc.v1.cri".registry]
      config_path = "/etc/containerd/certs.d"
nodes:
  - role: control-plane
  - role: worker
EOF
    kind create cluster --name "$NAME" --image "$NODE_IMAGE" --config "$STATE/kind.yaml" --wait 0s
  fi
  docker inspect "$NAME-registry" >/dev/null 2>&1 || docker run -d --restart=no --name "$NAME-registry" \
    -p "127.0.0.1:$port:5000" public.ecr.aws/docker/library/registry:2 >/dev/null
  docker network connect kind "$NAME-registry" 2>/dev/null || true
  for node in $(kind get nodes --name "$NAME"); do
    docker exec "$node" mkdir -p "/etc/containerd/certs.d/localhost:$port"
    printf '[host."http://%s:5000"]\n' "$NAME-registry" | docker exec -i "$node" cp /dev/stdin "/etc/containerd/certs.d/localhost:$port/hosts.toml"
    docker update --memory 4g --memory-swap 4g "$node" >/dev/null   # 8 GB together
  done
  kubectl taint nodes "$NAME-control-plane" node-role.kubernetes.io/control-plane:NoSchedule- 2>/dev/null || true
  kubectl create -f "https://raw.githubusercontent.com/projectcalico/calico/$CALICO_VERSION/manifests/tigera-operator.yaml" 2>/dev/null || true
  kubectl wait --for=condition=Established crd/installations.operator.tigera.io --timeout=120s
  kubectl apply -f - <<EOF
apiVersion: operator.tigera.io/v1
kind: Installation
metadata: {name: default}
spec:
  registry: quay.io/
  calicoNetwork:
    ipPools: [{cidr: 192.168.0.0/16, encapsulation: VXLANCrossSubnet, natOutgoing: Enabled, nodeSelector: all()}]
---
apiVersion: operator.tigera.io/v1
kind: APIServer
metadata: {name: default}
spec: {}
EOF
  kubectl wait --for=condition=Ready nodes --all --timeout=600s
  for i in $(seq 1 60); do kubectl api-resources --api-group=projectcalico.org 2>/dev/null | grep -q networkpolicies && break; sleep 5; done
  kubectl api-resources --api-group=projectcalico.org | grep networkpolicies
  kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata: {name: gp2-expand}
provisioner: rancher.io/local-path
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
reclaimPolicy: Delete
EOF
  kubectl delete storageclass standard --ignore-not-found
  status
}

status() {
  kubectl get nodes -o wide
  kubectl get pods -A -o wide 2>/dev/null | grep -E "$NS|platform-managed" || true
  docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' $(kind get nodes --name "$NAME")
}

down() {
  [ -x "$TOOLS/kind" ] && kind delete cluster --name "$NAME" || true
  docker ps -a --format '{{.Names}}' | grep "^$NAME" | xargs -r docker rm -f
  local port; port=$(cat "$STATE/registry-port" 2>/dev/null || echo none)
  # Ours only (never a server-wide prune: other lanes build here too).
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -E "^($NAME|localhost:$port/)" | xargs -r docker rmi -f
  rm -f "$STATE/registry-port"
  echo "$NAME down: $(docker ps -a --format '{{.Names}}' | grep -c "^$NAME" || true) containers left, $(kind get clusters 2>/dev/null | grep -c "^$NAME$" || true) clusters"
}

helm() {
  docker run --rm --network host -v "$KUBECONFIG:/root/.kube/config:ro" \
    -v "$PWD/deploy/helm/ospreyflow:/chart:ro" -v "$OUT:/render:ro" alpine/helm:3.16.3 "$@"
}

images() {  # theirs from this server's Docker; ours (the Conduit's image, which runs the backups) built here
  local port; port=$(registry_port)
  DRIVER render --registry "localhost:$port" --resolve none
  while read -r source target; do
    local_ref="${source%%@*}"
    docker image inspect "$local_ref" >/dev/null 2>&1 || docker pull -q "$local_ref" >/dev/null || { echo "no local copy of $local_ref"; return 1; }
    docker tag "$local_ref" "$target" && docker push -q "$target" >/dev/null
    echo "seeded $target from $local_ref"
  done < "$OUT/theirs.txt"
  OSPREYFLOW_HOME="$PWD" PYTHONPATH=.:packages:cli .venv/bin/python -m ospreyflow images push --registry "localhost:$port" --from "$OUT/ours"
  DRIVER render --registry "localhost:$port" --resolve registry
}

deploy() {
  images
  kubectl create namespace platform-managed --dry-run=client -o yaml | kubectl apply -f -
  kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
  DRIVER standin
  DRIVER secrets
  # Since P7b the chart makes the Ingest root's claim itself; one made by an earlier run here is
  # adopted into the release (Helm's own ownership marks), its data kept.
  if kubectl -n "$NS" get pvc ospreyflow-ingest >/dev/null 2>&1; then
    kubectl -n "$NS" label pvc ospreyflow-ingest app.kubernetes.io/managed-by=Helm --overwrite
    kubectl -n "$NS" annotate pvc ospreyflow-ingest meta.helm.sh/release-name=ospreyflow \
      meta.helm.sh/release-namespace="$NS" --overwrite
  fi
  helm upgrade --install ospreyflow /chart -n "$NS" -f /render/values.yaml
  DRIVER patch
  for s in clickhouse-keeper clickhouse arcadedb; do kubectl -n "$NS" rollout status "statefulset/$s" --timeout=600s; done
}

reset() {  # the deployment and the stand-in removed (their claims with them), the cluster kept
  helm uninstall ospreyflow -n "$NS" 2>/dev/null || true
  kubectl delete namespace "$NS" platform-managed --ignore-not-found --wait=true
}

restore_job() {  # the restore Job for a set, as an operator renders it (`--show-only`), to stdout
  helm template ospreyflow /chart -n "$NS" -f /render/values.yaml --set "backups.restore.set=$1" \
    --show-only templates/backups.yaml
}

case "${1:-}" in
  up) up ;; down) down ;; status) status ;; tools) tools ;; deploy) deploy ;; reset) reset ;;
  restore-job) restore_job "$2" ;;
  roundtrip|reds|seed|backup|destroy|restore|counts|osprey_sources|osprey_bound_red|restore_refused|live_restore|runbook_walk) DRIVER "$1" --helm-script "$0" ;;
  *) echo "usage: p9_kind.sh up|deploy|roundtrip|reds|reset|down|status|seed|backup|destroy|restore|counts" >&2; exit 2 ;;
esac
