#!/bin/zsh
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print "The Python environment is missing. See README.md for setup instructions."
  read -k 1
  exit 1
fi
if /usr/bin/curl --silent --fail --max-time 2 http://127.0.0.1:8765/api/status >/dev/null; then
  open http://127.0.0.1:8765
  exit 0
fi
# Open only once the server is ready, so a fresh launch does not show an error page.
(
  for attempt in {1..40}; do
    if /usr/bin/curl --silent --fail --max-time 1 http://127.0.0.1:8765/api/status >/dev/null; then
      open http://127.0.0.1:8765
      break
    fi
    sleep 0.25
  done
) &
exec .venv/bin/python -m medlock_lab serve
