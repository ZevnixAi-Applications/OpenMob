import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:openmob/api/engine_client.dart';
import 'package:openmob/main.dart';
import 'package:openmob/state/app_state.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

// Offline fakes keep the panes on their offline state, so no WebSocket
// connections or reconnect timers run inside the test.
Device fakeDevice(String id) => Device(
      id: id,
      name: 'Dev $id',
      platform: 'android',
      status: 'offline',
      width: 1080,
      height: 1920,
    );

Future<AppState> pumpApp(WidgetTester tester, List<String> ids) async {
  SharedPreferences.setMockInitialValues({});
  final state = AppState();
  state.engineOnline = true;
  state.devices = [for (final id in ids) fakeDevice(id)];
  for (final id in ids) {
    state.openDevice(id);
  }
  await tester.pumpWidget(
    ChangeNotifierProvider.value(
      value: state,
      child: const OpenMobApp(),
    ),
  );
  await tester.pump();
  return state;
}

void main() {
  testWidgets('renders one tab per open device', (tester) async {
    final state = await pumpApp(tester, ['a', 'b']);
    expect(find.byKey(const ValueKey('tab_a')), findsOneWidget);
    expect(find.byKey(const ValueKey('tab_b')), findsOneWidget);
    expect(state.activeDeviceId, 'b');
    state.dispose();
  });

  testWidgets('tapping a tab activates it', (tester) async {
    final state = await pumpApp(tester, ['a', 'b']);
    await tester.tap(find.byKey(const ValueKey('tab_a')));
    await tester.pump();
    expect(state.activeDeviceId, 'a');
    state.dispose();
  });

  testWidgets('closing the active tab activates the neighbor', (tester) async {
    final state = await pumpApp(tester, ['a', 'b']);
    await tester.tap(find.byKey(const ValueKey('tab_a')));
    await tester.pump();

    await tester.tap(find.byKey(const ValueKey('tab_close_a')));
    await tester.pump();
    expect(state.openDeviceIds, ['b']);
    expect(state.activeDeviceId, 'b');
    expect(find.byKey(const ValueKey('tab_a')), findsNothing);
    state.dispose();
  });

  testWidgets('closing the last tab shows the no-device-open hint',
      (tester) async {
    final state = await pumpApp(tester, ['a']);
    await tester.tap(find.byKey(const ValueKey('tab_close_a')));
    await tester.pump();
    expect(state.openDeviceIds, isEmpty);
    expect(find.text('No device open'), findsOneWidget);
    state.dispose();
  });

  testWidgets('layout toggle shows all open devices as panes',
      (tester) async {
    final state = await pumpApp(tester, ['a', 'b']);
    expect(find.byKey(const ValueKey('pane_a')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('layout_toggle')));
    await tester.pump();
    expect(state.layout, PaneLayout.split);
    expect(find.byKey(const ValueKey('pane_a')), findsOneWidget);
    expect(find.byKey(const ValueKey('pane_b')), findsOneWidget);
    state.dispose();
  });

  testWidgets('sync toggle is a no-op in single view and works in split',
      (tester) async {
    final state = await pumpApp(tester, ['a', 'b']);
    // Single view: the button is disabled.
    await tester.tap(find.byKey(const ValueKey('sync_toggle')),
        warnIfMissed: false);
    await tester.pump();
    expect(state.syncMode, isFalse);

    await tester.tap(find.byKey(const ValueKey('layout_toggle')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('sync_toggle')));
    await tester.pump();
    expect(state.syncActive, isTrue);

    // Leaving split view drops sync mode.
    await tester.tap(find.byKey(const ValueKey('layout_toggle')));
    await tester.pump();
    expect(state.syncMode, isFalse);
    state.dispose();
  });

  testWidgets('closing a pane header x closes its tab', (tester) async {
    final state = await pumpApp(tester, ['a', 'b']);
    await tester.tap(find.byKey(const ValueKey('layout_toggle')));
    await tester.pump();

    await tester.tap(find.byKey(const ValueKey('pane_close_a')));
    await tester.pump();
    expect(state.openDeviceIds, ['b']);
    expect(find.byKey(const ValueKey('pane_a')), findsNothing);
    state.dispose();
  });
}
