# Langflow 1.8.1 — Cybersec Test Environment

A fully self-contained Docker Compose environment with:

- **Langflow 1.8.1** — the target, with two public flows pre-configured
- **Frontend** — realistic chat UI (port 3000) that calls Langflow
- **Traffic Simulator** — generates mixed baseline traffic continuously
- **Bootstrapper** — one-shot container that creates and publishes the flows on first start

---

## Quick Start

```bash
docker compose up --build
```

First boot takes ~2 min. Startup order:

1. `langflow` starts and becomes healthy (health check polls `/api/v1/version`)
2. `bootstrapper` runs, creates two public flows, writes IDs to `/data/flow_ids.json`
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

Output example:
```json
{
  "echo_chat": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "webhook_logger": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
}
```

Use these UUIDs in the frontend's "Connect a flow" field, or directly in API calls.

---

## Key Endpoints (for your tool)

| Method | Path                                              | Auth     | Notes                          |
|--------|---------------------------------------------------|----------|--------------------------------|
| POST   | `/api/v1/build_public_tmp/{flow_id}/flow`         | None     | **The target endpoint**        |
| POST   | `/api/v1/run/{flow_id}`                           | Bearer   | Authenticated run              |
| POST   | `/api/v1/webhook/{flow_id}`                       | Bearer   | Webhook trigger                |
| POST   | `/api/v1/login`                                   | None     | Get bearer token               |
| GET    | `/api/v1/version`                                 | None     | Version info                   |
| GET    | `/api/v1/flows/`                                  | Bearer   | List flows                     |

---

## Baseline Traffic Mix

The simulator generates continuous mixed traffic:

| Traffic type               | Weight |
|----------------------------|--------|
| Chat via `/run`            | 50%    |
| `build_public_tmp` (legit) | 25%    |
| Webhook trigger            | 15%    |
| API introspection          | 10%    |

Sessions are 3–8 actions with 2–12s think-time between actions, and 15–90s between sessions. This simulates realistic human-paced usage.

---

## Monitoring

```bash
# Simulator traffic log
docker logs -f simulator

# Langflow logs
docker logs -f langflow

# Bootstrap result
docker logs bootstrapper
```

---

## Resetting

To wipe state and re-bootstrap from scratch:

```bash
docker compose down -v
docker compose up --build
```

The `-v` flag removes the named `langflow-data` volume, which triggers a fresh bootstrap on next start.

---

## What's Vulnerable

`POST /api/v1/build_public_tmp/{flow_id}/flow` in Langflow ≤ 1.8.1 accepts
an optional `data` parameter containing attacker-controlled flow definitions.
Those definitions are passed to `exec()` with no sandboxing and no authentication.

This is **CVE-2026-33017**. The fix (removing the `data` parameter) landed in v1.9.0.

**This environment is intentionally vulnerable. Do not expose it to a public network.**
