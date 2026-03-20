# Langflow 1.8.1 — Cybersec Test Environment

> ⚠️ **SECURITY RESEARCH ENVIRONMENT — DO NOT DEPLOY PUBLICLY**
>
> This project is an **intentionally vulnerable** test environment for security research and tooling development. It runs Langflow 1.8.1, which contains a critical unauthenticated RCE vulnerability (CVE-2026-33017). Credentials are hardcoded and not meant to be secure.
>
> **Run this only on a local, isolated network. Never expose it to the internet.**

A fully self-contained Docker Compose environment for testing detection tooling against CVE-2026-33017 — unauthenticated RCE in Langflow ≤ 1.8.1 via the `build_public_tmp` endpoint.

Includes:

- **Langflow 1.8.1** — the vulnerable target, with two public flows pre-configured
- **Frontend** — realistic chat UI (port 3000) that calls Langflow like a real user
- **Traffic Simulator** — generates continuous mixed baseline traffic
- **Bootstrapper** — one-shot container that creates and publishes flows on first start
- **Test Suite** — 10 structured test cases across baseline, basic RCE, evasion, and OOB/canary categories

---

## Repository Structure

```
langflow-testenv/
├── docker-compose.yml          # Full environment definition
├── README.md                   # This file
├── frontend/                   # React chat UI
│   ├── Dockerfile
│   ├── nginx.conf              # Proxies /api/* to Langflow
│   ├── src/App.jsx             # Chat interface
│   └── ...
├── langflow-init/
│   └── bootstrap.py           # Creates & publishes flows on first boot
├── simulator/
│   └── simulate.py            # Mixed realistic traffic generator
└── tests/
    ├── README.md              # Test matrix and run instructions
    ├── config.py              # Shared config and payload helpers
    ├── conftest.py            # pytest path setup
    ├── requirements.txt       # pytest
    ├── test_cve_2026_33017.py # pytest test suite (10 test cases)
    ├── run_tests.py           # Standalone Python runner (no pytest needed)
    └── curl_tests.sh          # Self-contained curl commands
```

---

## Quick Start

```bash
docker compose up --build
```

First boot takes ~2 min. Startup order:

1. `langflow` starts and passes its health check (`/api/v1/version`)
2. `bootstrapper` creates two public flows, writes IDs to `/data/flow_ids.json`
3. `simulator` starts generating baseline traffic
4. `frontend` is available at http://localhost:3000

---

## Services & Ports

| Service      | Port  | Description                        |
|--------------|-------|------------------------------------|
| Langflow     | 7860  | Langflow API + UI                  |
| Frontend     | 3000  | Chat UI (proxies /api/* to LF)     |
| Bootstrapper | —     | One-shot setup, exits when done    |
| Simulator    | —     | Internal only, no exposed port     |

---

## Credentials

| Field    | Value        |
|----------|--------------|
| User     | `admin`      |
| Password | `testpass123`|

---

## Flow IDs

After bootstrap, flow IDs are written to the shared volume:

```bash
docker exec langflow cat /data/flow_ids.json
```

Example output:
```json
{
  "echo_chat": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "webhook_logger": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
}
```

Use these UUIDs in the frontend's "Connect a flow" field, in API calls, or when running tests.

---

## Key Endpoints

| Method | Path                                              | Auth     | Notes                          |
|--------|---------------------------------------------------|----------|--------------------------------|
| POST   | `/api/v1/build_public_tmp/{flow_id}/flow`         | None     | **The vulnerable endpoint**    |
| POST   | `/api/v1/run/{flow_id}`                           | Bearer   | Authenticated run              |
| POST   | `/api/v1/webhook/{flow_id}`                       | Bearer   | Webhook trigger                |
| POST   | `/api/v1/login`                                   | None     | Get bearer token               |
| GET    | `/api/v1/version`                                 | None     | Version info                   |
| GET    | `/api/v1/flows/`                                  | Bearer   | List flows                     |

---

## Running the Test Suite

```bash
# 1. Pull flow IDs out of the container
docker exec langflow cat /data/flow_ids.json > tests/flow_ids.json

# 2a. Standalone Python runner (no dependencies)
python tests/run_tests.py

# 2b. pytest
pip install -r tests/requirements.txt
pytest tests/ -v

# 2c. curl
chmod +x tests/curl_tests.sh
./tests/curl_tests.sh
```

### OOB / Canary tests (TC-08, TC-09, TC-10)

Set `OOB_HOST` to a host you control before running:

```bash
OOB_HOST=abc123.oast.me python tests/run_tests.py
```

Free OOB options: [interactsh](https://github.com/projectdiscovery/interactsh), [canarytokens.org](https://canarytokens.org), [webhook.site](https://webhook.site)

### Test matrix

| ID     | Category  | Technique                  | Detection surface           |
|--------|-----------|----------------------------|-----------------------------|
| TC-01a | Baseline  | Legit public build         | Should NOT alert            |
| TC-01b | Baseline  | Authenticated /run         | Should NOT alert            |
| TC-02  | Basic RCE | `os.system` canary write   | Network + process           |
| TC-03  | Basic RCE | `subprocess.run` canary    | Network + process           |
| TC-04  | Evasion   | base64-encoded exec        | Network (obfuscated)        |
| TC-05  | Evasion   | `chr()` obfuscated import  | Network (obfuscated)        |
| TC-06  | Evasion   | `exec(exec())` double-wrap | Network (nested)            |
| TC-07  | Evasion   | 5s delayed execution       | Process (post-response)     |
| TC-08  | OOB       | HTTP callback              | Network egress              |
| TC-09  | OOB       | DNS lookup                 | DNS egress                  |
| TC-10  | OOB       | Unique canary tokens       | OOB log correlation         |

See `tests/README.md` for full details.

---

## Baseline Traffic Mix

The simulator runs continuously in the background:

| Traffic type               | Weight |
|----------------------------|--------|
| Chat via `/run`            | 50%    |
| `build_public_tmp` (legit) | 25%    |
| Webhook trigger            | 15%    |
| API introspection          | 10%    |

Sessions are 3–8 actions with 2–12s think-time between actions and 15–90s between sessions, simulating realistic human-paced usage.

---

## Monitoring

```bash
docker logs -f simulator    # baseline traffic log
docker logs -f langflow     # Langflow application logs
docker logs bootstrapper    # one-shot bootstrap result
```

---

## Resetting

```bash
docker compose down -v
docker compose up --build
```

The `-v` flag removes the `langflow-data` volume and triggers a fresh bootstrap on next start.

---

## The Vulnerability

`POST /api/v1/build_public_tmp/{flow_id}/flow` in Langflow ≤ 1.8.1 accepts an optional `data` parameter containing attacker-controlled flow definitions. Those definitions are passed to `exec()` with no sandboxing and no authentication required.

**CVE:** CVE-2026-33017  
**Affected versions:** `langflow <= 1.8.1`  
**Fixed in:** `langflow >= 1.9.0` (patch removes the `data` parameter entirely)  
**Advisory:** https://github.com/langflow-ai/langflow/security/advisories/GHSA-vwmf-pq79-vjvx
