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

# --- Rebrand runner UI as OpenMob Runner ------------------------------------
# Display layer ONLY: app icon + CFBundleDisplayName. Never change CFBundleName
# or class/bundle structure — that breaks XCTest bundle loading. Upstream
# attribution stays in THIRD_PARTY_LICENSES.md (BSD-3-Clause). Idempotent.

BRANDING_DIR="${ROOT_DIR}/runner/ios/branding"
RUNNER_XCASSETS="${WDA_DIR}/WebDriverAgentRunner/Assets.xcassets"
if [[ -f "${BRANDING_DIR}/icon-1024.png" && -f "${RUNNER_XCASSETS}/AppIcon.appiconset/icon-1024.png" ]]; then
    cp "${BRANDING_DIR}/icon-1024.png" "${RUNNER_XCASSETS}/AppIcon.appiconset/icon-1024.png"
    log "OpenMob app icon copied into the runner asset catalog."
fi
# Launch-screen assets (branded idle screen shown when the app is opened by hand)
if [[ -d "${BRANDING_DIR}/LaunchImage.imageset" && -d "${RUNNER_XCASSETS}" ]]; then
    cp -R "${BRANDING_DIR}/LaunchImage.imageset" "${BRANDING_DIR}/LaunchBackground.colorset" "${RUNNER_XCASSETS}/"
    log "OpenMob launch-screen assets copied into the runner asset catalog."
fi

RUNNER_PLIST="${WDA_DIR}/WebDriverAgentRunner/Info.plist"
if [[ -f "${RUNNER_PLIST}" ]]; then
    /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 'OM Runner'" "${RUNNER_PLIST}" 2>/dev/null \
        || /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'OM Runner'" "${RUNNER_PLIST}"
    log "Runner display name set to 'OM Runner'."
fi

# --- Resolve device UDID ---------------------------------------------------

UDID="${1:-}"
if [[ -z "${UDID}" ]]; then
    log "No UDID given — auto-detecting via pymobiledevice3 ..."
    UDID="$(uvx pymobiledevice3 usbmux list 2>/dev/null \
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

# --- Rebrand the BUILT bundle (Xcode generates the runner's Info.plist,   --
# --- ignoring the source plist) and re-sign it                            --

/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 'OM Runner'" "${RUNNER_APP}/Info.plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'OM Runner'" "${RUNNER_APP}/Info.plist"
# Branded launch screen (idle screen when the app is opened by hand); assets are
# compiled into Assets.car from the catalog copies made before the build.
/usr/libexec/PlistBuddy -c "Delete :UILaunchScreen" "${RUNNER_APP}/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :UILaunchScreen dict" "${RUNNER_APP}/Info.plist"
/usr/libexec/PlistBuddy -c "Add :UILaunchScreen:UIColorName string LaunchBackground" "${RUNNER_APP}/Info.plist"
/usr/libexec/PlistBuddy -c "Add :UILaunchScreen:UIImageName string LaunchImage" "${RUNNER_APP}/Info.plist"
SIGN_ID="$(security find-identity -v -p codesigning | grep -m1 'Apple Development' | awk '{print $2}')"
[[ -n "${SIGN_ID}" ]] || die "No 'Apple Development' signing identity found in keychain."
codesign -f --preserve-metadata=identifier,entitlements,flags -s "${SIGN_ID}" "${RUNNER_APP}"
log "Runner rebranded to 'OM Runner' (display name + launch screen) and re-signed."

# --- Install onto the phone ------------------------------------------------

log "Installing runner app onto device ..."
xcrun devicectl device install app --device "${UDID}" "${RUNNER_APP}"

# --- Launch standalone (no xcodebuild session needed) ----------------------

log "Launching OpenMob Runner ..."
xcrun devicectl device process launch --terminate-existing --device "${UDID}" "${BUNDLE_ID}.xctrunner" || \
    log "Launch failed — unlock the phone and re-run, or use the xcodebuild fallback below."

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
