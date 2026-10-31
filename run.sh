#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

# Go to the directory where the script is located
cd "$(dirname "$0")"

PROJECT_DIR=$(pwd)
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python3"

echo "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    echo "Please install Python 3 and run this script again."
    exit 1
fi

echo "Checking virtual environment..."
create_venv() {
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_PY" -m pip install --upgrade pip
}

if [ ! -f "$VENV_PY" ] || ! "$VENV_PY" -c "import sys" >/dev/null 2>&1; then
    if [ -d "$VENV_DIR" ]; then
        echo "Existing virtual environment is broken. Recreating..."
        rm -rf "$VENV_DIR"
    fi
    create_venv
else
    echo "Using existing virtual environment..."
fi

echo "Checking dependencies..."
"$VENV_PY" -m pip install -r requirements.txt

echo "Checking database..."
if [ ! -f "$PROJECT_DIR/database/app.db" ]; then
    echo "Database not found. Initializing..."
    "$VENV_PY" database/init_db.py
else
    echo "Database already exists."
fi

# Load environment variables from .env if it exists
if [ -f "$PROJECT_DIR/.env" ]; then
    set -o allexport
    source "$PROJECT_DIR/.env"
    set +o allexport
    echo "Loaded environment from .env"
fi

HOST=${FLASK_RUN_HOST:-127.0.0.1}
PORT=${FLASK_RUN_PORT:-5000}

echo "Starting application at http://${HOST}:${PORT}..."
"$VENV_PY" -c "from app import app; app.run(host='${HOST}', port=int(${PORT}), debug=False, use_reloader=False)"
