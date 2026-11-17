#!/usr/bin/env bash
# Usage: sudo bash scripts/run-tp4.sh
# Runs only against the dedicated kind cluster and isolated kubeconfig below.
set -Eeuo pipefail
export LC_ALL=C
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
mkdir -p .tools .state evidence report
chmod 700 .state
export PATH="$ROOT/.tools:$PATH"
export KUBECONFIG="$ROOT/.state/kubeconfig"
export KIND_EXPERIMENTAL_PROVIDER=docker
RUN="$ROOT/evidence/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$RUN"
printf '%s\n' "$RUN" > .state/latest-evidence
exec > >(tee "$RUN/session.txt") 2>&1
PF_PID= MON_PID=
finish() {
    local result=$?
    trap - EXIT
    for pid in "$PF_PID" "$MON_PID"; do
        if [[ -n $pid ]]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
    done
    if ((result != 0)); then
        printf 'Execution interrupted, exit code %s. See session.txt.\n' "$result" > "$RUN/FAILED"
        if command -v kubectl >/dev/null && [[ -f $KUBECONFIG ]]; then
            kubectl --context kind-tp-k8s get pods -A -o wide > "$RUN/failure-pods.txt" 2>&1 || true
            kubectl --context kind-tp-k8s get events -A --sort-by=.metadata.creationTimestamp > "$RUN/failure-events.txt" 2>&1 || true
        fi
    fi
    python3 scripts/build-report.py --evidence "$RUN" || result=1
    if [[ $EUID == 0 && -n ${SUDO_UID:-} && -n ${SUDO_GID:-} ]]; then
        chown -R "$SUDO_UID:$SUDO_GID" .tools .state evidence report
    fi
    echo "Evidence: $RUN"
    echo "Report: $ROOT/report/Rapport_TP4_Kubernetes.pdf"
    exit "$result"
}
trap finish EXIT
fail() { echo "ERROR: $*" >&2; exit 1; }
capture() {
    local file=$1; shift
    printf '\n$'; printf ' %q' "$@"; printf '\n'
    "$@" 2>&1 | tee "$RUN/$file"
}
fetch() { curl --fail --location --show-error --retry 3 --connect-timeout 20 "$1" -o "$2"; }
verify() {
    local file=$1 checksum=$2 expected
    expected=$(awk 'NR==1 {print $1}' "$checksum")
    [[ $expected =~ ^[[:xdigit:]]{64}$ ]] || fail "Invalid checksum for $file"
    printf '%s  %s\n' "$expected" "$file" | sha256sum --check
}
for tool in docker curl python3 sha256sum tar; do command -v "$tool" >/dev/null || fail "Missing required tool: $tool"; done
if ! docker info >/dev/null 2>&1; then
    if [[ $EUID == 0 ]]; then systemctl start docker.service; fi
    docker info >/dev/null || fail 'Docker unavailable. Run this script in a host terminal with sudo.'
fi
case $(uname -m) in x86_64) arch=amd64;; aarch64) arch=arm64;; *) fail 'Unsupported architecture';; esac
KIND_VERSION=v0.33.0
K8S_VERSION=v1.37.0
HELM_VERSION=v4.3.1
NODE_IMAGE='kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5'
if [[ ! -x .tools/kind ]]; then
    base="https://github.com/kubernetes-sigs/kind/releases/download/$KIND_VERSION/kind-linux-$arch"
    fetch "$base" .tools/kind.download
    fetch "$base.sha256sum" .tools/kind.sha256sum
    verify .tools/kind.download .tools/kind.sha256sum
    mv .tools/kind.download .tools/kind; chmod 755 .tools/kind
fi
if [[ ! -x .tools/kubectl ]]; then
    base="https://dl.k8s.io/release/$K8S_VERSION/bin/linux/$arch/kubectl"
    fetch "$base" .tools/kubectl.download
    fetch "$base.sha256" .tools/kubectl.sha256
    verify .tools/kubectl.download .tools/kubectl.sha256
    mv .tools/kubectl.download .tools/kubectl; chmod 755 .tools/kubectl
fi
if [[ ! -x .tools/helm ]]; then
    base="https://get.helm.sh/helm-$HELM_VERSION-linux-$arch.tar.gz"
    fetch "$base" .tools/helm.tar.gz
    fetch "$base.sha256sum" .tools/helm.sha256sum
    verify .tools/helm.tar.gz .tools/helm.sha256sum
    tar -xzf .tools/helm.tar.gz -C .tools "linux-$arch/helm"
    mv ".tools/linux-$arch/helm" .tools/helm
    rm -rf -- ".tools/linux-$arch" .tools/helm.tar.gz
fi
{
    date -u --iso-8601=seconds
    uname -srmo
    free -h
    df -h .
    docker version
    kind version
    kubectl version --client
    helm version
} | tee "$RUN/00-environment.txt"
capture 01-hello-world.txt docker run --rm hello-world
clusters=$(kind get clusters)
if [[ $'\n'$clusters$'\n' == *$'\ntp-k8s\n'* ]]; then
    [[ -f .state/owned-cluster ]] || fail 'Cluster tp-k8s already exists and was not created by this script. It was preserved.'
    kind export kubeconfig --name tp-k8s --kubeconfig "$KUBECONFIG"
else
    python3 - <<'PY'
import socket
for port in (30080, 8080):
    with socket.socket() as s:
        s.bind(('127.0.0.1', port))
PY
    free_kib=$(df -Pk . | awk 'END {print $4}')
    (( free_kib >= 20971520 )) || fail 'The assignment requires at least 20 GiB free.'
    touch .state/owned-cluster
    capture 02-create-cluster.txt kind create cluster --config kind-config.yaml --image "$NODE_IMAGE" --kubeconfig "$KUBECONFIG" --wait 300s
fi
k() { kubectl --context kind-tp-k8s --namespace default "$@"; }
capture 03-nodes.txt k get nodes -o wide
k wait --for=condition=Ready nodes --all --timeout=300s
capture 04-system-pods.txt k get pods -n kube-system -o wide
k wait --for=condition=Ready pods --all -n kube-system --timeout=300s
capture 05-docker-nodes.txt docker ps --filter label=io.x-k8s.kind.cluster=tp-k8s
# A rerun resets only assignment resources in this script's own cluster.
k delete deployment whoami --ignore-not-found --wait=true
k delete service whoami --ignore-not-found
k delete pod web test --ignore-not-found --wait=true
capture 06-run-web.txt k run web --image=nginx:1.27 --port=80
k wait --for=condition=Ready pod/web --timeout=240s
capture 07-web-describe.txt k describe pod web
capture 08-web-shell.txt k exec web -- sh -c 'hostname; nginx -v; cat /etc/os-release'
kubectl --context kind-tp-k8s --namespace default port-forward pod/web 8080:80 > "$RUN/09-port-forward.txt" 2>&1 & PF_PID=$!
for ((i=0; i<30; i++)); do
    if curl --fail --silent --max-time 2 http://127.0.0.1:8080 > "$RUN/10-nginx.html"; then break; fi
    sleep 1
done
grep -q 'Welcome to nginx' "$RUN/10-nginx.html" || fail 'Nginx forwarding test failed.'
capture 11-web-logs.txt k logs web
kill "$PF_PID"; wait "$PF_PID" 2>/dev/null || true; PF_PID=
k delete pod web --wait=true
sleep 3
capture 12-standalone-deleted.json k get pods -l run=web -o json
python3 - "$RUN/12-standalone-deleted.json" <<'PY'
import json, sys
assert not json.load(open(sys.argv[1]))['items'], 'Standalone pod unexpectedly recreated'
PY
capture 13-generated-pod.yaml k run web --image=nginx:1.27 --dry-run=client -o yaml
capture 14-declarative-pod.txt k apply -f pod.yaml
k wait --for=condition=Ready pod/web --timeout=180s
capture 15-deployment.txt k apply -f whoami.yaml
k rollout status deployment/whoami --timeout=240s
capture 16-resources.txt k get deploy,rs,pods,svc -o wide
capture 17-endpointslices.txt k get endpointslices -l kubernetes.io/service-name=whoami -o wide
for ((i=0; i<20; i++)); do
    curl --fail --silent --show-error --max-time 5 http://127.0.0.1:30080
    sleep 0.2
done | tee "$RUN/18-load-balancing.txt"
old_pod=$(k get pods -l app=whoami -o jsonpath='{.items[0].metadata.name}')
capture 19-pods-before.json k get pods -l app=whoami -o json
capture 20-delete-managed-pod.txt k delete pod "$old_pod" --wait=true
k wait --for=condition=Ready pods -l app=whoami --timeout=180s
capture 21-pods-after.json k get pods -l app=whoami -o json
python3 - "$RUN" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
before = {x['metadata']['uid'] for x in json.loads((p/'19-pods-before.json').read_text())['items']}
after = {x['metadata']['uid'] for x in json.loads((p/'21-pods-after.json').read_text())['items']}
assert len(after) == 3 and len(after-before) >= 1, 'Replacement pod not verified'
PY
capture 22-scale.txt k scale deployment whoami --replicas=6
k rollout status deployment/whoami --timeout=240s
capture 23-six-replicas.txt k get deploy,rs,pods -o wide
capture 24-six-replicas.json k get deployment whoami -o json
python3 - "$RUN/24-six-replicas.json" <<'PY'
import json, sys
d=json.load(open(sys.argv[1])); assert d['status']['readyReplicas']==6
PY
python3 scripts/monitor-http.py "$RUN/availability.csv" & MON_PID=$!
sleep 2
capture 25-successful-update.txt k set image deployment/whoami whoami=traefik/whoami:v1.11
capture 26-successful-rollout.txt k rollout status deployment/whoami --timeout=240s
capture 27-history-before-failure.txt k rollout history deployment/whoami
capture 28-broken-update.txt k set image deployment/whoami whoami=traefik/whoami:v9.99
found=0
for ((i=0; i<90; i++)); do
    k get pods -l app=whoami -o json > "$RUN/29-broken-pods.json"
    if python3 - "$RUN/29-broken-pods.json" <<'PY'
import json, sys
pods=json.load(open(sys.argv[1]))['items']
sys.exit(0 if any(s.get('state',{}).get('waiting',{}).get('reason')=='ImagePullBackOff'
                 for p in pods for s in p.get('status',{}).get('containerStatuses',[])) else 1)
PY
    then found=1; break; fi
    sleep 2
done
(( found == 1 )) || fail 'ImagePullBackOff was not observed within 180 seconds.'
capture 30-broken-pods.txt k get pods -l app=whoami -o wide
capture 31-broken-deployment.json k get deployment whoami -o json
capture 32-broken-description.txt k describe deployment whoami
capture 33-http-during-failure.txt curl --fail --silent --show-error --max-time 5 http://127.0.0.1:30080
capture 34-rollback.txt k rollout undo deployment/whoami
capture 35-rollback-status.txt k rollout status deployment/whoami --timeout=240s
sleep 3
kill "$MON_PID"; wait "$MON_PID" 2>/dev/null || true; MON_PID=
capture 36-rollout-history.txt k rollout history deployment/whoami
capture 37-final-replicasets.txt k get rs -l app=whoami -o wide
capture 38-final-replicasets.json k get rs -l app=whoami -o json
capture 39-final-deployment.json k get deployment whoami -o json
python3 - "$RUN/39-final-deployment.json" <<'PY'
import json, sys
d=json.load(open(sys.argv[1])); assert d['status']['readyReplicas']==6
assert d['spec']['template']['spec']['containers'][0]['image']=='traefik/whoami:v1.11'
PY
capture 40-dns-challenge.txt k run test --rm -i --restart=Never --image=busybox:1.36 --pod-running-timeout=180s -- sh -c 'nslookup whoami.default.svc.cluster.local && wget -qO- http://whoami.default.svc.cluster.local'
capture 41-final-resources.txt k get deploy,rs,pods,svc -o wide
capture 42-final-endpointslices.txt k get endpointslices -l kubernetes.io/service-name=whoami -o wide
date -u --iso-8601=seconds > "$RUN/COMPLETE"
echo 'All assignment exercises completed. Generating report...'
