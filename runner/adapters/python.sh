#!/bin/sh
# G8 adapter for Python apps. Runs in a throwaway container from the APP image,
# so it sees exactly the dependencies the app installs. Each tool ends with a
# GOLDEN-RESULT line the host parses; a non-zero code is a finding.
cd /app || exit 0
if ! pip install --quiet --disable-pip-version-check --target /tmp/golden-tools \
     ruff==0.6.9 vulture==2.13 >/tmp/golden-pip.log 2>&1; then
  tail -5 /tmp/golden-pip.log
  echo "GOLDEN-RESULT install 1"
  exit 0
fi
export PYTHONPATH="/tmp/golden-tools${PYTHONPATH:+:$PYTHONPATH}"
EXCLUDE=".venv,venv,node_modules,__pycache__,.browser_screenshots,.downloads"
echo "=== ruff (pyflakes, syntax, bugbear)"
python -m ruff check --no-cache --output-format concise --select F,E9,B --extend-exclude "$EXCLUDE" .
echo "GOLDEN-RESULT ruff $?"
echo "=== vulture (dead code, confidence >= 80)"
python -m vulture . --min-confidence 80 --exclude "$EXCLUDE"
echo "GOLDEN-RESULT vulture $?"
echo "=== compileall"
python -m compileall -q -x '(\.venv|node_modules)' . >/tmp/golden-compile.log 2>&1
rc=$?; tail -20 /tmp/golden-compile.log
echo "GOLDEN-RESULT compileall $rc"
