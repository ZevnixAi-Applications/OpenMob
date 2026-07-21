import 'package:flutter_test/flutter_test.dart';
import 'package:openmob/api/engine_client.dart';

void main() {
  final client = EngineClient('http://127.0.0.1:8930');

  test('unscoped log stream carries no scope params', () {
    final uri = client.logsStreamUri('dev1');
    expect(uri.scheme, 'ws');
    expect(uri.path, '/api/v1/devices/dev1/logs/stream');
    expect(uri.queryParameters, isEmpty);
  });

  test('package scope + flutter toggle become query params', () {
    final uri = client.logsStreamUri(
      'dev1',
      package: 'ai.zevnix.openmob_testbed',
      flutter: true,
      filter: 'boom',
    );
    expect(uri.queryParameters['package'], 'ai.zevnix.openmob_testbed');
    expect(uri.queryParameters['flutter'], 'true');
    expect(uri.queryParameters['filter'], 'boom');
    expect(uri.queryParameters.containsKey('scope'), isFalse);
  });

  test('foreground scope maps to scope=foreground', () {
    final uri = client.logsStreamUri('dev1', scope: 'foreground');
    expect(uri.queryParameters['scope'], 'foreground');
    expect(uri.queryParameters.containsKey('package'), isFalse);
  });

  test('flutter=false is omitted', () {
    final uri = client.logsStreamUri('dev1', flutter: false);
    expect(uri.queryParameters.containsKey('flutter'), isFalse);
  });

  test('https base upgrades to wss', () {
    final secure = EngineClient('https://example.com:8443');
    expect(secure.logsStreamUri('dev1').scheme, 'wss');
  });
}
