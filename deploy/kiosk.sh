#!/bin/sh
set -eu
# Only run inside a configured graphical session with its actual display driver.
if command -v chromium >/dev/null 2>&1; then
    browser=chromium
elif command -v chromium-browser >/dev/null 2>&1; then
    browser=chromium-browser
else
    echo 'Install Chromium for browser-display mode.' >&2
    exit 1
fi
attempt=0
until curl --silent --fail http://127.0.0.1:8767/api/state >/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo 'MedLock backend did not become ready.' >&2
        exit 1
    fi
    sleep 1
done
exec "$browser" --kiosk --no-first-run --force-device-scale-factor=1 http://127.0.0.1:8767/
