#!/usr/bin/env bash
# ==============================================================================
# FOOD-LABEL-CHECKER — Service Shutdown Script
# ==============================================================================
# Safely stops running local backend (port 8000) and frontend (port 5173) services.
# ==============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "=================================================="
echo " Stopping FOOD-LABEL-CHECKER Local Stack"
echo "=================================================="

# 1. Stop Frontend on Port 5173
FRONTEND_PIDS=$(lsof -ti :5173 2>/dev/null || true)
if [ -n "$FRONTEND_PIDS" ]; then
    echo "[Frontend] Stopping Vite dev server on port 5173 (PIDs: $FRONTEND_PIDS)..."
    kill -TERM $FRONTEND_PIDS 2>/dev/null || true
    sleep 0.5
    kill -9 $FRONTEND_PIDS 2>/dev/null || true
    echo "[Frontend] Stopped."
else
    echo "[Frontend] No process running on port 5173."
fi

# 2. Stop Backend on Port 8000
BACKEND_PIDS=$(lsof -ti :8000 2>/dev/null || true)
if [ -n "$BACKEND_PIDS" ]; then
    echo "[Backend] Stopping FastAPI server on port 8000 (PIDs: $BACKEND_PIDS)..."
    kill -TERM $BACKEND_PIDS 2>/dev/null || true
    sleep 0.5
    kill -9 $BACKEND_PIDS 2>/dev/null || true
    echo "[Backend] Stopped."
else
    echo "[Backend] No process running on port 8000."
fi

echo "=================================================="
echo " All specified project services stopped."
echo " Note: MongoDB daemon was kept running."
echo "=================================================="
