import 'package:flutter_test/flutter_test.dart';
import 'package:openmob/state/app_state.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('openDevice adds a tab and activates it; reopening only activates',
      () {
    final s = AppState();
    s.openDevice('a');
    s.openDevice('b');
    expect(s.openDeviceIds, ['a', 'b']);
    expect(s.activeDeviceId, 'b');

    s.openDevice('a'); // already open: no duplicate, just activate
    expect(s.openDeviceIds, ['a', 'b']);
    expect(s.activeDeviceId, 'a');
    s.dispose();
  });

  test('activateDevice switches only to open tabs', () {
    final s = AppState();
    s.openDevice('a');
    s.openDevice('b');
    s.activateDevice('a');
    expect(s.activeDeviceId, 'a');
    s.activateDevice('nope');
    expect(s.activeDeviceId, 'a');
    s.dispose();
  });

  test('closing the active middle tab activates the right neighbor', () {
    final s = AppState();
    s.openDevice('a');
    s.openDevice('b');
    s.openDevice('c');
    s.activateDevice('b');
    s.closeDevice('b');
    expect(s.openDeviceIds, ['a', 'c']);
    expect(s.activeDeviceId, 'c');
    s.dispose();
  });

  test('closing the active rightmost tab activates the left neighbor', () {
    final s = AppState();
    s.openDevice('a');
    s.openDevice('b');
    s.openDevice('c'); // active
    s.closeDevice('c');
    expect(s.openDeviceIds, ['a', 'b']);
    expect(s.activeDeviceId, 'b');
    s.dispose();
  });

  test('closing a non-active tab keeps the active tab', () {
    final s = AppState();
    s.openDevice('a');
    s.openDevice('b');
    s.closeDevice('a');
    expect(s.openDeviceIds, ['b']);
    expect(s.activeDeviceId, 'b');
    s.dispose();
  });

  test('closing the last tab clears active and resets layout + sync', () {
    final s = AppState();
    s.openDevice('a');
    s.openDevice('b');
    s.setLayout(PaneLayout.split);
    s.toggleSync();
    expect(s.syncActive, isTrue);

    s.closeDevice('a');
    s.closeDevice('b');
    expect(s.openDeviceIds, isEmpty);
    expect(s.activeDeviceId, isNull);
    expect(s.layout, PaneLayout.single);
    expect(s.syncMode, isFalse);
    s.dispose();
  });

  test('sync toggle only works in split layout and resets on single', () {
    final s = AppState();
    s.openDevice('a');
    s.toggleSync(); // single layout: no-op
    expect(s.syncMode, isFalse);

    s.setLayout(PaneLayout.split);
    s.toggleSync();
    expect(s.syncMode, isTrue);
    expect(s.syncActive, isTrue);

    s.setLayout(PaneLayout.single);
    expect(s.syncMode, isFalse);
    expect(s.syncActive, isFalse);
    s.dispose();
  });

  test('restores open tabs and active tab from preferences', () async {
    SharedPreferences.setMockInitialValues({
      // Unreachable engine so init()'s refresh cannot repopulate/prune.
      'engine_base_url': 'http://127.0.0.1:1',
      'open_device_ids': ['x', 'y'],
      'active_device_id': 'y',
    });
    final s = AppState();
    await s.init();
    expect(s.openDeviceIds, ['x', 'y']);
    expect(s.activeDeviceId, 'y');
    s.dispose();
  });

  test('falls back to the first restored tab when active id is stale',
      () async {
    SharedPreferences.setMockInitialValues({
      'engine_base_url': 'http://127.0.0.1:1',
      'open_device_ids': ['x', 'y'],
      'active_device_id': 'gone',
    });
    final s = AppState();
    await s.init();
    expect(s.activeDeviceId, 'x');
    s.dispose();
  });
}
