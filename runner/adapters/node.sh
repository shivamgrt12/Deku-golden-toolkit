#!/bin/sh
# G8 adapter for Node / TypeScript apps. Runs in a throwaway container from the
# APP image, where the manifest's install has already produced node_modules.
DIR=/app
for d in /app /app/server /app/web /app/frontend /app/client; do
  [ -f "$d/package.json" ] && DIR="$d" && break
done
cd "$DIR" || exit 0
if [ -f tsconfig.json ]; then
  echo "=== tsc --noEmit ($DIR)"
  if [ -x node_modules/.bin/tsc ]; then node_modules/.bin/tsc --noEmit -p .
  else npx --yes -p typescript@5.6.3 tsc --noEmit -p .; fi
  echo "GOLDEN-RESULT tsc $?"
fi
echo "=== knip (unused files, exports, dependencies)"
# knip loads TypeScript as a peer. Unpinned, npx resolves the newest one (7.x dropped
# the compiler API knip uses), so pin it: the app's own version when installed.
TS_VER=$(node -p "require('./node_modules/typescript/package.json').version" 2>/dev/null || echo 5.7.3)
npx --yes -p knip@5.64.1 -p "typescript@$TS_VER" knip --no-progress --reporter compact
echo "GOLDEN-RESULT knip $?"
