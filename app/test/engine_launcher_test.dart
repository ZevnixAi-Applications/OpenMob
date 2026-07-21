import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:openmob/api/engine_discovery.dart';
import 'package:openmob/services/engine_launcher.dart';

void main() {
  test('start command runs through a login shell', () {
    expect(EngineLauncher.shell, '/bin/zsh');
    expect(
      EngineLauncher.shellArgs('uv run openmob serve'),
      ['-l', '-c', 'uv run openmob serve'],
    );
  });

  test('defaultCommand targets the repo engine when run from a checkout', () {
    // flutter test runs with cwd = app/, so the repo's engine/ is found.
    final command = EngineLauncher.defaultCommand();
    expect(command, startsWith('uv run --project "'));
    expect(command, endsWith('openmob serve'));
    expect(command, contains('${Platform.pathSeparator}engine'));
  });

  test('findEngineDir returns a directory containing pyproject.toml', () {
    final dir = EngineLauncher.findEngineDir();
    expect(dir, isNotNull);
    expect(
      File('$dir${Platform.pathSeparator}pyproject.toml').existsSync(),
      isTrue,
    );
  });

  test('instanceLabel strips the mDNS service suffix', () {
    expect(
      EngineDiscovery.instanceLabel(
          'OpenMob Engine on my-mac._openmob._tcp.local'),
      'OpenMob Engine on my-mac',
    );
    expect(EngineDiscovery.instanceLabel('plain-name'), 'plain-name');
  });

  test('discovered engine URL is built from host and port', () {
    const engine =
        DiscoveredEngine(name: 'OpenMob Engine', host: '192.168.1.5', port: 8930);
    expect(engine.url, 'http://192.168.1.5:8930');
    expect(engine.hostPort, '192.168.1.5:8930');
  });
}
