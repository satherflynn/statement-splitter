#!/usr/bin/env bash
# Double-click this file in Finder to run Statement Splitter from source.
# (Only needed on a Mac that has the code checked out; Steve gets the .app.)
set -e
cd "$(dirname "$0")"
if [ ! -d venv ]; then
    echo "First run — setting up (one-time, about 30 seconds)…"
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q --upgrade pip >/dev/null 2>&1 || true
pip install -q -r requirements.txt
echo ""
echo "Launching Statement Splitter… (you can close this window once the app appears)"
python app.py
