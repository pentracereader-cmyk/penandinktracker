@echo off
cd /d "%~dp0"
echo Starting Pen ^& Ink Tracker...
echo.
echo Desktop:  http://localhost:3838
echo Phone:    see the address printed below (same Wi-Fi) - this is what the QR encodes
echo.
echo Press Ctrl+C to stop the server when done.
echo.
start "" "http://localhost:3838"
python tracker\server.py
pause
