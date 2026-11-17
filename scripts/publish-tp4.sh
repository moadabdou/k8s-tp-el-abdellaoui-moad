#!/usr/bin/env bash
# Run as your normal user after completing the lab: bash scripts/publish-tp4.sh <binome>
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
[[ $EUID != 0 ]] || { echo 'Run this publication script without sudo.' >&2; exit 1; }
slug=${1:-el-abdellaoui-moad}
[[ $slug =~ ^[a-zA-Z0-9][a-zA-Z0-9-]{0,79}$ ]] || { echo 'Usage: bash scripts/publish-tp4.sh <binome-without-spaces>' >&2; exit 1; }
command -v gh >/dev/null
command -v git >/dev/null
gh auth status
[[ -f .state/latest-evidence ]] || { echo 'Run the lab first.' >&2; exit 1; }
run=$(cat .state/latest-evidence)
[[ $run == "$ROOT"/evidence/* && -f $run/COMPLETE ]] || { echo 'The latest lab run is incomplete.' >&2; exit 1; }
python3 scripts/build-report.py --evidence "$run"
[[ -f report/Rapport_TP4_Kubernetes.pdf ]] || { echo 'PDF report missing.' >&2; exit 1; }
stage=$(mktemp -d "$ROOT/.state/publication.XXXXXXXX")
cp kind-config.yaml kind-config-multinode.yaml pod.yaml whoami.yaml README.md .gitignore "$stage/"
cp -r scripts "$stage/"
mkdir -p "$stage/report" "$stage/evidence"
cp report/Rapport_TP4_Kubernetes.{pdf,md,tex} "$stage/report/"
cp -r report/assets "$stage/report/"
cp -r "$run" "$stage/evidence/"
git -C "$stage" init -b main
if ! git -C "$stage" config user.name >/dev/null; then
    git -C "$stage" config user.name "$(gh api user --jq '.login')"
fi
if ! git -C "$stage" config user.email >/dev/null; then
    git -C "$stage" config user.email "$(gh api user --jq '(.id|tostring) + "+" + .login + "@users.noreply.github.com"')"
fi
git -C "$stage" add .
git -C "$stage" commit -m 'Complete Kubernetes TP4 with manifests, evidence and report'
gh repo create "k8s-tp-$slug" --public --source "$stage" --remote origin --push
repo_url=$(gh repo view "$(gh api user --jq '.login')/k8s-tp-$slug" --json url --jq .url)
printf '%s\n' "$repo_url" > "$ROOT/.state/repository-url"
python3 scripts/build-report.py --evidence "$run"
cp report/Rapport_TP4_Kubernetes.{pdf,md,tex} "$stage/report/"
cp -r report/assets/. "$stage/report/assets/"
git -C "$stage" add report
if ! git -C "$stage" diff --cached --quiet; then
    git -C "$stage" commit -m 'Record the public submission repository in the report'
    git -C "$stage" push origin main
fi
echo "$repo_url"
