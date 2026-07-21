#!/usr/bin/env bash
# Build the OpenMob debugger testbed for the iOS simulator (no Xcode project needed).
# Usage: ./build.sh [UDID]  — installs+launches into the booted sim (or the given one).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
APP_DIR="${BUILD_DIR}/tb.app"
UDID="${1:-booted}"
BUNDLE_ID="ai.zevnix.openmob.testbed"

rm -rf "${APP_DIR}"
mkdir -p "${APP_DIR}"

xcrun -sdk iphonesimulator clang -fobjc-arc -g -O0 \
    -mios-simulator-version-min=15.0 \
    -framework UIKit -framework Foundation \
    -o "${APP_DIR}/tb" "${SCRIPT_DIR}/main.m"
cp "${SCRIPT_DIR}/Info.plist" "${APP_DIR}/Info.plist"
codesign --force --sign - "${APP_DIR}"

xcrun simctl install "${UDID}" "${APP_DIR}"
xcrun simctl launch "${UDID}" "${BUNDLE_ID}"
echo "Installed and launched ${BUNDLE_ID}"
