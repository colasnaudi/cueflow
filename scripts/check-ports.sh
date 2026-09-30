#!/usr/bin/env bash
# Fail fast with a readable message when the API or web port is already taken.
status=0
for port in "$@"; do
  if pid=$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1) && [ -n "$pid" ]; then
    echo "Port $port is already used by PID $pid: $(ps -o command= -p "$pid" | cut -c1-120)"
    echo "  -> stop it with: kill $pid"
    status=1
  fi
done
exit $status
