import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/engine_client.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// "DEVICES" caption + refresh button + scrollable device rows.
/// Used by the desktop sidebar and the mobile device-list screen; the caller
/// decides what selecting a device does via [onDeviceTap].
class DeviceList extends StatelessWidget {
  const DeviceList({super.key, required this.onDeviceTap});

  final void Function(Device device) onDeviceTap;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 8, 6),
          child: Row(
            children: [
              const Text(
                'DEVICES',
                style: TextStyle(
                  color: OM.textMuted,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.2,
                ),
              ),
              const Spacer(),
              Tooltip(
                message: 'Refresh devices',
                child: IconButton(
                  icon: const Icon(Icons.refresh, size: 16),
                  onPressed: state.refresh,
                  visualDensity: VisualDensity.compact,
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: state.devices.isEmpty
              ? Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    state.engineOnline
                        ? 'No devices detected.'
                        : 'Engine offline.',
                    style: const TextStyle(
                        color: OM.textMuted, fontSize: 12),
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  itemCount: state.devices.length,
                  itemBuilder: (context, i) {
                    final device = state.devices[i];
                    return _DeviceRow(
                      device: device,
                      selected: device.id == state.selectedDeviceId,
                      onTap: () => onDeviceTap(device),
                    );
                  },
                ),
        ),
      ],
    );
  }
}

class _DeviceRow extends StatelessWidget {
  const _DeviceRow({
    required this.device,
    required this.selected,
    required this.onTap,
  });

  final Device device;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Material(
        color: selected ? OM.card : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          hoverColor: OM.cardHover,
          child: Container(
            padding:
                const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: selected ? OM.accent.withValues(alpha: 0.5)
                    : Colors.transparent,
              ),
            ),
            child: Row(
              children: [
                Icon(
                  device.isIos
                      ? Icons.phone_iphone
                      : Icons.phone_android,
                  size: 20,
                  color: selected ? OM.accent : OM.textMuted,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        device.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w500),
                      ),
                      Text(
                        device.id,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            color: OM.textMuted, fontSize: 11),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  width: 7,
                  height: 7,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: device.online ? OM.accent : OM.textMuted,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
