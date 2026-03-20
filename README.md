# Langflow 1.8.1 — Cybersec Test Environment

> ⚠️ **SECURITY RESEARCH ENVIRONMENT — DO NOT DEPLOY PUBLICLY**
>
> This project is an **intentionally vulnerable** test environment for security research
> and tooling development. It runs Langflow 1.8.1, which contains a critical unauthenticated
> RCE vulnerability (CVE-2026-33017). Credentials are hardcoded and not meant to be secure.
>
> **Run this only on a local, isolated network. Never expose it to the internet.**

A fully self-contained test environment for validating detection tooling against
**CVE-2026-33017** — unauthenticated remote code execution in Langflow ≤ 1.8.1 via the
`POST /api/v1/build_public_tmp/{flow_id}/flow` endpoint.

Supports two deployment modes:

| Mode          | Best for                                 | Setup time |
|---------------|------------------------------------------|------------|
| Docker Compose| Local development and quick iteration    | ~2 min     |
| AWS EKS       | Realistic cloud environment, team access | ~20 min    |

---

## Repository Structure

```
langflow-testenv/
├── README.md                   # This file
├── docker-compose.yml          # Docker Compose deployment
├── eks-cluster.yaml            # eksctl EKS cluster definition
├── deploy.sh                   # EKS one-shot deploy script
├── teardown.sh                 # EKS cleanup script
│
├── frontend/                   # React chat UI (served by nginx)
│   ├── Dockerfile
│   ├── nginx.conf              # Reverse proxies /api/* to Langflow
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       └── App.jsx             # Chat interface component
│
├── langflow-init/
│   └── bootstrap.py            # Creates and publishes flows on first boot
│
├── simulator/
│   └── simulate.py             # Generates mixed realistic baseline traffic
│
├── k8s/                        # Kubernetes manifests for EKS deployment
│   ├── README.md               # Detailed EKS deployment guide
│   ├── 00-namespace.yaml
│   ├── 01-storage.yaml         # EBS StorageClass + PVC
│   ├── 02-configmap.yaml       # ConfigMap + Secret
│   ├── 03-langflow.yaml        # Langflow Deployment + Service
│   ├── 04-bootstrapper.yaml    # Bootstrap Job
│   ├── 05-simulator.yaml       # Simulator Deployment
│   └── 06-frontend.yaml        # Frontend Deployment + Service
│
└── tests/
    ├── README.md               # Test matrix and detailed run instructions
    ├── config.py               # Shared config, helpers, payload builder
    ├── conftest.py             # pytest path setup
    ├── requirements.txt        # pytest
    ├── test_cve_2026_33017.py  # pytest test suite (10 test cases)
    ├── run_tests.py            # Standalone Python runner (no pytest needed)
    └── curl_tests.sh           # Self-contained curl commands
```

---

## The Vulnerability

`POST /api/v1/build_public_tmp/{flow_id}/flow` in Langflow ≤ 1.8.1 accepts an optional
`data` parameter containing attacker-controlled flow definitions. Those definitions are
passed directly to `exec()` with no sandboxing and no authentication required.

| Field             | Value                                                                          |
|-------------------|--------------------------------------------------------------------------------|
| CVE               | CVE-2026-33017                                                                 |
| Affected versions | `langflow <= 1.8.1`                                                            |
| Fixed in          | `langflow >= 1.9.0` (patch removes the `data` parameter entirely)              |
| Advisory          | https://github.com/langflow-ai/langflow/security/advisories/GHSA-vwmf-pq79-vjvx |
| Patch commit      | https://github.com/langflow-ai/langflow/commit/73b6612                         |

---

## Option 1 — Docker Compose (local)

### Requirements

- Docker Desktop (or Docker Engine + Compose plugin)

### Quick start

```bash
docker compose up --build
```

First boot takes ~2 minutes. Startup order:

1. `langflow` starts and passes its health check on `/api/v1/version`
2. `bootstrapper` creates two public flows and writes their IDs to `/data/flow_ids.json`
3. `simulator` starts generating continuous mixed baseline traffic
4. `frontend` becomes available at http://localhost:3000

### Services and ports

| Service      | Port  | Description                               |
|--------------|-------|-------------------------------------------|
| Langflow     | 7860  | Langflow API and UI                       |
| Frontend     | 3000  | Chat UI (reverse proxies /api/* to LF)    |
| Bootstrapper | —     | One-shot setup container, exits when done |
| Simulator    | —     | Internal only, no exposed port            |

### Monitoring

```bash
docker logs -f simulator      # baseline traffic log
docker logs -f langflow       # Langflow application logs
docker logs bootstrapper      # bootstrap result (one-shot)
```

### Reset

```bash
docker compose down -v        # -v removes the data volume, triggers fresh bootstrap
docker compose up --build
```

---

## Option 2 — AWS EKS

See **[k8s/README.md](k8s/README.md)** for the full EKS deployment guide, including:

- Prerequisites and AWS permissions required
- Cluster architecture diagram
- Step-by-step manual deployment instructions
- Accessing services via `kubectl port-forward`
- Debugging common issues
- Cost breakdown and teardown instructions

### TL;DR

```bash
# Requires: aws cli, kubectl, eksctl, docker
chmod +x deploy.sh teardown.sh
./deploy.sh                    # creates cluster + deploys everything (~20 min)

# Access services
kubectl port-forward svc/langflow 7860:7860 -n langflow-testenv
kubectl port-forward svc/frontend 3000:80   -n langflow-testenv

# Tear down when done
./teardown.sh --full           # removes cluster + ECR + all resources
```

---

## Credentials

| Field    | Value         |
|----------|---------------|
| Username | `admin`       |
| Password | `testpass123` |

---

## Flow IDs

After bootstrap, two public flows are created and their IDs written to `flow_ids.json`.

**Docker Compose:**
```bash
docker exec langflow cat /data/flow_ids.json
```

**EKS:**
```bash
kubectl exec -n langflow-testenv deploy/langflow -- cat /data/flow_ids.json
```

Example output:
```json
{
  "echo_chat":      "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "webhook_logger": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
}
```

---

## Key Endpoints

| Method | Path                                          | Auth   | Notes                       |
|--------|-----------------------------------------------|--------|-----------------------------|
| POST   | `/api/v1/build_public_tmp/{flow_id}/flow`     | None   | **The vulnerable endpoint** |
| POST   | `/api/v1/run/{flow_id}`                       | Bearer | Authenticated flow run      |
| POST   | `/api/v1/webhook/{flow_id}`                   | Bearer | Webhook trigger             |
| POST   | `/api/v1/login`                               | None   | Get bearer token            |
| GET    | `/api/v1/version`                             | None   | Version / health check      |
| GET    | `/api/v1/flows/`                              | Bearer | List all flows              |

---

## Baseline Traffic

The simulator generates continuous mixed traffic to create a realistic baseline
before and during test execution.

| Traffic type                  | Weight | Endpoint                              |
|-------------------------------|--------|---------------------------------------|
| Chat via `/run`               | 50%    | `POST /api/v1/run/{flow_id}`          |
| Legitimate `build_public_tmp` | 25%    | `POST /api/v1/build_public_tmp/…`     |
| Webhook trigger               | 15%    | `POST /api/v1/webhook/{flow_id}`      |
| API introspection             | 10%    | `GET /api/v1/version`, `/api/v1/flows`|

Sessions are 3–8 actions with 2–12s think-time between actions and 15–90s between
sessions, simulating realistic human-paced usage.

---

## Test Suite

Ten structured test cases covering four categories. See **[tests/README.md](tests/README.md)**
for full details and run instructions.

| ID     | Category  | Technique                   | Detection surface        |
|--------|-----------|-----------------------------|--------------------------|
| TC-01a | Baseline  | Legitimate public build     | Should NOT alert         |
| TC-01b | Baseline  | Authenticated `/run`        | Should NOT alert         |
| TC-02  | Basic RCE | `os.system` canary write    | Network + process        |
| TC-03  | Basic RCE | `subprocess.run` canary     | Network + process        |
| TC-04  | Evasion   | base64-encoded exec         | Network (obfuscated)     |
| TC-05  | Evasion   | `chr()` obfuscated import   | Network (obfuscated)     |
| TC-06  | Evasion   | `exec(exec())` double-wrap  | Network (nested)         |
| TC-07  | Evasion   | 5s delayed execution        | Process (post-response)  |
| TC-08  | OOB       | HTTP callback               | Network egress           |
| TC-09  | OOB       | DNS lookup                  | DNS egress               |
| TC-10  | OOB       | Unique canary tokens        | OOB log correlation      |

### Quick run (Docker Compose)

```bash
docker exec langflow cat /data/flow_ids.json > tests/flow_ids.json
python tests/run_tests.py
```

### Quick run (EKS)

```bash
kubectl exec -n langflow-testenv deploy/langflow -- cat /data/flow_ids.json > tests/flow_ids.json
kubectl port-forward svc/langflow 7860:7860 -n langflow-testenv &
python tests/run_tests.py
```

### With OOB canary detection

```bash
OOB_HOST=abc123.oast.me python tests/run_tests.py
```

Free OOB options: [interactsh](https://github.com/projectdiscovery/interactsh) ·
[canarytokens.org](https://canarytokens.org) · [webhook.site](https://webhook.site)
