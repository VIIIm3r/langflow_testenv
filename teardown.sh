#!/usr/bin/env bash
# teardown.sh — Remove all resources and optionally delete the EKS cluster
#
# Usage:
#   ./teardown.sh              # delete k8s resources only (keep cluster)
#   ./teardown.sh --full       # delete k8s resources AND the EKS cluster + ECR

set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-langflow-testenv}"
AWS_REGION="${AWS_REGION:-us-east-1}"
NAMESPACE="langflow-testenv"
ECR_REPO_NAME="langflow-testenv-frontend"
FULL_DELETE=false

[[ "${1:-}" == "--full" ]] && FULL_DELETE=true

log()  { echo -e "\n\033[1;36m[teardown]\033[0m $*"; }
ok()   { echo -e "\033[1;32m  ✓\033[0m $*"; }
warn() { echo -e "\033[1;33m  !\033[0m $*"; }

# ── Remove Kubernetes resources ───────────────────────────────────────────────
log "Deleting namespace '$NAMESPACE' and all resources within it..."
kubectl delete namespace "$NAMESPACE" --ignore-not-found=true
ok "Namespace deleted."

if [ "$FULL_DELETE" = true ]; then
  # ── Delete ECR repository ──────────────────────────────────────────────────
  log "Deleting ECR repository '$ECR_REPO_NAME'..."
  aws ecr delete-repository \
    --repository-name "$ECR_REPO_NAME" \
    --region "$AWS_REGION" \
    --force \
    &>/dev/null && ok "ECR repo deleted." || warn "ECR repo not found — skipping."

  # ── Delete EKS cluster ─────────────────────────────────────────────────────
  log "Deleting EKS cluster '$CLUSTER_NAME' (this takes ~10 min)..."
  eksctl delete cluster \
    --name "$CLUSTER_NAME" \
    --region "$AWS_REGION"
  ok "Cluster deleted."
else
  warn "Cluster '$CLUSTER_NAME' kept. Run './teardown.sh --full' to delete it too."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Teardown complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
