# App Store listing — OpenMob

## App details

| Field | Value |
|---|---|
| App name | OpenMob |
| Subtitle (max 30 chars) | Control your devices, anywhere |
| Bundle ID | ai.zevnix.openmob |
| Primary category | Developer Tools |
| Secondary category | Utilities |
| Price | Free |
| Team | Zevnix AI (76Z3N79K53) |
| Privacy policy URL | link to `PRIVACY.md` in the public GitHub repo |

## Promotional text (max 170 chars)

> Run the free OpenMob engine on your computer, plug in your devices, and
> drive them from your phone — live mirror, touch control, all on your own
> LAN. Open source.

## Description

OpenMob turns your phone into a remote control for the real devices on your
desk. Run the free, open-source OpenMob engine on a computer, plug in your
Android or iOS devices, and control them from anywhere on your local network —
live screen mirror, tap, swipe, type, install apps, read logs.

HOW IT WORKS

- Install the free OpenMob engine on a computer (macOS) and connect your
  devices over USB.
- Open the app, enter the engine's address, and every connected device
  appears with a live mirror you can drive by touch.
- Everything stays on your LAN. The app never talks to any server that
  isn't yours.

HIGHLIGHTS

- Live screen mirror with touch control (tap, swipe, type)
- Works with real Android and iOS devices attached to your engine
- Built for developers, testers, and AI-agent workflows (MCP server included
  in the engine)
- 100% open source (MIT) — audit every line
- No account, no ads, no analytics, no data collection
- Try Demo mode: explore the full UI with a simulated device, no hardware or
  engine needed

Requires the free OpenMob engine running on a computer on the same network.
Get it at the OpenMob GitHub repository.

## Keywords (max 100 chars, comma-separated)

> device,mirror,adb,remote,control,testing,automation,developer,farm,mcp,open source

(83 chars)

## Age rating questionnaire — answers

All content descriptors (violence, sexual content, profanity, drugs,
gambling, horror, etc.): **None**. Unrestricted web access: **No**.
Gambling/contests: **No**. Made for kids: **No**. Expected rating: **4+**.

## App privacy (nutrition label) — answers

- Data collection: **Data Not Collected** (no analytics, no identifiers, no
  tracking, no third-party SDKs).

## Local-network permission — review notes text

Paste this into App Store Connect "Notes" for review, and use the same
wording for `NSLocalNetworkUsageDescription`:

> OpenMob is a client for the open-source OpenMob engine that the user runs
> on their own computer. The app uses the local network solely to connect to
> that engine at an address the user types in themselves (HTTP + WebSocket on
> the user's LAN), to list the user's own attached devices, stream their
> screens, and send the user's touch input back. No other network access
> occurs; nothing is sent to the developer or any third party.

Suggested `NSLocalNetworkUsageDescription` (Info.plist):

> OpenMob connects to the OpenMob engine on your computer over your local
> network to show and control your devices.

## Demo mode — note for reviewers

> To review without any hardware: on the connect screen, tap **Try Demo** —
> the full UI runs against a simulated device. No engine, no hardware, and no
> network connection needed.
