#!/usr/bin/env bash
# deploy.sh — Create EKS cluster and deploy the full test environment
#
# Prerequisites (all already confirmed):
#   aws cli (configured with credentials)
#   kubectl
#   eksctl
#   helm (available, not used in this script but ready)
#   docker (for building the frontend image)
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Optional env overrides:
#   AWS_REGION=us-west-2 ./deploy.sh
#   CLUSTER_NAME=my-cluster ./deploy.sh

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
CLUSTER_NAME="${CLUSTER_NAME:-langflow-testenv}"
AWS_REGION="${AWS_REGION:-us-east-1}"
NAMESPACE="langflow-testenv"
ECR_REPO_NAME="langflow-testenv-frontend"

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo -e "\n\033[1;36m[deploy]\033[0m $*"; }
ok()   { echo -e "\033[1;32m  ✓\033[0m $*"; }
warn() { echo -e "\033[1;33m  !\033[0m $*"; }
die()  { echo -e "\033[1;31m  ✗\033[0m $*"; exit 1; }

# ── Step 1: Verify AWS credentials ───────────────────────────────────────────
log "Verifying AWS credentials..."
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ok "Account: $AWS_ACCOUNT | Region: $AWS_REGION"

# ── Step 2: Create EKS cluster (skip if exists) ───────────────────────────────
log "Checking for existing cluster '$CLUSTER_NAME'..."
if eksctl get cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" &>/dev/null; then
  warn "Cluster '$CLUSTER_NAME' already exists — skipping creation."
else
  log "Creating EKS cluster (this takes ~15 min)..."
  eksctl create cluster -f eks-cluster.yaml
  ok "Cluster created."
fi

# ── Step 3: Update kubeconfig ─────────────────────────────────────────────────
log "Updating kubeconfig..."
aws eks update-kubeconfig \
  --name "$CLUSTER_NAME" \
  --region "$AWS_REGION"
ok "kubeconfig updated."

# ── Step 4: Create ECR repo for frontend ──────────────────────────────────────
log "Ensuring ECR repository exists..."
ECR_URI="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
FULL_REPO="${ECR_URI}/${ECR_REPO_NAME}"

aws ecr describe-repositories \
  --repository-names "$ECR_REPO_NAME" \
  --region "$AWS_REGION" &>/dev/null \
  || aws ecr create-repository \
       --repository-name "$ECR_REPO_NAME" \
       --region "$AWS_REGION" \
       --image-scanning-configuration scanOnPush=true \
       > /dev/null
ok "ECR repo: $FULL_REPO"

# ── Step 5: Build and push frontend image ─────────────────────────────────────
log "Authenticating Docker to ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_URI"

IMAGE_TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")
FRONTEND_IMAGE="${FULL_REPO}:${IMAGE_TAG}"

log "Building frontend image → $FRONTEND_IMAGE"
docker build -t "$FRONTEND_IMAGE" ./frontend
docker push "$FRONTEND_IMAGE"
ok "Image pushed: $FRONTEND_IMAGE"

# ── Step 6: Apply Kubernetes manifests ────────────────────────────────────────
log "Applying Kubernetes manifests..."

kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-storage.yaml
kubectl apply -f k8s/02-configmap.yaml
kubectl apply -f k8s/03-langflow.yaml
kubectl apply -f k8s/04-bootstrapper.yaml
kubectl apply -f k8s/05-simulator.yaml

# Substitute the real frontend image into the manifest before applying
sed "s|FRONTEND_IMAGE|${FRONTEND_IMAGE}|g" k8s/06-frontend.yaml \
  | kubectl apply -f -

ok "All manifests applied."

# ── Step 7: Wait for Langflow to be ready ─────────────────────────────────────
log "Waiting for Langflow pod to be ready (up to 5 min)..."
kubectl rollout status deployment/langflow \
  -n "$NAMESPACE" \
  --timeout=300s
ok "Langflow is ready."

# ── Step 8: Wait for bootstrapper job ─────────────────────────────────────────
log "Waiting for bootstrapper job to complete (up to 5 min)..."
kubectl wait job/bootstrapper \
  -n "$NAMESPACE" \
  --for=condition=complete \
  --timeout=300s
ok "Bootstrap complete."

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Deployment complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  All services are internal (ClusterIP). Access them via:"
echo ""
echo "  Langflow UI + API:"
echo "    kubectl port-forward svc/langflow 7860:7860 -n $NAMESPACE"
echo "    → http://localhost:7860"
echo ""
echo "  Frontend:"
echo "    kubectl port-forward svc/frontend 3000:80 -n $NAMESPACE"
echo "    → http://localhost:3000"
echo ""
echo "  Get flow IDs:"
echo "    kubectl exec -n $NAMESPACE deploy/langflow -- cat /data/flow_ids.json"
echo ""
echo "  Run test suite:"
echo "    kubectl exec -n $NAMESPACE deploy/langflow -- cat /data/flow_ids.json > tests/flow_ids.json"
echo "    python tests/run_tests.py"
echo ""
echo "  Simulator logs:"
echo "    kubectl logs -f deploy/simulator -n $NAMESPACE"
echo ""
