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

/// An Android hardware profile (e.g. "pixel_7") for creating an AVD.
class DeviceProfile {
  const DeviceProfile({required this.id, required this.name});
  final String id;
  final String name;

  factory DeviceProfile.fromJson(Map<String, dynamic> json) => DeviceProfile(
        id: json['id'] as String? ?? '',
        name: json['name'] as String? ?? '',
      );
}

/// An installable Android system image (from `sdkmanager --list`).
class SystemImage {
  const SystemImage({
    required this.id,
    required this.api,
    required this.tag,
    required this.abi,
    required this.installed,
  });

  final String id;
  final String api;
  final String tag;
  final String abi;
  final bool installed;

  /// Human label, e.g. "Android 35 · google_apis · arm64-v8a".
  String get label => 'Android $api · $tag · $abi';

  factory SystemImage.fromJson(Map<String, dynamic> json) => SystemImage(
        id: json['id'] as String? ?? '',
        api: json['api'] as String? ?? '',
        tag: json['tag'] as String? ?? '',
        abi: json['abi'] as String? ?? '',
        installed: json['installed'] as bool? ?? false,
      );
}

/// An iOS simulator device type (e.g. "iPhone 17 Pro").
class DeviceType {
  const DeviceType({required this.id, required this.name});
  final String id;
  final String name;

  factory DeviceType.fromJson(Map<String, dynamic> json) => DeviceType(
        id: json['id'] as String? ?? '',
        name: json['name'] as String? ?? '',
      );
}

/// An iOS runtime (e.g. "iOS 26.3"); [available] false means it needs a download.
class Runtime {
  const Runtime({required this.id, required this.name, required this.available});
  final String id;
  final String name;
  final bool available;

  factory Runtime.fromJson(Map<String, dynamic> json) => Runtime(
        id: json['id'] as String? ?? '',
        name: json['name'] as String? ?? '',
        available: json['available'] as bool? ?? false,
      );
}

/// Android creation options: profiles + installable images (or why unavailable).
class AndroidCreateOptions {
  const AndroidCreateOptions({
    required this.available,
    required this.reason,
    required this.deviceProfiles,
    required this.systemImages,
  });

  final bool available;
  final String? reason;
  final List<DeviceProfile> deviceProfiles;
  final List<SystemImage> systemImages;

  factory AndroidCreateOptions.fromJson(Map<String, dynamic> json) {
    return AndroidCreateOptions(
      available: json['available'] as bool? ?? false,
      reason: json['reason'] as String?,
      deviceProfiles: ((json['device_profiles'] as List<dynamic>?) ?? [])
          .map((e) => DeviceProfile.fromJson(e as Map<String, dynamic>))
          .toList(),
      systemImages: ((json['system_images'] as List<dynamic>?) ?? [])
          .map((e) => SystemImage.fromJson(e as Map<String, dynamic>))
          .toList(),
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

/// iOS creation options: device types + runtimes (or why unavailable).
class IosCreateOptions {
  const IosCreateOptions({
    required this.available,
    required this.reason,
    required this.deviceTypes,
    required this.runtimes,
  });

  final bool available;
  final String? reason;
  final List<DeviceType> deviceTypes;
  final List<Runtime> runtimes;

  factory IosCreateOptions.fromJson(Map<String, dynamic> json) {
    return IosCreateOptions(
      available: json['available'] as bool? ?? false,
      reason: json['reason'] as String?,
      deviceTypes: ((json['device_types'] as List<dynamic>?) ?? [])
          .map((e) => DeviceType.fromJson(e as Map<String, dynamic>))
          .toList(),
      runtimes: ((json['runtimes'] as List<dynamic>?) ?? [])
          .map((e) => Runtime.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// Options for creating new virtual devices (GET /virtual-devices/create-options).
class CreateOptions {
  const CreateOptions({required this.android, required this.ios});
  final AndroidCreateOptions android;
  final IosCreateOptions ios;

  factory CreateOptions.fromJson(Map<String, dynamic> json) => CreateOptions(
        android: AndroidCreateOptions.fromJson(
            (json['android'] as Map<String, dynamic>?) ?? const {}),
        ios: IosCreateOptions.fromJson(
            (json['ios'] as Map<String, dynamic>?) ?? const {}),
      );
}

/// A device-creation job (POST /virtual-devices/create + its job poll endpoint).
class CreateJob {
  const CreateJob({
    required this.id,
    required this.platform,
    required this.name,
    required this.status,
    required this.progress,
    required this.log,
    required this.error,
    required this.deviceId,
  });

  final String id;
  final String platform;
  final String name;
  final String status; // queued | running | succeeded | failed
  final int? progress; // 0-100 for downloads, else null
  final List<String> log;
  final String? error;
  final String? deviceId; // set on success (AVD name or simulator UDID)

  bool get succeeded => status == 'succeeded';
  bool get failed => status == 'failed';
  bool get done => succeeded || failed;

  factory CreateJob.fromJson(Map<String, dynamic> json) => CreateJob(
        id: json['id'] as String? ?? '',
        platform: json['platform'] as String? ?? '',
        name: json['name'] as String? ?? '',
        status: json['status'] as String? ?? 'queued',
        progress: (json['progress'] as num?)?.toInt(),
        log: ((json['log'] as List<dynamic>?) ?? [])
            .map((e) => e.toString())
            .toList(),
        error: json['error'] as String?,
        deviceId: json['device_id'] as String?,
      );
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

  /// Options for creating new virtual devices. Uses a longer timeout because the
  /// engine queries the Android SDK catalog (`sdkmanager --list`).
  Future<CreateOptions> createOptions() async {
    final res = await http
        .get(_api('/virtual-devices/create-options'))
        .timeout(const Duration(seconds: 100));
    if (res.statusCode != 200) {
      throw EngineException('create-options returned ${res.statusCode}');
    }
    return CreateOptions.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  /// Starts a create job and returns its initial snapshot.
  Future<CreateJob> createVirtualDevice({
    required String platform,
    required String name,
    String? deviceProfile,
    String? systemImage,
    String? deviceType,
    String? runtime,
  }) async {
    final body = await _postJson('/virtual-devices/create', {
      'platform': platform,
      'name': name,
      if (deviceProfile != null) 'device_profile': deviceProfile,
      if (systemImage != null) 'system_image': systemImage,
      if (deviceType != null) 'device_type': deviceType,
      if (runtime != null) 'runtime': runtime,
    });
    return CreateJob.fromJson(body);
  }

  /// Polls a create job's status/progress/log.
  Future<CreateJob> createJob(String jobId) async {
    final res = await http
        .get(_api('/virtual-devices/create/jobs/$jobId'))
        .timeout(_timeout);
    if (res.statusCode != 200) {
      throw EngineException('create job returned ${res.statusCode}');
    }
    return CreateJob.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
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

  // --- Flutter run sessions (managed hot reload / restart / DevTools) ---

  /// Current managed `flutter run` session for [deviceId] (running:false if none).
  Future<Map<String, dynamic>> flutterSession(String deviceId) =>
      _getJson('/devices/$deviceId/flutter/session');

  /// Launches [projectPath] on [deviceId] via `flutter run --machine`. The cold
  /// build can take minutes, so this call uses a long timeout.
  Future<Map<String, dynamic>> flutterRun(
    String deviceId,
    String projectPath, {
    String mode = 'debug',
  }) =>
      _postJson(
        '/devices/$deviceId/flutter/run',
        {'project_path': projectPath, 'mode': mode},
        timeout: const Duration(minutes: 6),
      );

  Future<Map<String, dynamic>> flutterHotReload(String deviceId) => _postJson(
        '/devices/$deviceId/flutter/hot-reload',
        const {},
        timeout: const Duration(seconds: 90),
      );

  Future<Map<String, dynamic>> flutterHotRestart(String deviceId) => _postJson(
        '/devices/$deviceId/flutter/hot-restart',
        const {},
        timeout: const Duration(seconds: 90),
      );

  Future<Map<String, dynamic>> flutterDevtools(String deviceId) => _getJson(
        '/devices/$deviceId/flutter/devtools',
        timeout: const Duration(seconds: 45),
      );

  Future<void> flutterStop(String deviceId) =>
      _delete('/devices/$deviceId/flutter/session');

  Future<void> _post(String path, Map<String, dynamic> body) =>
      _postJson(path, body);

  Future<Map<String, dynamic>> _postJson(
    String path,
    Map<String, dynamic> body, {
    Duration? timeout,
  }) async {
    final res = await http
        .post(
          _api(path),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(timeout ?? _timeout);
    return _decode(res);
  }

  Future<Map<String, dynamic>> _getJson(String path, {Duration? timeout}) async {
    final res = await http.get(_api(path)).timeout(timeout ?? _timeout);
    return _decode(res);
  }

  Future<Map<String, dynamic>> _delete(String path, {Duration? timeout}) async {
    final res = await http.delete(_api(path)).timeout(timeout ?? _timeout);
    return _decode(res);
  }

  /// Validates the response and returns its JSON body (empty map if none).
  Map<String, dynamic> _decode(http.Response res) {
    if (res.statusCode < 200 || res.statusCode >= 300) {
      String detail = 'HTTP ${res.statusCode}';
      try {
        detail =
            (jsonDecode(res.body) as Map<String, dynamic>)['detail'] as String? ??
                detail;
      } catch (_) {
        // keep generic detail
      }
      throw EngineException(detail);
    }
    if (res.body.isEmpty) return const {};
    final decoded = jsonDecode(res.body);
    return decoded is Map<String, dynamic> ? decoded : const {};
  }
}
