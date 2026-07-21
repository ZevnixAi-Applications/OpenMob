import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/engine_client.dart';
import '../services/engine_launcher.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'create_device_dialog.dart';
import 'engine_discovery_dialog.dart';

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
          Expanded(
            child: ListView(
              padding: const EdgeInsets.only(bottom: 12),
              children: [
                _SectionHeader(
                  title: 'DEVICES',
                  trailing: Tooltip(
                    message: 'Refresh devices',
                    child: IconButton(
                      icon: const Icon(Icons.refresh, size: 16),
                      onPressed: state.refresh,
                      visualDensity: VisualDensity.compact,
                    ),
                  ),
                ),
                if (state.devices.isEmpty)
                  _SectionNote(
                    text: state.engineOnline
                        ? 'No devices detected.'
                        : 'Engine offline.',
                  )
                else
                  for (final device in state.devices)
                    Padding(
                      padding:
                          const EdgeInsets.symmetric(horizontal: 8),
                      child: _DeviceRow(
                        device: device,
                        selected: device.id == state.activeDeviceId,
                        onTap: () => state.openDevice(device.id),
                      ),
                    ),
                _SectionHeader(
                  title: 'VIRTUAL DEVICES',
                  trailing: Tooltip(
                    message: 'Create a new virtual device',
                    child: IconButton(
                      icon: const Icon(Icons.add, size: 16),
                      onPressed: () => showDialog<void>(
                        context: context,
                        builder: (_) => const CreateDeviceDialog(),
                      ),
                      visualDensity: VisualDensity.compact,
                    ),
                  ),
                ),
                if (state.virtualDevices.isEmpty)
                  _SectionNote(
                    text: state.engineOnline
                        ? 'No AVDs or simulators found.'
                        : 'Engine offline.',
                  )
                else
                  for (final virtual in state.virtualDevices)
                    Padding(
                      padding:
                          const EdgeInsets.symmetric(horizontal: 8),
                      child: _VirtualDeviceRow(
                        device: virtual,
                        booting:
                            state.launchingNames.contains(virtual.name),
                        onLaunch: () =>
                            state.launchVirtualDevice(virtual.name),
                      ),
                    ),
              ],
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
    await showDialog<void>(
      context: context,
      builder: (context) => const _SettingsDialog(),
    );
  }
}

class _SettingsDialog extends StatefulWidget {
  const _SettingsDialog();

  @override
  State<_SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<_SettingsDialog> {
  late final TextEditingController _urlController;
  late final TextEditingController _commandController;

  @override
  void initState() {
    super.initState();
    final state = context.read<AppState>();
    _urlController = TextEditingController(text: state.baseUrl);
    _commandController = TextEditingController(text: state.engineCommand);
  }

  @override
  void dispose() {
    _urlController.dispose();
    _commandController.dispose();
    super.dispose();
  }

  Future<void> _findEngines() async {
    final url = await showDialog<String>(
      context: context,
      builder: (context) => const EngineDiscoveryDialog(),
    );
    if (url != null && url.isNotEmpty) {
      _urlController.text = url;
    }
  }

  Future<void> _save() async {
    final state = context.read<AppState>();
    Navigator.of(context).pop();
    if (EngineLauncher.isSupported) {
      await state.setEngineCommand(_commandController.text);
    }
    final url = _urlController.text.trim();
    if (url.isNotEmpty && url != state.baseUrl) {
      await state.setBaseUrl(url);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Engine settings', style: TextStyle(fontSize: 16)),
      content: SizedBox(
        width: 400,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _urlController,
              autofocus: true,
              style: const TextStyle(fontSize: 13),
              decoration: const InputDecoration(
                labelText: 'Engine base URL',
                hintText: AppState.defaultBaseUrl,
                border: OutlineInputBorder(),
              ),
              onSubmitted: (_) => _save(),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                icon: const Icon(Icons.wifi_find_outlined, size: 16),
                label: const Text('Find engines on my network',
                    style: TextStyle(fontSize: 12)),
                onPressed: _findEngines,
              ),
            ),
            if (EngineLauncher.isSupported) ...[
              const SizedBox(height: 16),
              TextField(
                controller: _commandController,
                style: const TextStyle(fontSize: 13),
                decoration: const InputDecoration(
                  labelText: 'Start engine command',
                  helperText:
                      'Used by the "Start engine" button. Leave empty to reset.',
                  helperStyle: TextStyle(fontSize: 11, color: OM.textMuted),
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _save,
          child: const Text('Save'),
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

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title, this.trailing});

  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 14, 8, 6),
      child: Row(
        children: [
          Text(
            title,
            style: const TextStyle(
              color: OM.textMuted,
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 1.2,
            ),
          ),
          const Spacer(),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

class _SectionNote extends StatelessWidget {
  const _SectionNote({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Text(
        text,
        style: const TextStyle(color: OM.textMuted, fontSize: 12),
      ),
    );
  }
}

class _VirtualDeviceRow extends StatelessWidget {
  const _VirtualDeviceRow({
    required this.device,
    required this.booting,
    required this.onLaunch,
  });

  final VirtualDevice device;
  final bool booting;
  final VoidCallback onLaunch;

  @override
  Widget build(BuildContext context) {
    final subtitle = booting
        ? 'booting…'
        : device.kind == 'avd'
            ? 'Android emulator'
            : 'iOS Simulator';
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          children: [
            Icon(
              device.isIos ? Icons.phone_iphone : Icons.phone_android,
              size: 20,
              color: OM.textMuted,
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
                        fontSize: 13, fontWeight: FontWeight.w500),
                  ),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: booting ? OM.accent : OM.textMuted,
                      fontSize: 11,
                    ),
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
                color: device.running ? OM.accent : OM.textMuted,
              ),
            ),
            if (device.running || booting)
              const SizedBox(width: 30)
            else
              Tooltip(
                message: 'Launch ${device.name}',
                child: IconButton(
                  icon: const Icon(Icons.play_arrow, size: 18),
                  color: OM.accent,
                  visualDensity: VisualDensity.compact,
                  onPressed: onLaunch,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
