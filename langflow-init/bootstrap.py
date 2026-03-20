#!/usr/bin/env python3
"""
Bootstrap script — runs once after Langflow is healthy.
Creates two flows and marks them as public so the
build_public_tmp endpoint is active and reachable.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = "http://langflow:7860"
USER = "admin"
PASS = "testpass123"
STATE_FILE = "/data/.bootstrapped"


def log(msg):
    print(f"[bootstrap] {msg}", flush=True)


def request(method, path, body=None, token=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log(f"HTTP {e.code} on {method} {path}: {body}")
        raise


def get_token():
    resp = request("POST", "/api/v1/login", {"username": USER, "password": PASS})
    return resp["access_token"]


# ── Minimal flow definitions ──────────────────────────────────────────────────

ECHO_FLOW = {
    "name": "Echo Chat",
    "description": "Simple echo chatbot — baseline public flow",
    "is_component": False,
    "data": {
        "nodes": [
            {
                "id": "ChatInput-1",
                "type": "genericNode",
                "position": {"x": 100, "y": 200},
                "data": {
                    "type": "ChatInput",
                    "node": {
                        "display_name": "Chat Input",
                        "description": "Receives chat messages",
                        "base_classes": ["Message"],
                        "outputs": [{"name": "message", "display_name": "Message", "types": ["Message"]}],
                        "template": {
                            "input_value": {"type": "str", "value": "", "required": False, "display_name": "Message"},
                            "_type": "Component"
                        }
                    }
                }
            },
            {
                "id": "ChatOutput-1",
                "type": "genericNode",
                "position": {"x": 500, "y": 200},
                "data": {
                    "type": "ChatOutput",
                    "node": {
                        "display_name": "Chat Output",
                        "description": "Returns chat messages",
                        "base_classes": ["Message"],
                        "template": {
                            "input_value": {"type": "str", "value": "", "required": False, "display_name": "Message"},
                            "_type": "Component"
                        }
                    }
                }
            }
        ],
        "edges": [
            {
                "source": "ChatInput-1",
                "target": "ChatOutput-1",
                "sourceHandle": "ChatInput-1-message",
                "targetHandle": "ChatOutput-1-input_value"
            }
        ]
    }
}

WEBHOOK_FLOW = {
    "name": "Webhook Logger",
    "description": "Accepts webhook payloads — baseline public flow",
    "is_component": False,
    "data": {
        "nodes": [
            {
                "id": "Webhook-1",
                "type": "genericNode",
                "position": {"x": 100, "y": 200},
                "data": {
                    "type": "Webhook",
                    "node": {
                        "display_name": "Webhook Input",
                        "description": "Receives webhook data",
                        "base_classes": ["Data"],
                        "outputs": [{"name": "output_data", "display_name": "Data", "types": ["Data"]}],
                        "template": {"_type": "Component"}
                    }
                }
            },
            {
                "id": "ChatOutput-1",
                "type": "genericNode",
                "position": {"x": 500, "y": 200},
                "data": {
                    "type": "ChatOutput",
                    "node": {
                        "display_name": "Chat Output",
                        "description": "Returns output",
                        "base_classes": ["Message"],
                        "template": {
                            "input_value": {"type": "str", "value": "", "required": False, "display_name": "Message"},
                            "_type": "Component"
                        }
                    }
                }
            }
        ],
        "edges": []
    }
}


def create_and_publish(token, flow_def):
    # Create the flow
    resp = request("POST", "/api/v1/flows/", flow_def, token=token)
    flow_id = resp["id"]
    log(f"Created flow '{flow_def['name']}' → id={flow_id}")

    # Mark as public (is_public flag)
    request("PATCH", f"/api/v1/flows/{flow_id}", {"is_public": True}, token=token)
    log(f"Marked flow {flow_id} as public")

    return flow_id


def write_flow_ids(ids: dict):
    path = "/data/flow_ids.json"
    with open(path, "w") as f:
        json.dump(ids, f, indent=2)
    log(f"Flow IDs written to {path}")


def main():
    if os.path.exists(STATE_FILE):
        log("Already bootstrapped — skipping.")
        sys.exit(0)

    log("Starting bootstrap...")
    token = get_token()
    log("Authenticated OK")

    ids = {}
    ids["echo_chat"] = create_and_publish(token, ECHO_FLOW)
    ids["webhook_logger"] = create_and_publish(token, WEBHOOK_FLOW)

    write_flow_ids(ids)

    # Mark done
    with open(STATE_FILE, "w") as f:
        f.write("done\n")

    log("Bootstrap complete.")


if __name__ == "__main__":
    main()
