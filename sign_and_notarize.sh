#!/bin/bash
#
# sign_and_notarize.sh — make the built .app open on any Mac with no warning.
#
#   1. Sign every binary inside dist/Statement Splitter.app (inside-out) with
#      the Developer ID Application certificate, Hardened Runtime on.
#   2. Build the DMG (via build_dmg.sh) and sign it too.
#   3. Submit the DMG to Apple's notary service and wait for the verdict.
#   4. Staple the notarization ticket to both the .app and the .dmg.
#
# One-time prerequisites on this Mac (see CLAUDE.md "Releasing"):
#   - "Developer ID Application: Sather Flynn (MW9D3L254H)" in the login keychain
#   - xcrun notarytool store-credentials statement-splitter-notary
#
# Usage:  ./sign_and_notarize.sh              (after: python setup.py py2app --no-strip)
#         ./sign_and_notarize.sh --sign-only  (sign the .app and stop; no DMG, no Apple)
set -euo pipefail
SIGN_ONLY=0; [ "${1:-}" = "--sign-only" ] && SIGN_ONLY=1

APP_NAME="Statement Splitter"
TEAM_ID="MW9D3L254H"
PROFILE="statement-splitter-notary"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
APP="dist/${APP_NAME}.app"
VERSION="$(./venv/bin/python -c "from version import APP_VERSION; print(APP_VERSION)")"
DMG="dist/Statement-Splitter-${VERSION}.dmg"
ENT="entitlements.plist"

[ -d "$APP" ] || { echo "ERROR: $APP not found — build it first (python setup.py py2app --no-strip)"; exit 1; }

IDENTITY="$(security find-identity -v -p codesigning | grep "Developer ID Application" | grep "$TEAM_ID" | head -1 | sed -E 's/.*"(.*)".*/\1/')"
[ -n "$IDENTITY" ] || { echo "ERROR: no 'Developer ID Application' certificate for team $TEAM_ID in the keychain."; exit 1; }
echo "Signing with: $IDENTITY"

sign() {  # sign one item; --force replaces py2app's ad-hoc signature
  codesign --force --options runtime --timestamp --entitlements "$ENT" --sign "$IDENTITY" "$1"
}

# --- 1. Sign inside-out: loose binaries first, then frameworks, then the app.
echo "Signing nested binaries…"
find "$APP/Contents" -type f \( -name "*.so" -o -name "*.dylib" \) -print0 | while IFS= read -r -d '' f; do sign "$f"; done
# Executables without an extension inside Frameworks / Resources (python, etc.)
find "$APP/Contents/Frameworks" "$APP/Contents/Resources" -type f -perm -u+x ! -name "*.so" ! -name "*.dylib" ! -name "*.py" ! -name "*.sh" -print0 \
  | while IFS= read -r -d '' f; do
      if file "$f" | grep -q "Mach-O"; then sign "$f"; fi
    done
for fw in "$APP"/Contents/Frameworks/*.framework; do
  [ -d "$fw" ] && sign "$fw"
done
# py2app puts a helper interpreter ("python") next to the main executable in
# Contents/MacOS. Everything there except the main executable must be signed
# on its own — the main one is signed as part of the bundle below.
MAIN_EXE="$(/usr/libexec/PlistBuddy -c "Print :CFBundleExecutable" "$APP/Contents/Info.plist")"
for f in "$APP"/Contents/MacOS/*; do
  [ "$(basename "$f")" = "$MAIN_EXE" ] && continue
  if file "$f" | grep -q "Mach-O"; then sign "$f"; fi
done
echo "Signing the app…"
sign "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
echo "App signature verified."
if [ "$SIGN_ONLY" = "1" ]; then echo "(--sign-only: stopping here)"; exit 0; fi

# --- 2. DMG
GUIDE_FLAGS=--notarized ./build_dmg.sh
codesign --force --timestamp --sign "$IDENTITY" "$DMG"

# --- 3. Notarize (Apple's automated scan; usually 1–5 minutes)
echo "Submitting to Apple for notarization…"
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait

# --- 4. Staple so the verdict travels with the files (works offline).
xcrun stapler staple "$APP"
xcrun stapler staple "$DMG"
echo ""
echo "Gatekeeper check:"
spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG" || true
spctl --assess --type execute --verbose=2 "$APP" || true
echo ""
echo "Done → $DMG is signed, notarized and stapled. Ready for GitHub Releases."
