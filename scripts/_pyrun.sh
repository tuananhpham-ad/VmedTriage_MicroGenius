#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Designed to be called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no working Python is found; hooks must never block pushes.
set -u

works() {
  # shellcheck disable=SC2086
  $1 --version >/dev/null 2>&1
}

PY=""
for cand in \
  "./.venv/Scripts/python.exe" \
  "./.venv/bin/python" \
  python3 \
  python \
  "py -3"; do
  if command -v ${cand%% *} >/dev/null 2>&1 && works "$cand"; then
    PY="$cand"
    break
  fi
done

if [ -z "$PY" ]; then
  # PATH lookup failed or found only Windows app aliases; probe standard Windows
  # install locations.
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    if [ -x "$cand" ] && "$cand" --version >/dev/null 2>&1; then
      PY="$cand"
      break
    fi
  done
  shopt -u nullglob 2>/dev/null || true
  [ -n "$PY" ] || exit 0
fi

# shellcheck disable=SC2086
exec $PY "$@"
