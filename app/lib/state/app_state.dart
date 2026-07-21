import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/demo_engine_client.dart';
import '../api/engine_client.dart';

class AppState extends ChangeNotifier {
  static const String defaultBaseUrl = 'http://127.0.0.1:8930';
  static const String _prefsKey = 'engine_base_url';
  static const Duration _pollInterval = Duration(seconds: 5);

  EngineClient _client = HttpEngineClient(defaultBaseUrl);

  /// The configured engine URL. Kept separately from [_client] so it survives
  /// demo mode (where the client is a [DemoEngineClient]).
  String _baseUrl = defaultBaseUrl;

  Timer? _pollTimer;
  bool _disposed = false;
  bool _demoMode = false;

  EngineClient get client => _client;
  String get baseUrl => _baseUrl;
  bool get demoMode => _demoMode;

  bool engineOnline = false;
  String? engineVersion;
  List<Device> devices = [];
  String? selectedDeviceId;

  /// Most recent action/engine error, shown transiently in the UI.
  String? lastError;

  Device? get selectedDevice {
    for (final d in devices) {
      if (d.id == selectedDeviceId) return d;
    }
    return null;
  }

  /// Returns an error message when [input] is not a usable engine URL,
  /// or null when it is valid.
  static String? validateEngineUrl(String input) {
    final trimmed = input.trim();
    if (trimmed.isEmpty) {
      return 'Enter the engine URL, e.g. http://192.168.1.50:8930';
    }
    final uri = Uri.tryParse(trimmed);
    if (uri == null ||
        (uri.scheme != 'http' && uri.scheme != 'https') ||
        uri.host.isEmpty) {
      return 'Enter a full URL starting with http://, '
          'e.g. http://192.168.1.50:8930';
    }
    return null;
  }

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_prefsKey);
    if (saved != null && saved.trim().isNotEmpty) {
      final client = HttpEngineClient(saved);
      _client = client;
      _baseUrl = client.baseUrl;
    }
    _pollTimer = Timer.periodic(_pollInterval, (_) => refresh());
    await refresh();
  }

  Future<void> setBaseUrl(String url) async {
    final trimmed = url.trim();
    if (validateEngineUrl(trimmed) != null) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsKey, trimmed);
    final client = HttpEngineClient(trimmed);
    _client = client;
    _baseUrl = client.baseUrl;
    _demoMode = false;
    engineOnline = false;
    engineVersion = null;
    devices = [];
    selectedDeviceId = null;
    lastError = null;
    _notify();
    await refresh();
  }

  /// Switches to the in-memory fake engine (see [DemoEngineClient]) and
  /// selects its device, so the mirror shows something without a real engine.
  Future<void> enterDemoMode() async {
    if (_demoMode) return;
    final demo = await DemoEngineClient.create();
    _client = demo;
    _demoMode = true;
    lastError = null;
    devices = [];
    selectedDeviceId = null;
    _notify();
    await refresh();
    if (devices.isNotEmpty) {
      selectedDeviceId = devices.first.id;
      _notify();
    }
  }

  /// Leaves demo mode and reconnects to the configured engine URL.
  Future<void> exitDemoMode() async {
    if (!_demoMode) return;
    _demoMode = false;
    _client = HttpEngineClient(_baseUrl);
    engineOnline = false;
    engineVersion = null;
    devices = [];
    selectedDeviceId = null;
    lastError = null;
    _notify();
    await refresh();
  }

  /// Polls health + devices. Also used by the manual refresh button.
  Future<void> refresh() async {
    final client = _client;
    try {
      final version = await client.health();
      if (client != _client) return; // URL/mode changed mid-flight.
      engineVersion = version;
      engineOnline = true;
    } catch (_) {
      if (client != _client) return;
      engineOnline = false;
      engineVersion = null;
      devices = [];
      _notify();
      return;
    }

    try {
      final list = await client.devices();
      if (client != _client) return;
      devices = list;
      if (selectedDeviceId != null &&
          !devices.any((d) => d.id == selectedDeviceId)) {
        selectedDeviceId = null;
      }
    } catch (_) {
      if (client != _client) return;
      devices = [];
      selectedDeviceId = null;
    }
    _notify();
  }

  void selectDevice(String id) {
    if (selectedDeviceId == id) return;
    selectedDeviceId = id;
    _notify();
  }

  // --- Device actions (fire against the selected device) ---

  Future<void> tap(int x, int y) =>
      _action((id) => _client.tap(id, x, y));

  Future<void> swipe(int x1, int y1, int x2, int y2, int durationMs) =>
      _action((id) => _client.swipe(id,
          x1: x1, y1: y1, x2: x2, y2: y2, durationMs: durationMs));

  Future<void> sendText(String text) =>
      _action((id) => _client.sendText(id, text));

  Future<void> pressKey(String key) =>
      _action((id) => _client.pressKey(id, key));

  Future<void> _action(Future<void> Function(String id) run) async {
    final id = selectedDeviceId;
    if (id == null) return;
    try {
      await run(id);
      if (lastError != null) {
        lastError = null;
        _notify();
      }
    } catch (e) {
      lastError = e is EngineException ? e.message : 'Engine unreachable';
      _notify();
    }
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
