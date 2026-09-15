#!/bin/bash
# build_dmg.sh — package Statement Splitter as a drag-to-install DMG.
#
# Unsigned by itself; sign_and_notarize.sh calls this after signing the .app
# and then signs/notarizes the DMG. For an unsigned build the Install Guide
# inside the DMG walks through the one-time "Open Anyway" step; pass
# --notarized (sign_and_notarize.sh does) to drop that section.
#
# Usage:  ./build_dmg.sh        (builds the .app first if it's missing)
# Output: dist/Statement-Splitter-<version>.dmg  (no spaces: GitHub would
#         otherwise rename the download to "Statement.Splitter.dmg")
set -euo pipefail
APP_NAME="Statement Splitter"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
PY="./venv/bin/python"

APP="dist/${APP_NAME}.app"
VERSION="$("$PY" -c "from version import APP_VERSION; print(APP_VERSION)")"
DMG="dist/Statement-Splitter-${VERSION}.dmg"
GUIDE="Install Guide (Mac).pdf"

if [ ! -d "$APP" ]; then
  echo "Building the .app first…"
  rm -rf build "$APP"
  "$PY" setup.py py2app --no-strip >/dev/null
fi

echo "Generating install guide…"
"$PY" make_install_guide.py "$GUIDE" ${GUIDE_FLAGS:-}

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
cp "$GUIDE" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
find "$STAGE" -name ".DS_Store" -delete 2>/dev/null || true

rm -f dist/*.dmg
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$DMG" >/dev/null
echo "Done  →  $DMG  ($(du -h "$DMG" | cut -f1 | tr -d ' '))"
