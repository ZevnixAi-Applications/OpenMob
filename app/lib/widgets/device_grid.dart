import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/engine_client.dart';
import '../state/app_state.dart';
import 'device_pane.dart';

/// Split view: every open device visible at once. 1-3 devices sit side by
/// side; 4 or more flow into 2-column grid rows. Each pane runs its own
/// screen stream and input handling.
class DeviceGrid extends StatelessWidget {
  const DeviceGrid({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final devices = state.openDevices;
    if (devices.isEmpty) return const SizedBox.shrink();

    Widget paneFor(Device d) => Padding(
          padding: const EdgeInsets.all(6),
          child: DevicePane(
            key: ValueKey('pane_${d.id}'),
            device: d,
            streamUri: state.client.streamUri(d.id),
            focused: d.id == state.activeDeviceId,
            syncOn: state.syncActive,
            flashTick: state.syncPulse,
            flashSourceId: state.syncPulseSourceId,
            onFocus: () => state.activateDevice(d.id),
            onClose: () => state.closeDevice(d.id),
            onTapAt: (x, y) => state.tapDevice(d.id, x, y),
            onSwipe: (x1, y1, x2, y2, ms) =>
                state.swipeDevice(d.id, x1, y1, x2, y2, ms),
          ),
        );

    if (devices.length <= 3) {
      return Padding(
        padding: const EdgeInsets.all(6),
        child: Row(
          children: [
            for (final d in devices) Expanded(child: paneFor(d)),
          ],
        ),
      );
    }

    final rows = <Widget>[];
    for (var i = 0; i < devices.length; i += 2) {
      rows.add(
        Expanded(
          child: Row(
            children: [
              Expanded(child: paneFor(devices[i])),
              if (i + 1 < devices.length)
                Expanded(child: paneFor(devices[i + 1]))
              else
                const Expanded(child: SizedBox()),
            ],
          ),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.all(6),
      child: Column(children: rows),
    );
  }
}
