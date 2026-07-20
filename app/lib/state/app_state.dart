import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/engine_client.dart';

class AppState extends ChangeNotifier {
  static const String defaultBaseUrl = 'http://127.0.0.1:8930';
  static const String _prefsKey = 'engine_base_url';
  static const Duration _pollInterval = Duration(seconds: 5);

  EngineClient _client = EngineClient(defaultBaseUrl);
  Timer? _pollTimer;
  bool _disposed = false;

  EngineClient get client => _client;
  String get baseUrl => _client.baseUrl;

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

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_prefsKey);
    if (saved != null && saved.trim().isNotEmpty) {
      _client = EngineClient(saved);
    }
    _pollTimer = Timer.periodic(_pollInterval, (_) => refresh());
    await refresh();
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
    selectedDeviceId = null;
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
      _notify();
      return;
    }

    try {
      devices = await _client.devices();
      if (selectedDeviceId != null &&
          !devices.any((d) => d.id == selectedDeviceId)) {
        selectedDeviceId = null;
      }
    } catch (_) {
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
