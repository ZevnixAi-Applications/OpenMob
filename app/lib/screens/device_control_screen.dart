import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/demo_badge.dart';
import '../widgets/device_pane.dart';
import '../widgets/toolbar.dart';

/// Mobile full-screen device control: mirror + toolbar for the selected
/// device. Pushed from [DeviceListScreen] on narrow layouts.
class DeviceControlScreen extends StatelessWidget {
  const DeviceControlScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final device = state.selectedDevice;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: OM.sidebar,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text(
          device?.name ?? 'Device',
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
        actions: [
          if (state.demoMode)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: DemoBadge(
                onExit: () {
                  context.read<AppState>().exitDemoMode();
                  Navigator.of(context).maybePop();
                },
              ),
            ),
        ],
      ),
      body: Column(
        children: [
          if (state.lastError != null)
            ErrorBanner(message: state.lastError!),
          const Expanded(child: DevicePane()),
          if (device != null) const DeviceToolbar(),
        ],
      ),
    );
  }
}
