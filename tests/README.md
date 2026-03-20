# Test Matrix — CVE-2026-33017

## Overview

| ID     | Category      | Method             | Detection surface              | OOB needed |
|--------|---------------|--------------------|--------------------------------|------------|
| TC-01a | Baseline      | Legit public build | —                              | No         |
| TC-01b | Baseline      | Authenticated /run | —                              | No         |
| TC-02  | Basic RCE     | os.system          | Network + process behaviour    | No         |
| TC-03  | Basic RCE     | subprocess.run     | Network + process behaviour    | No         |
| TC-04  | Evasion       | base64 exec        | Network (payload obfuscated)   | No         |
| TC-05  | Evasion       | chr() import       | Network (import obfuscated)    | No         |
| TC-06  | Evasion       | exec(exec())       | Network (nested execution)     | No         |
| TC-07  | Evasion       | time.sleep + exec  | Process (delayed post-response)| No         |
| TC-08  | OOB / Canary  | HTTP callback      | Network egress                 | Yes        |
| TC-09  | OOB / Canary  | DNS lookup         | DNS egress                     | Yes        |
| TC-10  | OOB / Canary  | Unique tokens      | OOB log correlation            | Yes        |

---

## What "Pass" means

For **TC-02 through TC-10**, a "pass" means the endpoint returned HTTP 200/202
— i.e. the target accepted the malicious payload, confirming it is vulnerable.

Your detection tool should:
- **Alert** on TC-02 through TC-10
- **Not alert** on TC-01a and TC-01b

---

## Running the tests

### Prerequisites

```bash
# 1. Start the environment
docker compose up --build

# 2. Wait for bootstrap (~2 min), then copy flow IDs locally
docker exec langflow cat /data/flow_ids.json > tests/flow_ids.json
```

### pytest

```bash
pip install -r tests/requirements.txt
pytest tests/test_cve_2026_33017.py -v
```

With OOB:
```bash
OOB_HOST=abc.oast.me pytest tests/test_cve_2026_33017.py -v
```

### Standalone Python runner

```bash
python tests/run_tests.py
OOB_HOST=abc.oast.me python tests/run_tests.py
```

### curl

```bash
chmod +x tests/curl_tests.sh
./tests/curl_tests.sh
OOB_HOST=abc.oast.me ./tests/curl_tests.sh
```

---

## Verifying canary file writes inside the container

After running TC-02 / TC-03:

```bash
docker exec langflow ls /tmp/canary_*.txt
docker exec langflow cat /tmp/canary_tc02.txt
docker exec langflow cat /tmp/canary_tc03.txt
```

---

## OOB setup options

| Tool                  | Free | Notes                                     |
|-----------------------|------|-------------------------------------------|
| interactsh            | Yes  | `interactsh-client` CLI, self-hostable    |
| Burp Collaborator     | Pro  | Built into Burp Suite Pro                 |
| canarytokens.org      | Yes  | Web UI, no CLI needed                     |
| webhook.site          | Yes  | HTTP only, no DNS                         |

Set your host as `OOB_HOST` before running OOB tests:

```bash
export OOB_HOST=abcdef.oast.me
python tests/run_tests.py
```
