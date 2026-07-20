import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

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

/// Interface to an OpenMob engine (see docs/API.md).
///
/// [HttpEngineClient] talks to a real engine over HTTP/WS;
/// [DemoEngineClient] (api/demo_engine_client.dart) fakes one in memory so
/// the app can be exercised without any engine on the network.
abstract class EngineClient {
  /// e.g. http://127.0.0.1:8930 (no trailing slash, no /api/v1).
  String get baseUrl;

  /// Returns the engine version, or throws if the engine is unreachable.
  Future<String> health();

  Future<List<Device>> devices();

  Future<void> tap(String deviceId, int x, int y);

  Future<void> swipe(
    String deviceId, {
    required int x1,
    required int y1,
    required int x2,
    required int y2,
    required int durationMs,
  });

  Future<void> sendText(String deviceId, String text);

  Future<void> pressKey(String deviceId, String key);

  /// Live screen frames (JPEG/PNG bytes, one event per frame) for [deviceId].
  ///
  /// Single-subscription; cancel to stop. Errors/closes when the stream is
  /// lost — the caller is expected to re-call to reconnect.
  Stream<Uint8List> frames(String deviceId);
}

/// Thin REST/WebSocket client for a real OpenMob engine.
class HttpEngineClient implements EngineClient {
  HttpEngineClient(String baseUrl) : baseUrl = _normalize(baseUrl);

  @override
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

  @override
  Future<String> health() async {
    final res = await http.get(_api('/health')).timeout(_timeout);
    if (res.statusCode != 200) {
      throw EngineException('health returned ${res.statusCode}');
    }
    final body = jsonDecode(res.body) as Map<String, dynamic>;
    return body['version'] as String? ?? '?';
  }

  @override
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

  @override
  Future<void> tap(String deviceId, int x, int y) =>
      _post('/devices/$deviceId/tap', {'x': x, 'y': y});

  @override
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

  @override
  Future<void> sendText(String deviceId, String text) =>
      _post('/devices/$deviceId/text', {'text': text});

  @override
  Future<void> pressKey(String deviceId, String key) =>
      _post('/devices/$deviceId/key', {'key': key});

  @override
  Stream<Uint8List> frames(String deviceId) {
    WebSocketChannel? channel;
    StreamSubscription<dynamic>? sub;
    late final StreamController<Uint8List> controller;
    controller = StreamController<Uint8List>(
      onListen: () {
        try {
          channel = WebSocketChannel.connect(streamUri(deviceId));
        } catch (e) {
          controller.addError(EngineException('stream failed: $e'));
          controller.close();
          return;
        }
        sub = channel!.stream.listen(
          (message) {
            if (message is List<int>) {
              controller.add(message is Uint8List
                  ? message
                  : Uint8List.fromList(message));
            }
          },
          onError: controller.addError,
          onDone: controller.close,
          cancelOnError: true,
        );
      },
      onCancel: () async {
        await sub?.cancel();
        await channel?.sink.close();
      },
    );
    return controller.stream;
  }

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
