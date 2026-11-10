#!/usr/bin/env bash
# P7's kind cluster on the test server, set up to the client platform's rules (spec/06_DECISIONS.md
# ADR-148 Consequences): Calico as the network, with its policies enforced; no ReadWriteMany storage
# class (only `gp2-expand`, ReadWriteOnce, by local-path); an NGINX ingress controller. Named
# osprey-p7-* and nothing else, its nodes capped at 8 GB together (the orchestrator's terms,
# 10 November 2026). Run on the server, from OspreyFlow_Core, through
#   OspreyFlow_Build/scripts/stack_lease.sh offline platform -- bash ../OspreyFlow_Build/process/lanes/platform/gates/p7_kind.sh up|down|status
# Its tools are pinned and kept under ~/osprey-runs/platform.tools, never installed system-wide.
set -euo pipefail
NAME=osprey-p7
TOOLS="$HOME/osprey-runs/platform.tools/bin"
KIND_VERSION=v0.27.0
NODE_IMAGE=kindest/node:v1.32.2
KUBECTL_VERSION=v1.32.2
CALICO_VERSION=v3.29.3
INGRESS_VERSION=controller-v1.12.1
export PATH="$TOOLS:$PATH" KUBECONFIG="$HOME/osprey-runs/platform.tools/kubeconfig"

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
  if ! kind get clusters | grep -qx "$NAME"; then
    cat > /tmp/$NAME-kind.yaml <<EOF
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
  - role: worker
EOF
    kind create cluster --name "$NAME" --image "$NODE_IMAGE" --config /tmp/$NAME-kind.yaml --wait 0s
  fi
  # The cluster's own registry (localhost:5001 from the host and from every node), for our images.
  docker inspect "$NAME-registry" >/dev/null 2>&1 || docker run -d --restart=no --name "$NAME-registry" \
    -p 127.0.0.1:5001:5000 public.ecr.aws/docker/library/registry:2 >/dev/null  # Docker Hub's official image, through AWS's mirror (no pull limit)
  docker network connect kind "$NAME-registry" 2>/dev/null || true
  for node in $(kind get nodes --name "$NAME"); do
    docker exec "$node" mkdir -p /etc/containerd/certs.d/localhost:5001
    printf '[host."http://%s:5000"]\n' "$NAME-registry" | docker exec -i "$node" cp /dev/stdin /etc/containerd/certs.d/localhost:5001/hosts.toml
  done
  # 8 GB together: 4 GB a node.
  for node in $(kind get nodes --name "$NAME"); do docker update --memory 4g --memory-swap 4g "$node" >/dev/null; done
  # Calico, by its operator, with its API server (projectcalico.org/v3 policies).
  kubectl create -f "https://raw.githubusercontent.com/projectcalico/calico/$CALICO_VERSION/manifests/tigera-operator.yaml" 2>/dev/null || true
  kubectl wait --for=condition=Established crd/installations.operator.tigera.io --timeout=120s
  kubectl apply -f - <<EOF
apiVersion: operator.tigera.io/v1
kind: Installation
metadata: {name: default}
spec:
  # Calico's own images on quay.io: Docker Hub's pull limit refused them on the test server.
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
  # Storage: the platform's one class, ReadWriteOnce; kind's own `standard` removed, so nothing else exists.
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
  # The ingress controller, as the platform runs one.
  kubectl apply -f "https://raw.githubusercontent.com/kubernetes/ingress-nginx/$INGRESS_VERSION/deploy/static/provider/kind/deploy.yaml"
  kubectl -n ingress-nginx wait --for=condition=Available deployment/ingress-nginx-controller --timeout=600s
  status
}

status() {
  kubectl get nodes -o wide
  kubectl get storageclass
  kubectl get pods -A --field-selector=status.phase!=Running 2>/dev/null | head -20 || true
  docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' $(kind get nodes --name "$NAME")
}

down() {
  [ -x "$TOOLS/kind" ] && kind delete cluster --name "$NAME" || true
  docker ps -a --format '{{.Names}}' | grep "^$NAME" | xargs -r docker rm -f
  # Ours only (never a server-wide prune: other lanes build here too), and the node image.
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -E "^($NAME|localhost:5001/)|^kindest/node:" | xargs -r docker rmi -f
  echo "osprey-p7 down: $(docker ps -a --format '{{.Names}}' | grep -c "^$NAME" || true) containers left"
}

HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$HERE/p7_kind_osprey.yaml"
OUT="$HOME/osprey-runs/platform.tools/render"
NS=ospreyflow-dev
helm() {
  docker run --rm --network host -v "$KUBECONFIG:/root/.kube/config:ro" \
    -v "$PWD/deploy/helm/ospreyflow:/chart:ro" -v "$OUT:/render:ro" alpine/helm:3.16.3 "$@"
}
render() {  # render <registry|any>: `registry` pins each image by the cluster registry's digest
  mkdir -p "$OUT/terraform"
  PYTHONPATH=.:packages .venv/bin/python - "$CONFIG" "$OUT" "$1" <<'PY'
import sys
from pathlib import Path
from harness.images import registry_digest_resolver
from harness.render import load_config, render
config, out, mode = load_config(Path(sys.argv[1])), Path(sys.argv[2]), sys.argv[3]
# kind alone: every image is pinned by the digest the cluster's registry holds for its copy (seeded
# from this server's Docker, whose push writes its own manifest), never Docker Hub's.
def in_kind_registry(ref):
    first, _, rest = ref.split("@")[0].partition("/")
    path = rest if rest and ("." in first or ":" in first or first == "localhost") else ref.split("@")[0]
    return "localhost:5001/" + path
resolver = (lambda ref: registry_digest_resolver(in_kind_registry(ref))) if mode == "registry" else (lambda ref: None)
# An image of ours skipped (SKIP_OURS) is left unpinned on kind, and its pod cannot pull: said so.
import os
result = render(config, resolver=resolver, allow_unpinned=mode == "any" or bool(os.environ.get("SKIP_OURS")))
for name, text in result.artefacts.items():
    (out / name).write_text(text)
print("rendered", ", ".join(sorted(result.artefacts)))
PY
}
# The managed stores' stand-ins, in a namespace of their own, and the secrets the namespace's
# Terraform would write, under the names the platform settings give.
standins() {
  kubectl create namespace platform-managed --dry-run=client -o yaml | kubectl apply -f -
  kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
  if ! kubectl -n platform-managed get secret standin-tls >/dev/null 2>&1; then
    c="$HOME/osprey-runs/platform.tools/standin-ca"
    mkdir -p "$c"
    openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj "/CN=osprey-p7 stand-in CA" \
      -keyout "$c/ca.key" -out "$c/ca.crt" 2>/dev/null
    openssl req -newkey rsa:2048 -nodes -subj "/CN=valkey.platform-managed.svc.cluster.local" \
      -keyout "$c/tls.key" -out "$c/tls.csr" 2>/dev/null
    printf 'subjectAltName=DNS:valkey.platform-managed.svc.cluster.local,DNS:postgres.platform-managed.svc.cluster.local' > "$c/san"
    openssl x509 -req -in "$c/tls.csr" -CA "$c/ca.crt" -CAkey "$c/ca.key" -CAcreateserial -days 7 \
      -extfile "$c/san" -out "$c/tls.crt" 2>/dev/null
    kubectl -n platform-managed create secret generic standin-tls --from-file="$c/tls.crt" --from-file="$c/tls.key" --from-file="$c/ca.crt"
    kubectl -n "$NS" create secret generic standin-ca --from-file="$c/ca.crt"
  fi
  # Their images, and the egress probe's, from the cluster's registry (Docker Hub's limit refuses the nodes).
  for i in postgres:16.4 valkey/valkey:8.0 chrislusf/seaweedfs:4.48 busybox:1.36; do
    docker tag "$i" "localhost:5001/$i" && docker push -q "localhost:5001/$i" >/dev/null
  done
  kubectl apply -f "$HERE/p7_kind_standins.yaml"
  for s in postgres valkey s3; do kubectl -n platform-managed rollout status "statefulset/$s" --timeout=300s; done
  # The buckets the namespace's Terraform makes (`terraform/s3.tf`), on the stand-in.
  for b in media staging site-images tile-cache; do
    echo "s3.bucket.create -name $NS-$b" | kubectl -n platform-managed exec -i s3-0 -- weed shell >/dev/null 2>&1 || true
  done
  kubectl -n "$NS" create secret generic rds-postgresql-instance-output --dry-run=client -o yaml \
    --from-literal=rds_instance_address=postgres.platform-managed.svc.cluster.local \
    --from-literal=rds_instance_port=5432 --from-literal=database_username=osprey \
    --from-literal=database_password=throwaway-p7 --from-literal=database_name=ospreyflow | kubectl apply -f -
  kubectl -n "$NS" create secret generic elasticache-redis --dry-run=client -o yaml \
    --from-literal=primary_endpoint_address=valkey.platform-managed.svc.cluster.local \
    --from-literal=port=6379 --from-literal=auth_token=throwaway-p7 | kubectl apply -f -
  kubectl -n "$NS" create secret generic s3-bucket-output --dry-run=client -o yaml \
    --from-literal=bucket_prefix=ospreyflow-dev- | kubectl apply -f -
}
ourselves() {  # our own Secret as the namespace's Terraform makes it: a password for each key
  # Each key the render names and the Secret lacks is added; one it holds is kept, since the stores
  # already hold its password.
  local key
  kubectl -n "$NS" get secret ospreyflow-secrets >/dev/null 2>&1 || kubectl -n "$NS" create secret generic ospreyflow-secrets
  for key in $(PYTHONPATH=. .venv/bin/python -c "import yaml; v=yaml.safe_load(open('$OUT/values.yaml')); print(' '.join(v['secrets']['keys']))"); do
    kubectl -n "$NS" get secret ospreyflow-secrets -o "jsonpath={.data.$key}" | grep -q . || \
      kubectl -n "$NS" patch secret ospreyflow-secrets --type=merge \
        -p "{\"data\":{\"$key\":\"$(openssl rand -hex 16 | tr -d '\n' | base64 -w0)\"}}" >/dev/null
  done
  kubectl -n "$NS" create serviceaccount ospreyflow --dry-run=client -o yaml | kubectl apply -f -
}
seed_theirs() {
  mkdir -p "$OUT/ours"
  PYTHONPATH=. .venv/bin/python - "$OUT" <<'PY'
import os, sys, yaml
from pathlib import Path
out = Path(sys.argv[1])
plan = yaml.safe_load((out / "images.yaml").read_text())
(out / "ours" / "images.yaml").write_text(yaml.safe_dump(
    {"registry": plan["registry"], "images": [
        i for i in plan["images"] if "dockerfile" in i
        # SKIP_OURS: images of ours already pushed, or not buildable now (a base Docker Hub refuses).
        and not any(f"/ospreyflow/{s}:" in i["target"] for s in os.environ.get("SKIP_OURS", "").split())]}))
(out / "theirs.txt").write_text("".join(f"{i['source']} {i['target']}\n" for i in plan["images"] if "source" in i))
PY
  while read -r source target; do
    local_ref="${source%%@*}"
    docker image inspect "$local_ref" >/dev/null 2>&1 || docker pull -q "$local_ref" >/dev/null || { echo "no local copy of $local_ref"; return 1; }
    docker tag "$local_ref" "$target" && docker push -q "$target" >/dev/null || { echo "push of $target failed"; return 1; }
    echo "seeded $target from this server's $local_ref: $(docker buildx imagetools inspect "$target" --format '{{.Manifest.Digest}}' 2>&1)"
  done < "$OUT/theirs.txt"
}
deploy() {
  render any
  # kind alone: Docker Hub's pull limit refuses the third-party copies on the test server, so each is
  # pushed from this server's own Docker, which already holds it, and the values pin the digest the
  # cluster's registry then holds (`render registry`). `images push` follows a plan of ours alone.
  seed_theirs
  OSPREYFLOW_HOME="$PWD" PYTHONPATH=.:packages:cli .venv/bin/python -m ospreyflow images push --registry localhost:5001 --from "$OUT/ours"
  render registry
  standins
  ourselves
  helm upgrade --install ospreyflow /chart -n "$NS" -f /render/values.yaml
  # kind alone, never rendered: S3 by keys at the stand-in (kind has no IRSA), and the stand-in's CA
  # for Valkey's TLS (ElastiCache's is Amazon's public one).
  kubectl -n "$NS" create configmap p7-kind-overrides --dry-run=client -o yaml \
    --from-literal=MINIO_ENDPOINT=s3.platform-managed.svc.cluster.local:8333 --from-literal=MINIO_USE_SSL=false \
    --from-literal=MINIO_CREDENTIALS=keys --from-literal=MINIO_ACCESS_KEY=p7admin \
    --from-literal=MINIO_SECRET_KEY=throwaway-p7 --from-literal=SSL_CERT_FILE=/etc/p7-ca/ca.crt | kubectl apply -f -
  for d in api worker; do
    kubectl -n "$NS" set env "deployment/$d" --from=configmap/p7-kind-overrides >/dev/null
    kubectl -n "$NS" patch "deployment/$d" --type=strategic -p "{\"spec\":{\"template\":{\"spec\":{
      \"volumes\":[{\"name\":\"p7-ca\",\"secret\":{\"secretName\":\"standin-ca\"}}],
      \"containers\":[{\"name\":\"$d\",\"volumeMounts\":[{\"name\":\"p7-ca\",\"mountPath\":\"/etc/p7-ca\",\"readOnly\":true}]}]}}}}" >/dev/null
  done
}
check() {
  set +e
  echo "== pods"; kubectl -n "$NS" get pods -o wide
  echo "== each running container's user"
  for pod in $(kubectl -n "$NS" get pods --field-selector=status.phase=Running -o name); do
    printf '%s: %s\n' "$pod" "$(kubectl -n "$NS" exec "$pod" -- id 2>&1 | head -1)"
  done
  echo "== claims and budgets"; kubectl -n "$NS" get pvc; kubectl -n "$NS" get pdb
  echo "== Calico policies"; kubectl -n "$NS" get networkpolicies.projectcalico.org
  echo "== egress: the internet refused; the managed stand-ins and the namespace's own pods reached"
  # The probe is one of the deployment's pods (`part-of`), as the chart's own policy admits to its stores.
  kubectl -n "$NS" run p7-egress --image=localhost:5001/busybox:1.36 --labels=app.kubernetes.io/part-of=ospreyflow \
    --restart=Never --rm -i --command -- sh -c \
    'wget -T 5 -q -O /dev/null http://1.1.1.1/ && echo "FAIL internet reached" || echo "PASS internet refused";
     nc -z -w 5 postgres.platform-managed.svc.cluster.local 5432 && echo "PASS managed postgres reached" || echo "FAIL managed postgres refused";
     nc -z -w 5 arcadedb.'"$NS"'.svc.cluster.local 2480 && echo "PASS own arcadedb reached" || echo "FAIL own arcadedb refused"'
}

case "${1:-}" in
  up) up ;; down) down ;; status) status ;; tools) tools ;; deploy) deploy ;; check) check ;;
  *) echo "usage: p7_kind.sh up|down|status|tools|deploy|check" >&2; exit 2 ;;
esac
