#!/bin/bash
# Pen & Ink Tracker launcher for Linux.
# Run this from a terminal (./start-linux.sh) to check for Python, run
# first-time setup once, start the local server, and open the app in
# your browser.

cd "$(dirname "$0")" || exit 1

fail() {
    echo ""
    echo "$1"
    echo ""
    echo "Press Enter to close..."
    read -r _
    exit 1
}

echo "Pen & Ink Tracker - checking that Python 3 is installed..."
echo ""

if ! command -v python3 >/dev/null 2>&1; then
    fail "Python 3 was not found on this computer.
Pen & Ink Tracker needs Python 3 to run. Install it with your distro's
package manager (for example: sudo apt install python3) or get it from
https://www.python.org/downloads/
Once it is installed, run this script again."
fi

echo "Found: $(python3 --version)"
echo ""

echo "Running first-time setup (only asks questions the first time)..."
python3 setup_first_run.py || fail "First-run setup reported a problem - see above."

echo ""
echo "Starting the Pen & Ink Tracker server..."
echo "(Leave this terminal open while you use the app. Press Ctrl+C to"
echo "stop the app.)"
echo ""

# Try to open a browser automatically; harmless if none is available.
( sleep 1
  if command -v xdg-open >/dev/null 2>&1; then
      xdg-open "http://localhost:3838" >/dev/null 2>&1
  fi
) &

python3 server.py

echo ""
echo "The server has stopped."
echo "Press Enter to close..."
read -r _
