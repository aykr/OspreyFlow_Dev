#!/usr/bin/env bash
# R1's kind cluster on the test server: the client install's acceptance (process/lanes/platform/BRIEF.md).
# The `cloud-platform` profile in `shape: poc`, installed by following P7b's rendered INSTALL.md, checked,
# backed up and restored by the recovery runbook's cloud-platform section, then removed by DECOMMISSION.md.
#
# The cluster is set up to the client platform's rules (ADR-148 Consequences), as P7a's p7_kind.sh is:
# Calico enforcing policy, one storage class (`gp2-expand`, ReadWriteOnce, WaitForFirstConsumer), an NGINX
# ingress controller. One node, its memory capped at R1_NODE_MEMORY (the brief: about 30-32 GiB, beside
# osprey-small capped at about 24). Named osprey-r1-* and nothing else; never touches osprey-small.
# Nothing is published on a host port but the cluster's registry, on 127.0.0.1.
#
#   bash ../OspreyFlow_Build/process/lanes/platform/gates/r1_kind.sh tools|up|status|down     (from OspreyFlow_Core)
#   bash ../OspreyFlow_Build/process/lanes/platform/gates/r1_kind.sh py <r1_kind.py's arguments>
#
# Its tools are pinned and kept under ~/osprey-runs/platform.tools (shared with P7a's), never installed
# system-wide. `tools` and `up` download (kind, kubectl, helm, Calico's and ingress-nginx's manifests and
# images): the owner's yes first.
set -euo pipefail
NAME=osprey-r1
ROOT="$HOME/osprey-runs/platform.tools"
TOOLS="$ROOT/bin"
STATE="$HOME/osprey-runs/platform.r1"
KIND_VERSION=v0.27.0
NODE_IMAGE=kindest/node:v1.32.2
KUBECTL_VERSION=v1.32.2
HELM_VERSION=v3.16.3
CALICO_VERSION=v3.29.3
INGRESS_VERSION=controller-v1.12.1
R1_NODE_MEMORY="${R1_NODE_MEMORY:-32g}"
export PATH="$TOOLS:$PATH" KUBECONFIG="$STATE/kubeconfig"
HERE="$(cd "$(dirname "$0")" && pwd)"
# The kind platform's settings (a test fixture: ADR-148 Amendment 1 item 11).
export OSPREY_PLATFORM_FOLDERS="$(cd "$HERE/../../../.." && pwd)/tests/fixtures/cloud_platform/platforms"

tools() {
  mkdir -p "$TOOLS" "$STATE"
  [ -x "$TOOLS/kind" ] || { curl -fsSLo "$TOOLS/kind" "https://kind.sigs.k8s.io/dl/$KIND_VERSION/kind-linux-amd64"; chmod +x "$TOOLS/kind"; }
  if [ ! -x "$TOOLS/kubectl" ]; then
    curl -fsSLo "$TOOLS/kubectl" "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/amd64/kubectl"
    echo "$(curl -fsSL "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/amd64/kubectl.sha256")  $TOOLS/kubectl" | sha256sum -c -
    chmod +x "$TOOLS/kubectl"
  fi
  # The runbook calls `helm` itself (3.16 or later, its own words), so a binary on the PATH, not a container.
  if [ ! -x "$TOOLS/helm" ] || ! "$TOOLS/helm" version --short | grep -q "^$HELM_VERSION"; then
    local t; t=$(mktemp -d)
    curl -fsSLo "$t/helm.tgz" "https://get.helm.sh/helm-$HELM_VERSION-linux-amd64.tar.gz"
    echo "$(curl -fsSL "https://get.helm.sh/helm-$HELM_VERSION-linux-amd64.tar.gz.sha256sum" | cut -d' ' -f1)  $t/helm.tgz" | sha256sum -c -
    tar -xzf "$t/helm.tgz" -C "$t" linux-amd64/helm && mv "$t/linux-amd64/helm" "$TOOLS/helm" && rm -rf "$t"
  fi
  kind version; kubectl version --client | head -1; helm version --short
}

up() {
  tools
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
    labels: {ingress-ready: "true"}
EOF
    kind create cluster --name "$NAME" --image "$NODE_IMAGE" --config "$STATE/kind.yaml" --kubeconfig "$KUBECONFIG" --wait 0s
  fi
  docker inspect "$NAME-registry" >/dev/null 2>&1 || docker run -d --restart=no --name "$NAME-registry" \
    -p 127.0.0.1:5001:5000 public.ecr.aws/docker/library/registry:2 >/dev/null
  docker network connect kind "$NAME-registry" 2>/dev/null || true
  for node in $(kind get nodes --name "$NAME"); do
    docker exec "$node" mkdir -p /etc/containerd/certs.d/localhost:5001
    printf '[host."http://%s:5000"]\n' "$NAME-registry" | docker exec -i "$node" cp /dev/stdin /etc/containerd/certs.d/localhost:5001/hosts.toml
    docker update --memory "$R1_NODE_MEMORY" --memory-swap "$R1_NODE_MEMORY" "$node" >/dev/null
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
  for _ in $(seq 1 60); do kubectl api-resources --api-group=projectcalico.org 2>/dev/null | grep -q networkpolicies && break; sleep 5; done
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
  kubectl apply -f "https://raw.githubusercontent.com/kubernetes/ingress-nginx/$INGRESS_VERSION/deploy/static/provider/kind/deploy.yaml"
  kubectl -n ingress-nginx wait --for=condition=Available deployment/ingress-nginx-controller --timeout=600s
  status
}

status() {
  kubectl get nodes -o wide
  kubectl get storageclass
  kubectl get pods -A --field-selector=status.phase!=Running 2>/dev/null | head -20 || true
  docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' $(kind get nodes --name "$NAME") "$NAME-registry"
}

down() {
  [ -x "$TOOLS/kind" ] && kind delete cluster --name "$NAME" --kubeconfig "$KUBECONFIG" || true
  docker ps -a --format '{{.Names}}' | grep "^$NAME-" | xargs -r docker rm -f
  # Ours only (never a server-wide prune: other lanes, and osprey-small, live here too).
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -E "^localhost:5001/|^kindest/node:" | xargs -r docker rmi -f
  echo "$NAME down: $(docker ps -a --format '{{.Names}}' | grep -c "^$NAME-" || true) containers left"
}

case "${1:-}" in
  tools) tools ;; up) up ;; status) status ;; down) down ;;
  py) shift; PYTHONPATH=.:packages exec .venv/bin/python "$HERE/r1_kind.py" "$@" ;;
  *) echo "usage: r1_kind.sh tools|up|status|down|py <r1_kind.py arguments>" >&2; exit 2 ;;
esac
