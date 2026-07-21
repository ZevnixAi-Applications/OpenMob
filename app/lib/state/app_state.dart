import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/engine_client.dart';
import '../services/engine_launcher.dart';
import '../util/coord_sync.dart';

/// How the main pane lays out open devices.
enum PaneLayout {
  /// Only the active tab's device fills the pane.
  single,

  /// All open devices are visible: 1-3 side by side, 4+ in a 2-column grid.
  split,
}

class AppState extends ChangeNotifier {
  static const String defaultBaseUrl = 'http://127.0.0.1:8930';
  static const String _prefsKey = 'engine_base_url';
  static const String _commandPrefsKey = 'engine_start_command';
  static const String _openTabsKey = 'open_device_ids';
  static const String _activeTabKey = 'active_device_id';
  static const Duration _pollInterval = Duration(seconds: 5);
  static const Duration _startTimeout = Duration(seconds: 30);

  EngineClient _client = EngineClient(defaultBaseUrl);
  Timer? _pollTimer;
  bool _disposed = false;

  EngineClient get client => _client;
  String get baseUrl => _client.baseUrl;

  bool engineOnline = false;
  String? engineVersion;
  List<Device> devices = [];
  List<VirtualDevice> virtualDevices = [];

  /// Ordered ids of the devices open as tabs.
  final List<String> openDeviceIds = [];

  /// Id of the active tab. In single layout it is the visible pane; in split
  /// layout it is the focused pane that the global toolbar targets.
  String? activeDeviceId;

  PaneLayout layout = PaneLayout.single;

  /// When true (split layout only), input performed on any pane is mirrored
  /// to every other visible online device.
  bool syncMode = false;

  /// Bumped on every sync broadcast so mirrored panes can flash briefly.
  int syncPulse = 0;

  /// The pane that originated the last sync broadcast (it does not flash).
  String? syncPulseSourceId;

  /// Names of virtual devices the user just launched, shown as "booting…"
  /// until polling reports them running.
  final Set<String> launchingNames = {};

  /// Names of just-launched virtual devices to auto-open as a tab (inside
  /// OpenMob) as soon as they come online, so the user sees the mirror without
  /// clicking. Cleared once opened.
  final Set<String> _autoOpenNames = {};

  /// Most recent action/engine error, shown transiently in the UI.
  String? lastError;

  /// Shell command used by "Start engine" (macOS only), persisted.
  String engineCommand = '';

  /// True while "Start engine" is launching and polling for health.
  bool engineStarting = false;

  /// Why the last "Start engine" attempt failed, if it did.
  String? engineStartError;

  bool get syncActive => syncMode && layout == PaneLayout.split;

  Device? deviceById(String id) {
    for (final d in devices) {
      if (d.id == id) return d;
    }
    return null;
  }

  Device? get activeDevice =>
      activeDeviceId == null ? null : deviceById(activeDeviceId!);

  /// Open tabs resolved against the current device list, in tab order.
  /// Ids the engine no longer reports are omitted (and pruned on refresh).
  List<Device> get openDevices {
    final out = <Device>[];
    for (final id in openDeviceIds) {
      final d = deviceById(id);
      if (d != null) out.add(d);
    }
    return out;
  }

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_prefsKey);
    if (saved != null && saved.trim().isNotEmpty) {
      _client = EngineClient(saved);
    }
    final savedCommand = prefs.getString(_commandPrefsKey);
    engineCommand = (savedCommand != null && savedCommand.trim().isNotEmpty)
        ? savedCommand
        : EngineLauncher.defaultCommand();
    final savedTabs = prefs.getStringList(_openTabsKey) ?? const [];
    openDeviceIds
      ..clear()
      ..addAll(savedTabs.where((id) => id.trim().isNotEmpty));
    final savedActive = prefs.getString(_activeTabKey);
    if (savedActive != null && openDeviceIds.contains(savedActive)) {
      activeDeviceId = savedActive;
    } else if (openDeviceIds.isNotEmpty) {
      activeDeviceId = openDeviceIds.first;
    }
    _pollTimer = Timer.periodic(_pollInterval, (_) => refresh());
    await refresh();
    // First run with no restored tabs: auto-open the first online device so the
    // mirror, logs panel and toolbar are visible immediately instead of a blank
    // "click a device" screen.
    if (openDeviceIds.isEmpty) {
      final online = devices.where((d) => d.status == 'online');
      if (online.isNotEmpty) openDevice(online.first.id);
    }
  }

  /// Persists the "Start engine" command; empty input restores the default.
  Future<void> setEngineCommand(String command) async {
    final trimmed = command.trim();
    engineCommand = trimmed.isEmpty ? EngineLauncher.defaultCommand() : trimmed;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_commandPrefsKey, engineCommand);
    _notify();
  }

  /// Launches the engine (macOS only) and waits for /health to come up.
  Future<void> startEngine() async {
    if (engineStarting || engineOnline || !EngineLauncher.isSupported) return;
    engineStarting = true;
    engineStartError = null;
    _notify();
    try {
      await EngineLauncher.start(engineCommand);
    } catch (e) {
      engineStarting = false;
      engineStartError = 'Could not launch `$engineCommand`: $e';
      _notify();
      return;
    }
    final deadline = DateTime.now().add(_startTimeout);
    while (DateTime.now().isBefore(deadline) && !_disposed) {
      await Future<void>.delayed(const Duration(seconds: 1));
      try {
        engineVersion = await _client.health();
        engineOnline = true;
        break;
      } catch (_) {
        // Not up yet; keep polling until the deadline.
      }
    }
    engineStarting = false;
    if (!engineOnline) {
      engineStartError =
          'Engine did not respond within ${_startTimeout.inSeconds}s. '
          'Command tried: `$engineCommand` — check it in Engine settings.';
    }
    _notify();
    if (engineOnline) await refresh();
  }

  Future<void> setBaseUrl(String url) async {
    final trimmed = url.trim();
    if (trimmed.isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsKey, trimmed);
    _client = EngineClient(trimmed);
    engineOnline = false;
    engineVersion = null;
    devices = [];
    _notify();
    await refresh();
  }

  /// Polls health + devices. Also used by the manual refresh button.
  Future<void> refresh() async {
    try {
      engineVersion = await _client.health();
      engineOnline = true;
    } catch (_) {
      engineOnline = false;
      engineVersion = null;
      devices = [];
      virtualDevices = [];
      _notify();
      return;
    }

    try {
      devices = await _client.devices();
      _pruneVanishedTabs();
    } catch (_) {
      devices = [];
    }

    try {
      virtualDevices = await _client.virtualDevices();
      launchingNames.removeWhere((name) =>
          virtualDevices.any((v) => v.name == name && v.running));
    } catch (_) {
      virtualDevices = [];
    }
    _autoOpenLaunched();
    _notify();
  }

  Future<void> launchVirtualDevice(String name) async {
    launchingNames.add(name); // optimistic "booting…"
    _notify();
    try {
      await _client.launchVirtualDevice(name);
      // Once it comes online, open it as a tab inside OpenMob automatically.
      _autoOpenNames.add(name);
      if (lastError != null) {
        lastError = null;
        _notify();
      }
    } catch (e) {
      launchingNames.remove(name);
      lastError = e is EngineException ? e.message : 'Engine unreachable';
      _notify();
    }
  }

  /// Registers [name] to be auto-opened as a tab when it next comes online
  /// (used after creating a device that is then launched).
  void autoOpenWhenOnline(String name) => _autoOpenNames.add(name);

  /// Opens any just-launched virtual device as a tab once it appears online in
  /// [devices]. AVDs resolve to an adb serial and simulators to a UDID via the
  /// virtual-device list's device_id.
  void _autoOpenLaunched() {
    if (_autoOpenNames.isEmpty) return;
    final known = {for (final d in devices) d.id};
    for (final name in _autoOpenNames.toList()) {
      VirtualDevice? match;
      for (final v in virtualDevices) {
        if (v.name == name) {
          match = v;
          break;
        }
      }
      // Drop names the engine no longer lists at all (e.g. deleted).
      if (match == null) {
        _autoOpenNames.remove(name);
        continue;
      }
      final id = match.deviceId;
      if (match.running && id != null && known.contains(id)) {
        openDevice(id);
        _autoOpenNames.remove(name);
      }
    }
  }

  /// Drops open tabs whose device the engine no longer reports at all.
  /// Offline devices stay open (their panes show an offline state).
  void _pruneVanishedTabs() {
    final known = devices.map((d) => d.id).toSet();
    if (!openDeviceIds.any((id) => !known.contains(id))) return;
    openDeviceIds.removeWhere((id) => !known.contains(id));
    if (activeDeviceId != null && !openDeviceIds.contains(activeDeviceId)) {
      activeDeviceId = openDeviceIds.isEmpty ? null : openDeviceIds.first;
    }
    if (openDeviceIds.isEmpty) {
      layout = PaneLayout.single;
      syncMode = false;
    }
    _persistTabs();
  }

  // --- Tab management ---

  /// Opens [id] as a tab (if not already open) and makes it active.
  void openDevice(String id) {
    final already = openDeviceIds.contains(id);
    if (!already) openDeviceIds.add(id);
    if (already && activeDeviceId == id) return;
    activeDeviceId = id;
    _persistTabs();
    _notify();
  }

  void activateDevice(String id) {
    if (!openDeviceIds.contains(id) || activeDeviceId == id) return;
    activeDeviceId = id;
    _persistTabs();
    _notify();
  }

  /// Closes the tab for [id]. Closing the active tab activates its right
  /// neighbor (or the left one when the rightmost tab was closed).
  void closeDevice(String id) {
    final idx = openDeviceIds.indexOf(id);
    if (idx == -1) return;
    openDeviceIds.removeAt(idx);
    if (activeDeviceId == id) {
      activeDeviceId = openDeviceIds.isEmpty
          ? null
          : openDeviceIds[
              idx < openDeviceIds.length ? idx : openDeviceIds.length - 1];
    }
    if (openDeviceIds.isEmpty) {
      layout = PaneLayout.single;
      syncMode = false;
    }
    _persistTabs();
    _notify();
  }

  void setLayout(PaneLayout value) {
    if (layout == value) return;
    layout = value;
    if (layout == PaneLayout.single) syncMode = false;
    _notify();
  }

  void toggleLayout() => setLayout(
      layout == PaneLayout.single ? PaneLayout.split : PaneLayout.single);

  /// Toggles sync-input mode. Only meaningful in split layout.
  void toggleSync() {
    if (layout != PaneLayout.split) return;
    syncMode = !syncMode;
    _notify();
  }

  void _persistTabs() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList(_openTabsKey, List.of(openDeviceIds));
      final active = activeDeviceId;
      if (active == null) {
        await prefs.remove(_activeTabKey);
      } else {
        await prefs.setString(_activeTabKey, active);
      }
    } catch (_) {
      // Persistence is best-effort; never break the UI over it.
    }
  }

  // --- Device actions ---
  //
  // Every action originates from a source device (the pane it was performed
  // on, or the active tab for the global toolbar). When sync is active the
  // action is also mirrored to every other visible online device,
  // fire-and-forget: one device failing never blocks the others. Tap/swipe
  // coordinates are translated proportionally; text and keys go verbatim.

  Future<void> tapDevice(String sourceId, int x, int y) async {
    final src = deviceById(sourceId);
    final targets = _syncTargets(sourceId);
    if (targets.isNotEmpty && src != null) {
      _firePulse(sourceId);
      for (final t in targets) {
        final p = translatePoint(
          x: x,
          y: y,
          srcWidth: src.width,
          srcHeight: src.height,
          dstWidth: t.width,
          dstHeight: t.height,
        );
        if (p == null) continue;
        _fireAndForget(t, () => _client.tap(t.id, p.x, p.y));
      }
    }
    await _runSource(() => _client.tap(sourceId, x, y));
  }

  Future<void> swipeDevice(
    String sourceId,
    int x1,
    int y1,
    int x2,
    int y2,
    int durationMs,
  ) async {
    final src = deviceById(sourceId);
    final targets = _syncTargets(sourceId);
    if (targets.isNotEmpty && src != null) {
      _firePulse(sourceId);
      for (final t in targets) {
        final p1 = translatePoint(
          x: x1,
          y: y1,
          srcWidth: src.width,
          srcHeight: src.height,
          dstWidth: t.width,
          dstHeight: t.height,
        );
        final p2 = translatePoint(
          x: x2,
          y: y2,
          srcWidth: src.width,
          srcHeight: src.height,
          dstWidth: t.width,
          dstHeight: t.height,
        );
        if (p1 == null || p2 == null) continue;
        _fireAndForget(
          t,
          () => _client.swipe(t.id,
              x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, durationMs: durationMs),
        );
      }
    }
    await _runSource(() => _client.swipe(sourceId,
        x1: x1, y1: y1, x2: x2, y2: y2, durationMs: durationMs));
  }

  Future<void> sendTextDevice(String sourceId, String text) =>
      _verbatimAction(sourceId, (id) => _client.sendText(id, text));

  Future<void> pressKeyDevice(String sourceId, String key) =>
      _verbatimAction(sourceId, (id) => _client.pressKey(id, key));

  /// Toolbar convenience: targets the active (focused) device.
  Future<void> sendText(String text) {
    final id = activeDeviceId;
    if (id == null) return Future.value();
    return sendTextDevice(id, text);
  }

  /// Toolbar convenience: targets the active (focused) device.
  Future<void> pressKey(String key) {
    final id = activeDeviceId;
    if (id == null) return Future.value();
    return pressKeyDevice(id, key);
  }

  Future<void> _verbatimAction(
    String sourceId,
    Future<void> Function(String id) run,
  ) async {
    final targets = _syncTargets(sourceId);
    if (targets.isNotEmpty) {
      _firePulse(sourceId);
      for (final t in targets) {
        _fireAndForget(t, () => run(t.id));
      }
    }
    await _runSource(() => run(sourceId));
  }

  /// Online open devices other than [sourceId]; empty when sync is off.
  List<Device> _syncTargets(String sourceId) {
    if (!syncActive) return const [];
    return [
      for (final d in openDevices)
        if (d.id != sourceId && d.online) d,
    ];
  }

  void _firePulse(String sourceId) {
    syncPulse++;
    syncPulseSourceId = sourceId;
    _notify();
  }

  void _fireAndForget(Device target, Future<void> Function() run) {
    run().catchError((Object e) {
      _reportError(
          '${target.name}: ${e is EngineException ? e.message : 'unreachable'}');
    });
  }

  Future<void> _runSource(Future<void> Function() run) async {
    try {
      await run();
      if (lastError != null) {
        lastError = null;
        _notify();
      }
    } catch (e) {
      _reportError(e is EngineException ? e.message : 'Engine unreachable');
    }
  }

  /// Surfaces an action error in the banner, deduping identical repeats.
  void _reportError(String message) {
    if (lastError == message) return;
    lastError = message;
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _pollTimer?.cancel();
    super.dispose();
  }
}
