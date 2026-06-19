#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Starting CRM Intelligence Desk agents..."

# Clear old pipeline log for a clean demo
> logs/pipeline.jsonl
echo "✅ Cleared logs/pipeline.jsonl"

python agents/auditor.py &
AUDITOR_PID=$!
echo "▶  Auditor  started (PID $AUDITOR_PID)"

python agents/enricher.py &
ENRICHER_PID=$!
echo "▶  Enricher started (PID $ENRICHER_PID)"

python agents/syncer.py &
SYNCER_PID=$!
echo "▶  Syncer   started (PID $SYNCER_PID)"

python agents/reporter.py &
REPORTER_PID=$!
echo "▶  Reporter started (PID $REPORTER_PID)"

echo ""
echo "All 4 agents running. Go to your Band room and @mention @auditor with 'run audit'."
echo "Press Ctrl+C to stop all agents."

# Trap Ctrl+C to kill all background jobs
trap "echo 'Stopping all agents...'; kill $AUDITOR_PID $ENRICHER_PID $SYNCER_PID $REPORTER_PID 2>/dev/null; exit 0" INT

wait
