import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../theme.dart';
import 'device_list.dart';
import 'engine_header.dart';

/// Desktop sidebar: engine header + device list in a fixed-width column.
class Sidebar extends StatelessWidget {
  const Sidebar({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    return Container(
      width: 260,
      decoration: const BoxDecoration(
        color: OM.sidebar,
        border: Border(right: BorderSide(color: OM.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const EngineHeader(),
          const Divider(height: 1),
          Expanded(
            child: DeviceList(
              onDeviceTap: (device) => state.selectDevice(device.id),
            ),
          ),
        ],
      ),
    );
  }
}
