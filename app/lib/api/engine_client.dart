import 'dart:convert';

import 'package:http/http.dart' as http;

/// A device as reported by GET /api/v1/devices.
class Device {
  const Device({
    required this.id,
    required this.name,
    required this.platform,
    required this.status,
    required this.width,
    required this.height,
  });

  final String id;
  final String name;
  final String platform; // "android" | "ios"
  final String status; // "online" | "offline"
  final int width;
  final int height;

  bool get online => status == 'online';
  bool get isIos => platform == 'ios';

  factory Device.fromJson(Map<String, dynamic> json) {
    return Device(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? 'Unknown device',
      platform: json['platform'] as String? ?? 'android',
      status: json['status'] as String? ?? 'offline',
      width: (json['width'] as num?)?.toInt() ?? 0,
      height: (json['height'] as num?)?.toInt() ?? 0,
    );
  }
}

/// A launchable virtual device as reported by GET /api/v1/virtual-devices.
class VirtualDevice {
  const VirtualDevice({
    required this.name,
    required this.platform,
    required this.kind,
    required this.state,
    this.deviceId,
  });

  final String name;
  final String platform; // "android" | "ios"
  final String kind; // "avd" | "simulator"
  final String state; // "running" | "stopped"

  /// Serial/UDID once running (AVDs have none while stopped).
  final String? deviceId;

  bool get running => state == 'running';
  bool get isIos => platform == 'ios';

  factory VirtualDevice.fromJson(Map<String, dynamic> json) {
    return VirtualDevice(
      name: json['name'] as String? ?? '',
      platform: json['platform'] as String? ?? 'android',
      kind: json['kind'] as String? ?? 'avd',
      state: json['state'] as String? ?? 'stopped',
      deviceId: json['device_id'] as String?,
    );
  }
}

/// An installed third-party app as reported by GET /devices/{id}/apps.
class AppInfo {
  const AppInfo({required this.package, required this.name});

  final String package;
  final String name;

  factory AppInfo.fromJson(Map<String, dynamic> json) {
    final package = json['package'] as String? ?? '';
    return AppInfo(
      package: package,
      name: json['name'] as String? ?? package,
    );
  }
}

class EngineException implements Exception {
  const EngineException(this.message);
  final String message;

  @override
  String toString() => 'EngineException: $message';
}

/// Thin REST client for the OpenMob engine (see docs/API.md).
class EngineClient {
  EngineClient(String baseUrl) : baseUrl = _normalize(baseUrl);

  /// e.g. http://127.0.0.1:8930 (no trailing slash, no /api/v1).
  final String baseUrl;

  static const Duration _timeout = Duration(seconds: 4);

  static String _normalize(String url) {
    var u = url.trim();
    if (u.endsWith('/')) u = u.substring(0, u.length - 1);
    return u;
  }

  Uri _api(String path) => Uri.parse('$baseUrl/api/v1$path');

  /// WebSocket URI for the live screen stream of [deviceId].
  Uri streamUri(String deviceId) {
    final u = Uri.parse(baseUrl);
    return u.replace(
      scheme: u.scheme == 'https' ? 'wss' : 'ws',
      path: '/api/v1/devices/$deviceId/stream',
    );
  }

  /// WebSocket URI for the live log stream of [deviceId].
  ///
  /// Scope the tail to one app with [package] (its live process, followed across
  /// restarts) or [scope] = 'foreground' (auto-target the foreground app). [flutter]
  /// narrows to Flutter output. With none set, the whole device is tailed.
  Uri logsStreamUri(
    String deviceId, {
    String? filter,
    String? package,
    String? scope,
    bool flutter = false,
  }) {
    final u = Uri.parse(baseUrl);
    final params = <String, String>{
      if (filter != null && filter.isNotEmpty) 'filter': filter,
      if (package != null && package.isNotEmpty) 'package': package,
      if (scope != null && scope.isNotEmpty) 'scope': scope,
      if (flutter) 'flutter': 'true',
    };
    return u.replace(
      scheme: u.scheme == 'https' ? 'wss' : 'ws',
      path: '/api/v1/devices/$deviceId/logs/stream',
      queryParameters: params.isEmpty ? null : params,
    );
  }

  /// Installed third-party apps on [deviceId] (for the logs scope selector).
  Future<List<AppInfo>> apps(String deviceId) async {
    final res = await http.get(_api('/devices/$deviceId/apps')).timeout(_timeout);
    if (res.statusCode != 200) {
      throw EngineException('apps returned ${res.statusCode}');
    }
    final body = jsonDecode(res.body) as List<dynamic>;
    return body
        .map((e) => AppInfo.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Returns the engine version, or throws if the engine is unreachable.
  Future<String> health() async {
    final res = await http.get(_api('/health')).timeout(_timeout);
    if (res.statusCode != 200) {
      throw EngineException('health returned ${res.statusCode}');
    }
    final body = jsonDecode(res.body) as Map<String, dynamic>;
    return body['version'] as String? ?? '?';
  }

  Future<List<Device>> devices() async {
    final res = await http.get(_api('/devices')).timeout(_timeout);
    if (res.statusCode != 200) {
      throw EngineException('devices returned ${res.statusCode}');
    }
    final body = jsonDecode(res.body) as List<dynamic>;
    return body
        .map((e) => Device.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<VirtualDevice>> virtualDevices() async {
    final res = await http.get(_api('/virtual-devices')).timeout(_timeout);
    if (res.statusCode != 200) {
      throw EngineException('virtual-devices returned ${res.statusCode}');
    }
    final body = jsonDecode(res.body) as List<dynamic>;
    return body
        .map((e) => VirtualDevice.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> launchVirtualDevice(String name) =>
      _post('/virtual-devices/launch', {'name': name});

  Future<void> tap(String deviceId, int x, int y) =>
      _post('/devices/$deviceId/tap', {'x': x, 'y': y});

  Future<void> swipe(
    String deviceId, {
    required int x1,
    required int y1,
    required int x2,
    required int y2,
    required int durationMs,
  }) =>
      _post('/devices/$deviceId/swipe', {
        'x1': x1,
        'y1': y1,
        'x2': x2,
        'y2': y2,
        'duration_ms': durationMs,
      });

  Future<void> sendText(String deviceId, String text) =>
      _post('/devices/$deviceId/text', {'text': text});

  Future<void> pressKey(String deviceId, String key) =>
      _post('/devices/$deviceId/key', {'key': key});

  Future<void> _post(String path, Map<String, dynamic> body) async {
    final res = await http
        .post(
          _api(path),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(_timeout);
    if (res.statusCode < 200 || res.statusCode >= 300) {
      String detail = 'HTTP ${res.statusCode}';
      try {
        final parsed = jsonDecode(res.body) as Map<String, dynamic>;
        detail = parsed['detail'] as String? ?? detail;
      } catch (_) {
        // keep generic detail
      }
      throw EngineException(detail);
    }
  }
}
