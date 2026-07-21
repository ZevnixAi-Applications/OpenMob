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
  Uri logsStreamUri(String deviceId, {String? filter}) {
    final u = Uri.parse(baseUrl);
    return u.replace(
      scheme: u.scheme == 'https' ? 'wss' : 'ws',
      path: '/api/v1/devices/$deviceId/logs/stream',
      queryParameters:
          (filter == null || filter.isEmpty) ? null : {'filter': filter},
    );
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
