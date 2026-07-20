#!/usr/bin/env bash
#
# setup-wda.sh — clone, build, and install WebDriverAgent onto a connected iPhone.
#
# Usage:   ./setup-wda.sh [UDID]
#   UDID   Hardware UDID of the target iPhone (e.g. 00008101-...). Auto-detected
#          via pymobiledevice3 if omitted.
#
# Idempotent: skips the clone if the repo already exists; rebuild/reinstall are
# safe to repeat. See docs/IOS.md for the full guide.

set -euo pipefail

TEAM_ID="76Z3N79K53"
BUNDLE_ID="ai.zevnix.WebDriverAgentRunner"   # runner installs as ${BUNDLE_ID}.xctrunner
WDA_REPO_URL="https://github.com/appium/WebDriverAgent.git"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WDA_DIR="${ROOT_DIR}/runner/ios/WebDriverAgent"
DERIVED_DATA="${WDA_DIR}/build"

log()  { printf '[setup-wda] %s\n' "$*"; }
die()  { printf '[setup-wda] ERROR: %s\n' "$*" >&2; exit 1; }

# --- Preflight -------------------------------------------------------------

command -v xcodebuild >/dev/null 2>&1 || die "xcodebuild not found; install Xcode."
command -v git        >/dev/null 2>&1 || die "git not found."
command -v uvx        >/dev/null 2>&1 || die "uvx not found; install uv (brew install uv)."

# --- Clone (skip if present) ----------------------------------------------

if [[ -d "${WDA_DIR}/.git" ]]; then
    log "WebDriverAgent already cloned at ${WDA_DIR} — skipping clone."
else
    log "Cloning WebDriverAgent into ${WDA_DIR} ..."
    mkdir -p "$(dirname "${WDA_DIR}")"
    git clone --depth 1 "${WDA_REPO_URL}" "${WDA_DIR}"
fi

# --- Resolve device UDID ---------------------------------------------------

UDID="${1:-}"
if [[ -z "${UDID}" ]]; then
    log "No UDID given — auto-detecting via pymobiledevice3 ..."
    UDID="$(uvx pymobiledevice3 usbmux list --no-color 2>/dev/null \
        | /usr/bin/python3 -c 'import json,sys
try:
    devices = json.load(sys.stdin)
except Exception:
    devices = []
print(devices[0].get("Identifier", "") if devices else "")')"
fi

if [[ -z "${UDID}" ]]; then
    die "No iPhone detected over USB. Plug it in, tap Trust, then re-run (or pass the UDID as \$1)."
fi
log "Target device: ${UDID}"

# --- Build (signed with the paid team, unique bundle id) -------------------

log "Building WebDriverAgentRunner (team ${TEAM_ID}, bundle id ${BUNDLE_ID}) ..."
xcodebuild \
    -project "${WDA_DIR}/WebDriverAgent.xcodeproj" \
    -scheme WebDriverAgentRunner \
    -destination "id=${UDID}" \
    -derivedDataPath "${DERIVED_DATA}" \
    -allowProvisioningUpdates \
    CODE_SIGN_STYLE=Automatic \
    DEVELOPMENT_TEAM="${TEAM_ID}" \
    PRODUCT_BUNDLE_IDENTIFIER="${BUNDLE_ID}" \
    build-for-testing

RUNNER_APP="${DERIVED_DATA}/Build/Products/Debug-iphoneos/WebDriverAgentRunner-Runner.app"
[[ -d "${RUNNER_APP}" ]] || die "Build succeeded but runner app not found at ${RUNNER_APP}"

# --- Install onto the phone ------------------------------------------------

log "Installing runner app onto device ..."
xcrun devicectl device install app --device "${UDID}" "${RUNNER_APP}"

log "Done. Runner installed as ${BUNDLE_ID}.xctrunner"
log "Next steps (see docs/IOS.md):"
log "  1) Start WDA:  xcodebuild -project \"${WDA_DIR}/WebDriverAgent.xcodeproj\" \\"
log "       -scheme WebDriverAgentRunner -destination \"id=${UDID}\" \\"
log "       -derivedDataPath \"${DERIVED_DATA}\" -allowProvisioningUpdates \\"
log "       DEVELOPMENT_TEAM=${TEAM_ID} PRODUCT_BUNDLE_IDENTIFIER=${BUNDLE_ID} \\"
log "       test-without-building"
log "  2) Forward ports:  uvx pymobiledevice3 usbmux forward 8100 8100"
log "                     uvx pymobiledevice3 usbmux forward 9100 9100"
log "  3) Check:          curl http://127.0.0.1:8100/status"
