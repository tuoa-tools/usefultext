#!/bin/bash
# The app end to end against real photos, with a crash in the middle:
#   tools/api_smoke.sh <folder of page photos> [work folder]
# Starts the API on a spare port with its own app-data and library folders,
# creates a document from the folder, starts reading, kill -9s the server
# once two pages are done, restarts it, resumes, sorts by printed number,
# corrects a line and pulls every export. Needs curl and python3; run it
# from the repo root with the venv installed (pip install -e ".[dev]").
set -u
PHOTOS="${1:?usage: tools/api_smoke.sh <photos folder> [work folder]}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S="${2:-$ROOT/output_smoke}"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python3
UVICORN="$ROOT/.venv/bin/uvicorn"; [ -x "$UVICORN" ] || UVICORN=uvicorn
PORT="${PORT:-8765}"
rm -rf "$S"; mkdir -p "$S"
export USEFULTEXT_DATA_DIR="$S/appdata"
cd "$ROOT" || exit 1

py() { python3 -c "import sys,json; d=json.load(sys.stdin); $1"; }
api() { curl -s -X "$1" "http://127.0.0.1:$PORT$2" -H 'content-type: application/json' ${3:+-d "$3"}; }
start_server() {
  nohup "$UVICORN" app.main:app --port "$PORT" --log-level warning > "$S/server-$1.log" 2>&1 &
  echo $! > "$S/server.pid"   # uvicorn's own pid (no wrapper subshell), so kill -9 hits the server
  for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PORT/api/health" > /dev/null && return; sleep 0.25; done
  echo "server did not start:"; cat "$S/server-$1.log"; exit 1
}
stop_server() { kill "$(cat "$S/server.pid")" 2>/dev/null; sleep 0.5; }
wait_engine() { for i in $(seq 1 120); do st=$(api GET /api/health | py "print(d['engine']['state'])"); [ "$st" = ready ] && break; sleep 0.5; done; echo "engine: $st"; }
doc_line() { api GET "/api/documents/$DOC" | py "print('status', d['status'], '| read', d['read'], 'of', d['included'], '| eta', (d['progress'] or {}).get('eta_seconds'), '| current', (d['progress'] or {}).get('current'))"; }
trap stop_server EXIT

start_server 1
api PUT /api/settings "{\"library_dir\": \"$S/Library\"}" > /dev/null
DOC=$(api POST /api/library '{"title": "Smoke test"}' | py "print(d['id'])")
echo "document $DOC in $S/Library"
api POST "/api/documents/$DOC/add-path" "{\"path\": \"$(cd "$PHOTOS" && pwd)\"}" | py "print('added', len(d['added']), 'page(s); blurry pre-check:', [p['blurry'] for p in d['pages']])"
wait_engine
api POST "/api/documents/$DOC/start" '{}' > /dev/null
for i in $(seq 1 600); do n=$(api GET "/api/documents/$DOC" | py "print(d['read'])"); [ "$n" -ge 2 ] && break; sleep 0.5; done
doc_line
echo "--- kill -9 the server mid-read ---"
kill -9 "$(cat "$S/server.pid")"; sleep 1
ps -p "$(cat "$S/server.pid")" > /dev/null 2>&1 && echo "server STILL ALIVE (bug in this script)" || echo "server gone"
start_server 2
echo -n "after restart: "; doc_line
wait_engine
api POST "/api/documents/$DOC/resume" '{}' > /dev/null
for i in $(seq 1 1200); do st=$(api GET "/api/documents/$DOC" | py "print(d['status'])"); [ "$st" = done ] && break; sleep 0.5; done
doc_line
api GET "/api/documents/$DOC" | py "
print('last_run:', {k: d['last_run'][k] for k in ('processed','resumed','failed','stopped_early','elapsed')})
[print('  warning:', w['message'][:120]) for w in d['warnings']]"
echo "--- sort by printed number ---"
api POST "/api/documents/$DOC/pages/sort" '{"by": "printed"}' | py "[print('  note:', n) for n in d['notes']]; print('order:', [(p['position'], (p['read'] or {}).get('printed_page')) for p in d['pages']])"
PID=$(api GET "/api/documents/$DOC" | py "print(next(p['id'] for p in d['pages'] if p['read'] and p['read']['status'] == 'done'))")
api GET "/api/documents/$DOC/pages/$PID" | py "print('page', d['position'], ':', len(d['lines']), 'lines | first:', d['lines'][0]['text'][:60], '| preview', d['read']['preview'])"
api PUT "/api/documents/$DOC/pages/$PID/lines/1" '{"text": "A corrected line, by hand."}' | py "print('corrected:', d['origin'], '|', d['corrected'])"
api GET "/api/documents/$DOC/export/md" | grep -c "A corrected line, by hand." | sed 's/^/markdown mentions the correction: /'
for kind in txt jsonl csv pages.zip; do curl -s -o /dev/null -w "export $kind: HTTP %{http_code}, %{size_download} bytes\n" "http://127.0.0.1:$PORT/api/documents/$DOC/export/$kind"; done
curl -s -o /dev/null -w "thumbnail: HTTP %{http_code}, %{size_download} bytes\n" "http://127.0.0.1:$PORT/api/documents/$DOC/previews/$PID.thumb.jpg"
echo "--- outputs in $S/Library/Smoke test ---"; ls "$S/Library/Smoke test"
