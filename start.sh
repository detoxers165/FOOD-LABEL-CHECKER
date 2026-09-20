#!/usr/bin/env bash
# ==============================================================================
# FOOD-LABEL-CHECKER — Unified Local Startup Script
# ==============================================================================
# Starts MongoDB, FastAPI backend, and Vite frontend from a single terminal.
# Handles graceful shutdown of started services on Ctrl+C.
# ==============================================================================

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "=================================================="
echo " Starting FOOD-LABEL-CHECKER Local Stack"
echo " Project: $PROJECT_ROOT"
echo "=================================================="

# ------------------------------------------------------------------------------
# 1. Environment & Dependency Validation
# ------------------------------------------------------------------------------
VENV_PYTHON="$PROJECT_ROOT/.venv311/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[Error] Python virtual environment not found at: $PROJECT_ROOT/.venv311"
    echo "Please verify .venv311 exists or set it up before running start.sh."
    exit 1
fi

if ! command -v node >/dev/null 2>&1; then
    echo "[Error] Node.js is not installed or not in PATH."
    echo "Please install Node.js (v18+) to run the frontend."
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "[Error] npm is not installed or not in PATH."
    echo "Please install npm to run the frontend."
    exit 1
fi

if [ ! -d "$PROJECT_ROOT/node_modules" ]; then
    echo "[Frontend] node_modules not found. Installing frontend dependencies..."
    npm install
fi

if [ ! -f "$PROJECT_ROOT/.env" ]; then
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        echo "[Config] .env not found. Creating default .env from .env.example..."
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    else
        echo "[Warning] No .env or .env.example found. Backend will use defaults."
    fi
fi

# ------------------------------------------------------------------------------
# 2. MongoDB Check & Startup
# ------------------------------------------------------------------------------
is_port_open() {
    local host="$1"
    local port="$2"
    if command -v nc >/dev/null 2>&1; then
        nc -z "$host" "$port" >/dev/null 2>&1
    else
        (exec 3<>/dev/tcp/"$host"/"$port") >/dev/null 2>&1
    fi
}

echo -n "[MongoDB] Checking status... "
if is_port_open 127.0.0.1 27017; then
    echo "Running on localhost:27017"
    STARTED_MONGO=false
else
    echo "Not running"
    echo "[MongoDB] Attempting to start MongoDB..."
    
    MONGOD_BIN="$(command -v mongod || true)"
    if [ -z "$MONGOD_BIN" ] && [ -x "/home/maulik-kalyan/.local/bin/mongod" ]; then
        MONGOD_BIN="/home/maulik-kalyan/.local/bin/mongod"
    fi
    
    CONF_FILE="/home/maulik-kalyan/.local/mongodb/mongod.conf"
    
    if [ -n "$MONGOD_BIN" ] && [ -f "$CONF_FILE" ]; then
        "$MONGOD_BIN" --config "$CONF_FILE" --fork >/dev/null 2>&1 || true
    elif [ -n "$MONGOD_BIN" ]; then
        "$MONGOD_BIN" --fork --logpath "$PROJECT_ROOT/mongodb.log" --dbpath "$PROJECT_ROOT/data/db" >/dev/null 2>&1 || true
    elif command -v systemctl >/dev/null 2>&1; then
        systemctl start mongod 2>/dev/null || systemctl start mongodb 2>/dev/null || true
    fi

    # Wait for MongoDB to become available
    MONGO_READY=false
    for i in {1..10}; do
        if is_port_open 127.0.0.1 27017; then
            MONGO_READY=true
            STARTED_MONGO=true
            break
        fi
        sleep 0.5
    done

    if [ "$MONGO_READY" = true ]; then
        echo "[MongoDB] Started successfully on localhost:27017"
    else
        echo "[Warning] Could not automatically start MongoDB on port 27017."
        echo "Please start MongoDB manually if database features are needed."
    fi
fi

# ------------------------------------------------------------------------------
# 3. Process Cleanup Traps (Ctrl+C)
# ------------------------------------------------------------------------------
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo "=================================================="
    echo " [Shutdown] Stopping FOOD-LABEL-CHECKER services..."
    echo "=================================================="
    
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo "[Frontend] Stopping Vite dev server (PID: $FRONTEND_PID)..."
        kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    fi

    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "[Backend] Stopping FastAPI server (PID: $BACKEND_PID)..."
        kill -TERM "$BACKEND_PID" 2>/dev/null || true
    fi

    # Give processes a brief moment to shut down gracefully
    sleep 0.5

    # Force kill if still running
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill -KILL "$FRONTEND_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill -KILL "$BACKEND_PID" 2>/dev/null || true
    fi

    echo "[Shutdown] All services stopped cleanly."
    exit 0
}

trap cleanup SIGINT SIGTERM

# ------------------------------------------------------------------------------
# 4. FastAPI Backend Check & Startup
# ------------------------------------------------------------------------------
echo -n "[Backend] Checking status... "
if is_port_open 127.0.0.1 8000 && curl -s http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "Already running on http://localhost:8000"
else
    echo "Starting..."
    # Check if port 8000 is occupied by something else
    if is_port_open 127.0.0.1 8000; then
        echo "[Warning] Port 8000 is already in use by another process."
        echo "Please free port 8000 or terminate conflicting services."
        exit 1
    fi

    "$VENV_PYTHON" "$PROJECT_ROOT/backend_api.py" > "$PROJECT_ROOT/.backend.log" 2>&1 &
    BACKEND_PID=$!

    # Wait for backend to be healthy
    BACKEND_HEALTHY=false
    for i in {1..30}; do
        if is_port_open 127.0.0.1 8000 && curl -s http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
            BACKEND_HEALTHY=true
            break
        fi
        if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo "[Error] Backend process terminated unexpectedly. Check .backend.log:"
            tail -n 20 "$PROJECT_ROOT/.backend.log"
            exit 1
        fi
        sleep 0.5
    done

    if [ "$BACKEND_HEALTHY" = true ]; then
        echo "[Backend] Running on http://localhost:8000"
    else
        echo "[Error] Backend failed to report healthy status within 15 seconds."
        tail -n 20 "$PROJECT_ROOT/.backend.log"
        exit 1
    fi
fi

# ------------------------------------------------------------------------------
# 5. Vite Frontend Check & Startup
# ------------------------------------------------------------------------------
echo -n "[Frontend] Checking status... "
if is_port_open 127.0.0.1 5173 && curl -s http://127.0.0.1:5173 >/dev/null 2>&1; then
    echo "Already running on http://localhost:5173"
else
    echo "Starting..."
    if is_port_open 127.0.0.1 5173; then
        echo "[Warning] Port 5173 is already in use by another process."
        echo "Please free port 5173 or terminate conflicting services."
        exit 1
    fi

    npm run dev > "$PROJECT_ROOT/.frontend.log" 2>&1 &
    FRONTEND_PID=$!

    # Wait for frontend dev server
    FRONTEND_HEALTHY=false
    for i in {1..20}; do
        if is_port_open 127.0.0.1 5173 && curl -s http://127.0.0.1:5173 >/dev/null 2>&1; then
            FRONTEND_HEALTHY=true
            break
        fi
        if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
            echo "[Error] Frontend process terminated unexpectedly. Check .frontend.log:"
            tail -n 20 "$PROJECT_ROOT/.frontend.log"
            exit 1
        fi
        sleep 0.5
    done

    if [ "$FRONTEND_HEALTHY" = true ]; then
        echo "[Frontend] Running on http://localhost:5173"
    else
        echo "[Error] Frontend failed to start within 10 seconds."
        tail -n 20 "$PROJECT_ROOT/.frontend.log"
        exit 1
    fi
fi

# ------------------------------------------------------------------------------
# 6. Ready Banner & Wait Loop
# ------------------------------------------------------------------------------
echo ""
echo "=================================================="
echo " 🎉 FOOD-LABEL-CHECKER application is ready!"
echo " 🌐 Open: http://localhost:5173"
echo " 📡 API:  http://localhost:8000/api/health"
echo "=================================================="
echo "Press [Ctrl+C] at any time to stop all services."
echo ""

# If both services were started by this script, wait on them
if [ -n "$BACKEND_PID" ] || [ -n "$FRONTEND_PID" ]; then
    # Keep script alive and monitor child processes
    while true; do
        if [ -n "$BACKEND_PID" ] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo "[Backend] Process exited unexpectedly."
            cleanup
        fi
        if [ -n "$FRONTEND_PID" ] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
            echo "[Frontend] Process exited unexpectedly."
            cleanup
        fi
        sleep 2
    done
else
    echo "Services are running independently in existing processes."
    echo "Use ./stop.sh if you wish to shut down running background services."
fi
