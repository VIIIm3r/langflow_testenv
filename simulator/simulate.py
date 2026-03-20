#!/usr/bin/env python3
"""
Traffic simulator — generates mixed realistic baseline traffic against Langflow.

Traffic mix:
  - Chat messages via /api/v1/run/{flow_id}           (~50%)
  - build_public_tmp legitimate calls                  (~25%)
  - Webhook triggers via /api/v1/webhook/{flow_id}    (~15%)
  - API introspection (version, flows list)            (~10%)

Pacing is randomised with natural jitter to avoid looking like a synthetic
load test. Sessions simulate realistic human think-time gaps.
"""

import json
import os
import random
import time
import traceback
import urllib.request
import urllib.error
from datetime import datetime

BASE       = os.environ.get("LANGFLOW_URL", "http://langflow:7860")
USER       = os.environ.get("LANGFLOW_USER", "admin")
PASS       = os.environ.get("LANGFLOW_PASS", "testpass123")
IDS_FILE   = "/data/flow_ids.json"

# ── helpers ───────────────────────────────────────────────────────────────────

def ts():
    return datetime.utcnow().strftime("%H:%M:%S")


def log(tag, msg, ok=True):
    sym = "✓" if ok else "✗"
    print(f"[{ts()}] {sym} [{tag}] {msg}", flush=True)


def http(method, path, body=None, token=None, timeout=20):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


def jitter(base, spread=0.4):
    """Return base ± spread*base seconds."""
    return base * (1 + random.uniform(-spread, spread))


# ── auth / token refresh ──────────────────────────────────────────────────────

_token = None
_token_ts = 0
TOKEN_TTL = 3600  # seconds


def get_token():
    global _token, _token_ts
    if _token and (time.time() - _token_ts) < TOKEN_TTL:
        return _token
    status, resp = http("POST", "/api/v1/login", {"username": USER, "password": PASS})
    if status == 200:
        _token = resp.get("access_token")
        _token_ts = time.time()
        log("auth", "Token refreshed")
    else:
        log("auth", f"Login failed ({status})", ok=False)
    return _token


# ── flow ID loader ────────────────────────────────────────────────────────────

_flow_ids = None


def load_flow_ids():
    global _flow_ids
    if _flow_ids:
        return _flow_ids
    for attempt in range(30):
        if os.path.exists(IDS_FILE):
            with open(IDS_FILE) as f:
                _flow_ids = json.load(f)
            log("init", f"Loaded flow IDs: {_flow_ids}")
            return _flow_ids
        log("init", f"Waiting for bootstrap... ({attempt+1}/30)")
        time.sleep(10)
    raise RuntimeError("Bootstrap never completed — flow_ids.json not found.")


# ── chat messages corpus ──────────────────────────────────────────────────────

CHAT_MESSAGES = [
    "Hello! Can you help me with something?",
    "What can this assistant do?",
    "Tell me a fun fact.",
    "How does natural language processing work?",
    "What's the weather like today?",
    "Can you summarise this for me?",
    "I need help drafting an email.",
    "What are best practices for API security?",
    "Explain machine learning in simple terms.",
    "Who invented the internet?",
    "What is a large language model?",
    "Help me debug my Python code.",
    "What is the difference between REST and GraphQL?",
    "Can you write a haiku about coffee?",
    "What does this error mean?",
    "Give me three ideas for a weekend project.",
    "Translate 'hello' into French.",
    "What time is it in Tokyo?",
    "Explain Docker containers simply.",
    "How do I center a div in CSS?",
]

WEBHOOK_PAYLOADS = [
    {"event": "user.signup", "user_id": "u_001", "email": "alice@example.com"},
    {"event": "order.placed", "order_id": "ord_882", "amount": 49.99},
    {"event": "alert.triggered", "severity": "medium", "source": "monitoring"},
    {"event": "file.uploaded", "filename": "report_q3.pdf", "size_kb": 412},
    {"event": "task.completed", "task_id": "t_772", "duration_ms": 1840},
    {"event": "login.failed", "ip": "203.0.113.45", "attempts": 3},
    {"event": "payment.succeeded", "txn_id": "txn_5512", "currency": "USD"},
    {"event": "session.ended", "session_id": "sess_991", "duration_s": 342},
]


# ── traffic actions ───────────────────────────────────────────────────────────

def action_chat(flow_ids, token):
    """Authenticated chat run via /api/v1/run/{flow_id}."""
    flow_id = flow_ids["echo_chat"]
    msg = random.choice(CHAT_MESSAGES)
    payload = {
        "input_value": msg,
        "input_type": "chat",
        "output_type": "chat",
    }
    status, _ = http("POST", f"/api/v1/run/{flow_id}", payload, token=token)
    log("chat", f"'{msg[:40]}...' → {status}", ok=status in (200, 201, 202))


def action_build_public(flow_ids):
    """Unauthenticated build_public_tmp — legitimate call, no data param."""
    flow_id = flow_ids["echo_chat"]
    payload = {
        "inputs": [{"input_value": random.choice(CHAT_MESSAGES), "components": []}]
    }
    status, _ = http("POST", f"/api/v1/build_public_tmp/{flow_id}/flow", payload)
    log("public_build", f"flow={flow_id[:8]}… → {status}", ok=status in (200, 201, 202))


def action_webhook(flow_ids, token):
    """Webhook trigger against the webhook flow."""
    flow_id = flow_ids["webhook_logger"]
    payload = random.choice(WEBHOOK_PAYLOADS)
    status, _ = http("POST", f"/api/v1/webhook/{flow_id}", payload, token=token)
    log("webhook", f"event={payload.get('event','?')} → {status}", ok=status in (200, 201, 202))


def action_introspect(token):
    """Light read-only introspection calls."""
    choice = random.random()
    if choice < 0.5:
        status, resp = http("GET", "/api/v1/version")
        ver = resp.get("version", "?")
        log("introspect", f"version={ver} → {status}", ok=status == 200)
    else:
        status, _ = http("GET", "/api/v1/flows/?page=1&size=10", token=token)
        log("introspect", f"flows list → {status}", ok=status == 200)


# ── weighted action dispatcher ────────────────────────────────────────────────

ACTIONS = [
    (0.50, "chat"),
    (0.25, "public_build"),
    (0.15, "webhook"),
    (0.10, "introspect"),
]


def pick_action():
    r = random.random()
    cumulative = 0.0
    for weight, name in ACTIONS:
        cumulative += weight
        if r < cumulative:
            return name
    return "introspect"


# ── session simulator ─────────────────────────────────────────────────────────

def run_session(flow_ids):
    """
    Simulate a user session: 3–8 actions with human-like gaps between them.
    """
    token = get_token()
    n_actions = random.randint(3, 8)
    log("session", f"Starting session ({n_actions} actions)")

    for _ in range(n_actions):
        action = pick_action()
        try:
            if action == "chat":
                action_chat(flow_ids, token)
            elif action == "public_build":
                action_build_public(flow_ids)
            elif action == "webhook":
                action_webhook(flow_ids, token)
            else:
                action_introspect(token)
        except Exception:
            log("error", traceback.format_exc(), ok=False)

        # Human think-time between actions: 2–12 s
        time.sleep(jitter(random.uniform(2, 12)))


# ── main loop ─────────────────────────────────────────────────────────────────

def main():
    log("sim", "Simulator starting — waiting for bootstrap...")
    flow_ids = load_flow_ids()

    # Stagger startup slightly so multiple restarts don't sync up
    time.sleep(jitter(5))

    log("sim", "Beginning traffic generation")
    session_count = 0

    while True:
        try:
            run_session(flow_ids)
            session_count += 1
            log("sim", f"Session {session_count} complete")
        except Exception:
            log("sim", f"Session error:\n{traceback.format_exc()}", ok=False)

        # Gap between sessions: 15–90 s (simulates users arriving independently)
        gap = jitter(random.uniform(15, 90))
        log("sim", f"Next session in {gap:.0f}s")
        time.sleep(gap)


if __name__ == "__main__":
    main()
