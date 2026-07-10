#!/usr/bin/env bash
# Live smoke test. Requires: Ollama running with both models pulled, and the
# service started (uv run uvicorn app.main:app). Usage: scripts/smoke.sh [base-url]
set -euo pipefail
BASE_URL="${1:-http://localhost:8000}"

echo "== health =="
curl -sf "$BASE_URL/health" | python3 -m json.tool

echo "== Site 3 (en-GB): the assignment's example query =="
curl -sf "$BASE_URL/chat" -X POST -H 'Content-Type: application/json' \
  -d '{"site_id": 3, "query": "best dry food for a puppy with a sensitive stomach"}' | python3 -m json.tool

echo "== Site 1 (de-DE): German product query =="
curl -sf "$BASE_URL/chat" -X POST -H 'Content-Type: application/json' \
  -d '{"site_id": 1, "query": "Ball zum Apportieren für meinen Hund"}' | python3 -m json.tool

echo "== Site 15 (es-ES): Spanish product query =="
curl -sf "$BASE_URL/chat" -X POST -H 'Content-Type: application/json' \
  -d '{"site_id": 15, "query": "pienso para perros con sobrepeso"}' | python3 -m json.tool

echo "== off-topic query -> polite decline, empty products =="
curl -sf "$BASE_URL/chat" -X POST -H 'Content-Type: application/json' \
  -d '{"site_id": 3, "query": "What is the weather today?"}' | python3 -m json.tool

echo "== unknown Site -> 404 =="
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/chat" -X POST \
  -H 'Content-Type: application/json' -d '{"site_id": 7, "query": "dog food"}')
echo "HTTP $code (expected 404)"
test "$code" = "404"

echo "== smoke OK =="
