# EKS Deployment — Langflow 1.8.1 Cybersec Test Environment

> ⚠️ **SECURITY RESEARCH ENVIRONMENT — DO NOT DEPLOY PUBLICLY**
>
> This deployment runs Langflow 1.8.1, which contains a critical unauthenticated RCE
> vulnerability (CVE-2026-33017). All services are internal (ClusterIP) with no public
> exposure. Never deploy this in a production account or on a publicly accessible cluster.

This directory contains everything needed to deploy the test environment on AWS EKS.
All services are exposed only within the cluster and accessed locally via `kubectl port-forward`.

---

## Prerequisites

The following tools must be installed and configured before running the deploy script.

| Tool       | Minimum version | Check                     | Install                                      |
|------------|-----------------|---------------------------|----------------------------------------------|
| AWS CLI    | 2.x             | `aws --version`           | https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html |
| kubectl    | 1.28+           | `kubectl version --client`| https://kubernetes.io/docs/tasks/tools/      |
| eksctl     | 0.170+          | `eksctl version`          | https://eksctl.io/installation/              |
| Docker     | 24+             | `docker --version`        | https://docs.docker.com/get-docker/          |

AWS credentials must be configured with permissions to create EKS clusters, EC2 resources,
ECR repositories, and IAM roles. The easiest way to verify:

```bash
aws sts get-caller-identity
```

---

## Directory Structure

```
k8s/
├── README.md               # This file
├── 00-namespace.yaml       # Kubernetes namespace
├── 01-storage.yaml         # StorageClass (EBS gp3) + PersistentVolumeClaim
├── 02-configmap.yaml       # ConfigMap (env vars) + Secret (credentials)
├── 03-langflow.yaml        # Langflow Deployment + ClusterIP Service
├── 04-bootstrapper.yaml    # Bootstrap Job + script ConfigMap
├── 05-simulator.yaml       # Traffic Simulator Deployment + script ConfigMap
└── 06-frontend.yaml        # Frontend Deployment + ClusterIP Service

../
├── eks-cluster.yaml        # eksctl cluster definition
├── deploy.sh               # One-shot deploy script
└── teardown.sh             # Cleanup script
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  EKS Cluster: langflow-testenv (us-east-1)              │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Namespace: langflow-testenv                     │   │
│  │                                                  │   │
│  │  ┌─────────────┐    ClusterIP    ┌────────────┐  │   │
│  │  │  frontend   │ ─────────────► │  langflow  │  │   │
│  │  │  :80        │                │  :7860     │  │   │
│  │  └─────────────┘                └─────┬──────┘  │   │
│  │                                       │          │   │
│  │  ┌─────────────┐                      │ PVC      │   │
│  │  │  simulator  │ ─────────────►       │          │   │
│  │  │  (no port)  │                ┌─────▼──────┐   │   │
│  │  └─────────────┘                │  EBS vol   │   │   │
│  │                                 │  /data     │   │   │
│  │  ┌─────────────┐                └─────▲──────┘   │   │
│  │  │ bootstrapper│ ──────────────────── │           │   │
│  │  │  (Job)      │   writes flow_ids    │           │   │
│  │  └─────────────┘                      │           │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  Nodes: 2x t3.medium, private subnets, no public IPs   │
└─────────────────────────────────────────────────────────┘
         │
         │  kubectl port-forward (your machine only)
         │
    localhost:7860  ←── Langflow API + UI
    localhost:3000  ←── Frontend chat UI
```

All inter-service communication is over internal ClusterIP services.
No LoadBalancer or Ingress is created — nothing is reachable from outside the cluster.

---

## Cluster Configuration

Defined in `../eks-cluster.yaml`. Key settings:

| Setting                | Value                      | Notes                                     |
|------------------------|----------------------------|-------------------------------------------|
| Cluster name           | `langflow-testenv`         | Override with `CLUSTER_NAME` env var      |
| Region                 | `us-east-1`                | Override in `eks-cluster.yaml` and env var|
| Kubernetes version     | `1.29`                     |                                           |
| Node type              | `t3.medium` (2 vCPU, 4GB)  | Sufficient for Langflow + simulator       |
| Node count             | 2 (min 2, max 3)           |                                           |
| Node networking        | Private subnets            | No public IP on nodes                     |
| API server access      | Public + private           | kubectl works from your machine via IAM   |
| Storage                | EBS gp3, encrypted         | Provisioned by aws-ebs-csi-driver addon   |

To change the region, edit `eks-cluster.yaml` and set `AWS_REGION` when running scripts:

```bash
AWS_REGION=eu-west-1 ./deploy.sh
```

---

## Deployment

### One-shot deploy

```bash
# From the repo root
chmod +x deploy.sh teardown.sh
./deploy.sh
```

The script performs the following steps in order:

1. Verifies AWS credentials
2. Creates the EKS cluster via eksctl (~15 min, skipped if already exists)
3. Updates your local kubeconfig
4. Creates an ECR repository for the frontend image
5. Builds the frontend Docker image and pushes it to ECR
6. Applies all Kubernetes manifests in numbered order
7. Waits for the Langflow deployment to be ready
8. Waits for the bootstrapper Job to complete

When finished it prints all the `kubectl port-forward` commands you need.

### Manual step-by-step (if you prefer)

```bash
# 1. Create the cluster
eksctl create cluster -f eks-cluster.yaml

# 2. Update kubeconfig
aws eks update-kubeconfig --name langflow-testenv --region us-east-1

# 3. Create ECR repo and push frontend image
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com"
aws ecr create-repository --repository-name langflow-testenv-frontend --region us-east-1
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$ECR_URI"
docker build -t "${ECR_URI}/langflow-testenv-frontend:latest" ./frontend
docker push "${ECR_URI}/langflow-testenv-frontend:latest"

# 4. Apply manifests
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-storage.yaml
kubectl apply -f k8s/02-configmap.yaml
kubectl apply -f k8s/03-langflow.yaml
kubectl apply -f k8s/04-bootstrapper.yaml
kubectl apply -f k8s/05-simulator.yaml
sed "s|FRONTEND_IMAGE|${ECR_URI}/langflow-testenv-frontend:latest|g" k8s/06-frontend.yaml \
  | kubectl apply -f -

# 5. Watch rollout
kubectl rollout status deployment/langflow -n langflow-testenv
kubectl wait job/bootstrapper -n langflow-testenv --for=condition=complete --timeout=300s
```

---

## Accessing Services

All services are ClusterIP — use `kubectl port-forward` to access them locally.
Open each in a separate terminal tab or run them in the background.

### Langflow API and UI

```bash
kubectl port-forward svc/langflow 7860:7860 -n langflow-testenv
```

- UI: http://localhost:7860
- API: http://localhost:7860/api/v1/
- Login: `admin` / `testpass123`

### Frontend chat UI

```bash
kubectl port-forward svc/frontend 3000:80 -n langflow-testenv
```

- http://localhost:3000

### Get flow IDs for testing

```bash
kubectl exec -n langflow-testenv deploy/langflow -- cat /data/flow_ids.json
```

Copy this output into `tests/flow_ids.json` before running the test suite.

---

## Startup Order and Dependencies

The manifests are designed to handle cold-start ordering safely:

| Component    | Waits for                              | Mechanism                              |
|--------------|----------------------------------------|----------------------------------------|
| Langflow     | Nothing (starts immediately)           | Readiness probe on `/api/v1/version`   |
| Bootstrapper | Langflow readiness                     | `initContainer` polls `/api/v1/version`|
| Simulator    | `flow_ids.json` to exist on the PVC    | `initContainer` polls for file         |
| Frontend     | Nothing (static files, no dependency) | Readiness probe on `/`                 |

The bootstrapper runs as a Kubernetes `Job` — it executes once, writes flow IDs to the
shared EBS volume, and exits. The `ttlSecondsAfterFinished: 300` setting cleans up the
pod automatically 5 minutes after it completes.

---

## Monitoring and Debugging

### Check pod status

```bash
kubectl get pods -n langflow-testenv
```

Expected output once everything is running:

```
NAME                         READY   STATUS      RESTARTS   AGE
langflow-xxx                 1/1     Running     0          5m
frontend-xxx                 1/1     Running     0          4m
simulator-xxx                1/1     Running     0          3m
bootstrapper-xxx             0/1     Completed   0          4m
```

### View logs

```bash
# Langflow application
kubectl logs -f deploy/langflow -n langflow-testenv

# Baseline traffic simulator
kubectl logs -f deploy/simulator -n langflow-testenv

# Bootstrap job result
kubectl logs job/bootstrapper -n langflow-testenv

# Frontend (nginx access log)
kubectl logs -f deploy/frontend -n langflow-testenv
```

### Describe a pod (for crash debugging)

```bash
kubectl describe pod -l app=langflow -n langflow-testenv
```

### Common issues

**Bootstrapper keeps restarting**
Langflow is not yet healthy. Check `kubectl logs job/bootstrapper -n langflow-testenv`
and `kubectl describe pod -l app=langflow -n langflow-testenv` for readiness probe failures.

**PVC stuck in Pending**
The `aws-ebs-csi-driver` addon may not be installed or may be unhealthy. Check:
```bash
kubectl get pods -n kube-system | grep ebs
```
If missing, install it:
```bash
eksctl create addon --name aws-ebs-csi-driver --cluster langflow-testenv --region us-east-1
```

**ECR pull errors on nodes**
The node group IAM role needs `AmazonEC2ContainerRegistryReadOnly`. This is configured
in `eks-cluster.yaml` but may take a few minutes to propagate after cluster creation.
Check with:
```bash
kubectl describe pod -l app=frontend -n langflow-testenv | grep -A5 Events
```

**kubectl: Unable to connect to the server**
Re-run the kubeconfig update:
```bash
aws eks update-kubeconfig --name langflow-testenv --region us-east-1
```

---

## Running the Test Suite Against EKS

```bash
# 1. Get flow IDs from the running cluster
kubectl exec -n langflow-testenv deploy/langflow -- cat /data/flow_ids.json > tests/flow_ids.json

# 2. Port-forward Langflow so tests can reach it
kubectl port-forward svc/langflow 7860:7860 -n langflow-testenv &

# 3. Run tests
python tests/run_tests.py

# or with pytest
pip install -r tests/requirements.txt
pytest tests/ -v

# 4. With OOB (set your host first)
OOB_HOST=abc123.oast.me python tests/run_tests.py
```

---

## Updating the Frontend Image

After making changes to `frontend/`:

```bash
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com"
IMAGE="${ECR_URI}/langflow-testenv-frontend:$(git rev-parse --short HEAD)"

docker build -t "$IMAGE" ./frontend
docker push "$IMAGE"

kubectl set image deployment/frontend frontend="$IMAGE" -n langflow-testenv
kubectl rollout status deployment/frontend -n langflow-testenv
```

---

## Resetting Without Recreating the Cluster

To wipe all resources and redeploy from scratch (keeps the cluster, saves ~15 min):

```bash
# Delete namespace (removes all pods, services, jobs, PVCs)
kubectl delete namespace langflow-testenv

# Reapply everything
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-storage.yaml
# ... etc, or just re-run deploy.sh (it skips cluster creation if it exists)
./deploy.sh
```

---

## Teardown

```bash
# Remove k8s resources only — keep the cluster for next time
./teardown.sh

# Remove everything: k8s resources + EKS cluster + ECR repo (~10 min)
./teardown.sh --full
```

The `--full` flag is important if you want to avoid ongoing AWS charges.
A 2-node `t3.medium` cluster costs approximately:

| Resource              | Cost (us-east-1)       |
|-----------------------|------------------------|
| EKS control plane     | ~$0.10/hr              |
| 2x t3.medium nodes    | ~$0.083/hr combined    |
| EBS volume (5Gi gp3)  | ~$0.001/hr             |
| **Total**             | **~$0.18/hr**          |

---

## Credentials Reference

| Service  | Username | Password      | Notes                              |
|----------|----------|---------------|------------------------------------|
| Langflow | `admin`  | `testpass123` | Hardcoded for research use only    |

Credentials are stored in the `langflow-secret` Kubernetes Secret in the namespace.
In a real environment, use AWS Secrets Manager with the External Secrets Operator instead.

---

## Key Endpoints (once port-forwarded)

| Method | Path                                          | Auth   | Notes                       |
|--------|-----------------------------------------------|--------|-----------------------------|
| POST   | `/api/v1/build_public_tmp/{flow_id}/flow`     | None   | **The vulnerable endpoint** |
| POST   | `/api/v1/run/{flow_id}`                       | Bearer | Authenticated run           |
| POST   | `/api/v1/webhook/{flow_id}`                   | Bearer | Webhook trigger             |
| POST   | `/api/v1/login`                               | None   | Get bearer token            |
| GET    | `/api/v1/version`                             | None   | Version / health check      |
| GET    | `/api/v1/flows/`                              | Bearer | List flows                  |

---

## The Vulnerability

`POST /api/v1/build_public_tmp/{flow_id}/flow` in Langflow ≤ 1.8.1 accepts an optional
`data` parameter containing attacker-controlled flow definitions. Those definitions are
passed to `exec()` with no sandboxing and no authentication required.

**CVE:** CVE-2026-33017
**Affected versions:** `langflow <= 1.8.1`
**Fixed in:** `langflow >= 1.9.0`
**Advisory:** https://github.com/langflow-ai/langflow/security/advisories/GHSA-vwmf-pq79-vjvx
