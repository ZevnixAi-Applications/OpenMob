# openmob

Desktop (macOS) UI for the OpenMob engine: live device mirrors with tap,
swipe, text and hardware-key input over the engine's local HTTP/WS API
(see `docs/API.md`).

## Multi-device view

Devices open as VS Code-style tabs. Clicking a device in the sidebar opens
(or re-activates) its tab; the tab's `x` closes it. The open set and the
active tab persist across restarts.

### Layouts

- **Single** (default): the active tab fills the main pane. Only the active
  device's screen stream is connected; switching tabs disposes the previous
  stream.
- **Split** (grid icon in the tab bar's right corner): every open device is
  visible at once — 1-3 devices side by side, 4+ in a 2-column grid. Each
  pane runs its own WebSocket stream, keeps its own aspect-correct mirror
  and tap/swipe handling, and has a slim header with the device name and a
  close button. Offline devices show an offline pane state.

### Focus and the toolbar

The bottom toolbar (back/home/power/volume/text) always targets the
**focused** pane: in single view that is the active tab; in split view,
click any pane to focus it — the focused pane gets an accent outline and
the toolbar shows the target device's name. A single global toolbar was
chosen over per-pane toolbars so panes keep their full height for the
mirror, and typing once + sync mode composes naturally ("type once, send
everywhere").

### Sync input

The link icon (enabled in split view only) toggles sync-input mode. While
on:

- Taps and swipes on any pane are also sent to every other visible online
  device, with coordinates translated proportionally to each device's
  reported resolution (a tap at 50%/30% lands at 50%/30% everywhere).
- Text and keys sent from the toolbar go verbatim to all online panes.
- All panes show a blue border; mirrored panes flash briefly when a
  broadcast fires.
- Offline devices are skipped, and a failure on one device never blocks
  the others (errors surface, deduped, in the error banner).

## Development

```sh
flutter run -d macos     # engine must be running: openmob serve
flutter test
flutter analyze
```
