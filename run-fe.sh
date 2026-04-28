#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# run-fe.sh — Install deps & start the Pantry Chef frontend
# ─────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR/frontend"

# ── Install npm dependencies if needed ────────────────────────────
if [ ! -d "node_modules" ]; then
  echo "⚙  Installing frontend dependencies..."
  npm install
fi

# ── Start Vite dev server ─────────────────────────────────────────
echo ""
echo "✓ Frontend starting on http://localhost:5174"
echo ""

npm run dev
