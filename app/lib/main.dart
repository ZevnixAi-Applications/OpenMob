import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'services/engine_launcher.dart';
import 'state/app_state.dart';
import 'theme.dart';
import 'widgets/device_screen.dart';
import 'widgets/engine_discovery_dialog.dart';
import 'widgets/sidebar.dart';
import 'widgets/toolbar.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final state = AppState();
  state.init();
  runApp(
    ChangeNotifierProvider.value(
      value: state,
      child: const OpenMobApp(),
    ),
  );
}

class OpenMobApp extends StatelessWidget {
  const OpenMobApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'OpenMob',
      debugShowCheckedModeBanner: false,
      theme: OM.theme(),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      body: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Sidebar(),
          Expanded(
            child: Column(
              children: [
                if (state.lastError != null)
                  _ErrorBanner(message: state.lastError!),
                Expanded(child: _MainPane(state: state)),
                if (state.selectedDevice != null) const DeviceToolbar(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MainPane extends StatelessWidget {
  const _MainPane({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    if (!state.engineOnline) {
      return _EngineOfflinePane(state: state);
    }
    if (state.devices.isEmpty) {
      return const _EmptyState(
        icon: Icons.usb_outlined,
        title: 'No devices',
        subtitle: 'Plug in a device with USB debugging enabled.',
      );
    }
    final device = state.selectedDevice;
    if (device == null) {
      return const _EmptyState(
        icon: Icons.smartphone_outlined,
        title: 'No device selected',
        subtitle: 'Pick a device from the sidebar to see its screen.',
      );
    }
    if (!device.online) {
      return const _EmptyState(
        icon: Icons.phonelink_off_outlined,
        title: 'Device offline',
        subtitle: 'Reconnect the device to stream its screen.',
      );
    }
    return Padding(
      padding: const EdgeInsets.all(16),
      child: DeviceScreen(
        key: ValueKey('${state.baseUrl}/${device.id}'),
        streamUri: state.client.streamUri(device.id),
        deviceWidth: device.width,
        deviceHeight: device.height,
        onTapAt: (x, y) => state.tap(x, y),
        onSwipe: (x1, y1, x2, y2, ms) => state.swipe(x1, y1, x2, y2, ms),
      ),
    );
  }
}

class _EngineOfflinePane extends StatelessWidget {
  const _EngineOfflinePane({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 440),
        padding: const EdgeInsets.symmetric(horizontal: 36, vertical: 28),
        decoration: BoxDecoration(
          color: OM.card,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: OM.border),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.power_off_outlined, size: 34, color: OM.textMuted),
            const SizedBox(height: 14),
            const Text(
              'Engine offline',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 6),
            const Text(
              'Run `openmob serve` to start the engine.',
              style: TextStyle(color: OM.textMuted, fontSize: 12),
            ),
            const SizedBox(height: 16),
            if (state.engineStarting)
              const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  SizedBox(width: 10),
                  Text('Starting engine…',
                      style: TextStyle(color: OM.textMuted, fontSize: 12)),
                ],
              )
            else
              Wrap(
                spacing: 10,
                runSpacing: 8,
                alignment: WrapAlignment.center,
                children: [
                  if (EngineLauncher.isSupported)
                    FilledButton.icon(
                      icon: const Icon(Icons.play_arrow, size: 16),
                      label: const Text('Start engine',
                          style: TextStyle(fontSize: 12)),
                      onPressed: state.startEngine,
                    ),
                  OutlinedButton.icon(
                    icon: const Icon(Icons.wifi_find_outlined, size: 16),
                    label: const Text('Find engines on my network',
                        style: TextStyle(fontSize: 12)),
                    onPressed: () => showEngineDiscoveryDialog(context),
                  ),
                ],
              ),
            if (state.engineStartError != null) ...[
              const SizedBox(height: 12),
              Text(
                state.engineStartError!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: OM.danger, fontSize: 11),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        padding:
            const EdgeInsets.symmetric(horizontal: 36, vertical: 28),
        decoration: BoxDecoration(
          color: OM.card,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: OM.border),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 34, color: OM.textMuted),
            const SizedBox(height: 14),
            Text(
              title,
              style: const TextStyle(
                  fontSize: 15, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 6),
            Text(
              subtitle,
              style: const TextStyle(color: OM.textMuted, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
      color: OM.danger.withValues(alpha: 0.12),
      child: Text(
        message,
        style: const TextStyle(color: OM.danger, fontSize: 12),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}
