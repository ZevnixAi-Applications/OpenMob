import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/engine_client.dart';
import '../state/app_state.dart';
import '../theme.dart';

class Sidebar extends StatelessWidget {
  const Sidebar({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Container(
      width: 260,
      decoration: const BoxDecoration(
        color: OM.sidebar,
        border: Border(right: BorderSide(color: OM.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _EngineHeader(state: state),
          const Divider(height: 1),
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
                        onTap: () => state.selectDevice(device.id),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _EngineHeader extends StatelessWidget {
  const _EngineHeader({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final online = state.engineOnline;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 8, 12),
      child: Row(
        children: [
          Container(
            width: 9,
            height: 9,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: online ? OM.accent : OM.danger,
              boxShadow: online
                  ? [
                      BoxShadow(
                        color: OM.accent.withValues(alpha: 0.45),
                        blurRadius: 6,
                      )
                    ]
                  : null,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'OpenMob Engine',
                  style: TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w600),
                ),
                Text(
                  online
                      ? 'connected · v${state.engineVersion ?? '?'}'
                      : 'offline',
                  style: const TextStyle(
                      color: OM.textMuted, fontSize: 11),
                ),
              ],
            ),
          ),
          Tooltip(
            message: 'Engine settings',
            child: IconButton(
              icon: const Icon(Icons.settings_outlined, size: 16),
              visualDensity: VisualDensity.compact,
              onPressed: () => _showSettings(context),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _showSettings(BuildContext context) async {
    final state = context.read<AppState>();
    final controller = TextEditingController(text: state.baseUrl);
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Engine settings',
            style: TextStyle(fontSize: 16)),
        content: SizedBox(
          width: 360,
          child: TextField(
            controller: controller,
            autofocus: true,
            style: const TextStyle(fontSize: 13),
            decoration: const InputDecoration(
              labelText: 'Engine base URL',
              hintText: AppState.defaultBaseUrl,
              border: OutlineInputBorder(),
            ),
            onSubmitted: (v) => Navigator.of(context).pop(v),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(controller.text),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (result != null && result.trim().isNotEmpty) {
      await state.setBaseUrl(result);
    }
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
