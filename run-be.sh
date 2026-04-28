#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# run-be.sh — Set up conda env & start the Pantry Chef backend
# ─────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_NAME="pantry-chef"
PYTHON_VERSION="3.12"

# ── Navigate to backend directory ──────────────────────────────────
cd "$SCRIPT_DIR/backend"

# ── Check for .env ─────────────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo "⚠  .env file not found. Copying from .env.example..."
  cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
  echo "   Edit $SCRIPT_DIR/.env and add your ANTHROPIC_API_KEY, then re-run."
  exit 1
fi

# ── Create conda environment if it doesn't exist ───────────────────
if conda env list | grep -q "^${ENV_NAME} "; then
  echo "✓ Conda environment '${ENV_NAME}' already exists"
else
  echo "⚙  Creating conda environment '${ENV_NAME}' (Python ${PYTHON_VERSION})..."
  conda create -n "$ENV_NAME" python="$PYTHON_VERSION" -y
fi

# ── Install Python dependencies ────────────────────────────────────
echo "⚙  Installing backend dependencies..."
conda run -n "$ENV_NAME" pip install -r requirements.txt --quiet

# ── Start uvicorn ──────────────────────────────────────────────────
echo ""
echo "✓ Backend starting on http://localhost:8001"
echo "  Health check: http://localhost:8001/health"
echo ""

conda run -n "$ENV_NAME" uvicorn main:app --reload --port 8001
