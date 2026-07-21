# Contributing to OpenMob

Thanks for helping out. This is a short guide to getting a dev environment running
and getting changes merged. New here? Read
[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) first, and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit together.

## Prerequisites

- macOS (the desktop app targets macOS; the engine also runs standalone)
- [uv](https://docs.astral.sh/uv/) — Python toolchain for `engine/` (Python 3.12 is installed by uv automatically)
- [Flutter](https://docs.flutter.dev/get-started/install) (stable channel) — for `app/`
- `adb` (Android SDK platform-tools) — only needed to control real Android devices
- `ffmpeg` — only for the Android low-latency video mirror
- Xcode — only needed for iOS device/simulator control and the macOS app build

## Repo layout

- `engine/` — Python device engine: CLI, HTTP/WebSocket API, MCP server
- `app/` — Flutter macOS desktop app
- `runner/` — on-device companions (iOS WebDriverAgent runner + branding)
- `scripts/` — setup helpers (`setup-wda.sh`) and the E2E release-gate harness
- `testapp/` — deterministic Flutter testbed used by the E2E gate
- `docs/` — API contract, architecture, dev tools, iOS setup (see [docs/README.md](docs/README.md))

## Engine

```sh
cd engine
uv sync                 # install deps into .venv
uv run openmob devices  # print detected devices
uv run openmob serve    # HTTP/WS API on 127.0.0.1:8930
uv run openmob mcp      # MCP stdio server
```

Tests and lint (no device required — tests are unit tests with mocks):

```sh
uv run pytest
uv run ruff check .
```

## App

```sh
cd app
flutter pub get
flutter run -d macos    # needs the engine running (uv run openmob serve)
flutter analyze
flutter test
flutter build macos --debug
```

## Code style

- **Engine (Python):** `ruff` is the source of truth (line length 100, target
  py312 — configured in `engine/pyproject.toml`). Run `uv run ruff check .` and fix
  what it flags before opening a PR.
- **App (Dart):** keep `flutter analyze` clean.
- Coordinates and screen sizes are **device pixels** at the API boundary; convert
  inside a backend, not in callers.

## CI / merge gate

Every PR must pass the `CI` workflow (`.github/workflows/ci.yml`) before merge:

- **engine** — `uv run ruff check .` and `uv run pytest -q` on Ubuntu
- **app** — `flutter analyze`, `flutter test`, and `flutter build macos --debug` on macOS

Run the same commands locally before opening a PR. Tests must pass without a device
attached; if a test genuinely needs hardware, mark it so it is skipped by default
and note it in the PR.

### End-to-end release gate (optional, needs hardware)

`scripts/` holds the E2E gate that proves the full automation flow against the
`testapp/` testbed — through the engine HTTP API (`scripts/e2e_test.py`) and
through real Claude over MCP (`scripts/e2e_mcp_test.sh`). It needs a device or
emulator and is not part of CI; see [scripts/README.md](scripts/README.md) to run it.

## PR conventions

- Branch from `main` using a short feature branch (`feat/...`, `fix/...`, `docs/...`).
- Open PRs against `main`; keep them focused on one change.
- Fill in the PR template checklist; update `docs/` when behavior or the API contract changes.
- Never commit secrets, tokens, signing identities, or personal device identifiers.
</content>
