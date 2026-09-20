#!/bin/bash
# Pen & Ink Tracker launcher for macOS.
# Double-click this file in Finder to check for Python, run first-time
# setup once, start the local server, and open the app in your browser.

cd "$(dirname "$0")" || exit 1

fail() {
    echo ""
    echo "$1"
    echo ""
    echo "Press Return to close this window..."
    read -r _
    exit 1
}

echo "Pen & Ink Tracker - checking that Python 3 is installed..."
echo ""

if ! command -v python3 >/dev/null 2>&1; then
    fail "Python 3 was not found on this Mac.
Pen & Ink Tracker needs Python 3 to run. It is free and takes about a
minute to install: https://www.python.org/downloads/
Once it is installed, double-click this file again."
fi

echo "Found: $(python3 --version)"
echo ""

echo "Running first-time setup (only asks questions the first time)..."
python3 setup_first_run.py || fail "First-run setup reported a problem - see above."

echo ""
echo "Starting the Pen & Ink Tracker server..."
echo "(Leave this window open while you use the app. Close it, or press"
echo "Ctrl+C, to stop the app.)"
echo ""

# Give the server a moment to bind the port, then open the browser.
( sleep 1; open "http://localhost:3838" ) &

python3 server.py

echo ""
echo "The server has stopped."
echo "Press Return to close this window..."
read -r _
