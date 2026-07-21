import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/engine_client.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// VS Code-style tab strip for open devices, with layout and sync toggles
/// in the right corner. Overflowing tabs scroll horizontally.
class DeviceTabBar extends StatelessWidget {
  const DeviceTabBar({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Container(
      height: 36,
      decoration: const BoxDecoration(
        color: OM.sidebar,
        border: Border(bottom: BorderSide(color: OM.border)),
      ),
      child: Row(
        children: [
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  for (final id in state.openDeviceIds)
                    _DeviceTab(
                      id: id,
                      device: state.deviceById(id),
                      active: id == state.activeDeviceId,
                      onTap: () => state.activateDevice(id),
                      onClose: () => state.closeDevice(id),
                    ),
                ],
              ),
            ),
          ),
          Container(width: 1, color: OM.border),
          const SizedBox(width: 4),
          _SyncToggle(state: state),
          _LayoutToggle(state: state),
          const SizedBox(width: 4),
        ],
      ),
    );
  }
}

class _SyncToggle extends StatelessWidget {
  const _SyncToggle({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final enabled = state.layout == PaneLayout.split;
    final on = state.syncActive;
    return Tooltip(
      message: enabled
          ? (on ? 'Sync input: on' : 'Sync input: off')
          : 'Sync input (split view only)',
      child: IconButton(
        key: const ValueKey('sync_toggle'),
        icon: Icon(
          Icons.link,
          size: 17,
          color: on ? OM.sync : (enabled ? OM.text : OM.textMuted),
        ),
        onPressed: enabled ? state.toggleSync : null,
        visualDensity: VisualDensity.compact,
      ),
    );
  }
}

class _LayoutToggle extends StatelessWidget {
  const _LayoutToggle({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final split = state.layout == PaneLayout.split;
    return Tooltip(
      message: split ? 'Single view' : 'Split view (all open devices)',
      child: IconButton(
        key: const ValueKey('layout_toggle'),
        icon: Icon(
          Icons.grid_view,
          size: 16,
          color: split ? OM.accent : OM.text,
        ),
        onPressed: state.toggleLayout,
        visualDensity: VisualDensity.compact,
      ),
    );
  }
}

class _DeviceTab extends StatelessWidget {
  const _DeviceTab({
    required this.id,
    required this.device,
    required this.active,
    required this.onTap,
    required this.onClose,
  });

  final String id;

  /// Null when the engine has not (yet) reported this device; rendered as
  /// an offline tab until the next refresh resolves or prunes it.
  final Device? device;
  final bool active;
  final VoidCallback onTap;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final online = device?.online ?? false;
    final name = device?.name ?? id;
    final textColor = online
        ? (active ? OM.text : OM.textMuted)
        : OM.textMuted.withValues(alpha: 0.75);

    return InkWell(
      key: ValueKey('tab_$id'),
      onTap: onTap,
      hoverColor: OM.cardHover,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 200),
        padding: const EdgeInsets.only(left: 12, right: 2),
        decoration: BoxDecoration(
          color: active ? OM.bg : Colors.transparent,
          border: Border(
            right: const BorderSide(color: OM.border),
            top: BorderSide(
              color: active ? OM.accent : Colors.transparent,
              width: 2,
            ),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              (device?.isIos ?? false)
                  ? Icons.phone_iphone
                  : Icons.phone_android,
              size: 14,
              color: online
                  ? (active ? OM.accent : OM.textMuted)
                  : OM.textMuted.withValues(alpha: 0.6),
            ),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 12, color: textColor),
              ),
            ),
            if (!online) ...[
              const SizedBox(width: 5),
              Container(
                width: 6,
                height: 6,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: OM.danger,
                ),
              ),
            ],
            const SizedBox(width: 2),
            Tooltip(
              message: 'Close',
              child: IconButton(
                key: ValueKey('tab_close_$id'),
                icon: const Icon(Icons.close, size: 13),
                onPressed: onClose,
                padding: EdgeInsets.zero,
                constraints:
                    const BoxConstraints(minWidth: 26, minHeight: 26),
                visualDensity: VisualDensity.compact,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
