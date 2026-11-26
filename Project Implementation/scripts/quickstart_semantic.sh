#!/usr/bin/env bash
# Quickstart for the Semantic Web part (Milestone 5): from a fresh clone to a running demo.
#   1. Python environment and dependencies
#   2. ontology (TBox) + knowledge graph (ABox) as RDF/XML
#   3. a Virtuoso triple store: an already running one, else a Docker container,
#      else the embedded rdflib store (no server)
#   4. load the graph, run the SPARQL demonstration, start the web UI on port 5001
# Usage:  bash scripts/quickstart_semantic.sh [--full] [--no-ui]
set -euo pipefail
cd "$(dirname "$0")/.."

FULL=""; UI=1
for a in "$@"; do case "$a" in --full) FULL="--full";; --no-ui) UI=0;; esac; done
ENDPOINT="${VIRTUOSO_ENDPOINT:-http://localhost:8890/sparql}"

echo "== 1/4 Python environment"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate
pip install -q -r requirements.txt

echo "== 2/4 Ontology and knowledge graph files"
python main.py kg-ontology
python main.py kg-build $FULL

echo "== 3/4 Triple store"
up() { curl -s -o /dev/null -w "%{http_code}" --data-urlencode "query=ASK {}" "$ENDPOINT" 2>/dev/null | grep -q 200; }
BACKEND=local
start_docker() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 || return 1
  echo "Starting Virtuoso in Docker (container 'csc501-virtuoso', dba password 'dba') ..."
  docker start csc501-virtuoso >/dev/null 2>&1 || docker run -d --name csc501-virtuoso \
      -p 8890:8890 -p 1111:1111 -e DBA_PASSWORD=dba openlink/virtuoso-opensource-7:latest >/dev/null || return 1
  for i in $(seq 1 60); do up && break; sleep 2; done
  up || { echo "Virtuoso did not start; see: docker logs csc501-virtuoso"; return 1; }
  # manual 5.2.3: let the SPARQL account update graphs (same as Conductor -> Users -> SPARQL)
  docker exec csc501-virtuoso isql 1111 dba dba \
      exec="GRANT SPARQL_UPDATE TO \"SPARQL\"; DB.DBA.RDF_DEFAULT_USER_PERMS_SET ('nobody', 7);" >/dev/null
}
if up; then
  echo "Virtuoso is running at $ENDPOINT"; BACKEND=virtuoso
elif start_docker; then
  BACKEND=virtuoso
else
  echo "No reachable Virtuoso (and Docker could not start one): using the embedded rdflib store (KG_BACKEND=local)."
fi
export KG_BACKEND=$BACKEND

echo "== 4/4 Load, demonstrate, serve"
python main.py kg-load $FULL
python main.py kg-demo
python main.py kg-check || true
if [ "$UI" = 1 ]; then
  echo "Web UI: http://127.0.0.1:5001  (Ctrl+C to stop)"
  python main.py kg-ui
fi
