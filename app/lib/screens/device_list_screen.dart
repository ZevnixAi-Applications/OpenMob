import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/engine_client.dart';
import '../state/app_state.dart';
import '../widgets/device_list.dart';
import '../widgets/device_pane.dart';
import '../widgets/engine_header.dart';
import 'device_control_screen.dart';

/// Mobile home: engine status header + device list. Tapping a device (or
/// entering demo mode) opens the full-screen [DeviceControlScreen].
class DeviceListScreen extends StatelessWidget {
  const DeviceListScreen({super.key});

  void _openDevice(BuildContext context, Device device) {
    context.read<AppState>().selectDevice(device.id);
    _openControlScreen(context);
  }

  void _openControlScreen(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => const DeviceControlScreen(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const EngineHeader(),
            const Divider(height: 1),
            Expanded(
              child: !state.engineOnline
                  ? EngineOfflineState(
                      onDemoEntered: () => _openControlScreen(context),
                    )
                  : state.devices.isEmpty
                      ? NoDevicesState(
                          onDemoEntered: () => _openControlScreen(context),
                        )
                      : DeviceList(
                          onDeviceTap: (d) => _openDevice(context, d),
                        ),
            ),
          ],
        ),
      ),
    );
  }
}
