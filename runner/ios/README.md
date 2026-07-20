# runner/ios

iOS device-control runner for OpenMob.

- `WebDriverAgent/` — clone of [appium/WebDriverAgent](https://github.com/appium/WebDriverAgent)
  (created by `scripts/setup-wda.sh`, not committed; its `build/` holds derived data).
  The built `WebDriverAgentRunner-Runner.app` is installed on the iPhone as
  `ai.zevnix.WebDriverAgentRunner.xctrunner`, signed with team `76Z3N79K53`, and
  exposes a WebDriver HTTP server on port 8100 plus an MJPEG screen stream on 9100.

Setup, run, and troubleshooting instructions: see **`docs/IOS.md`** at the repo root.
One-shot setup: `scripts/setup-wda.sh [UDID]`.
