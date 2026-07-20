import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../theme.dart';
import 'demo_badge.dart';
import 'device_screen.dart';
import 'engine_settings.dart';

/// Main device content: the live mirror for the selected device, or a
/// contextual empty state. Shared by the desktop main pane and the mobile
/// device-control screen.
class DevicePane extends StatelessWidget {
  const DevicePane({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    if (!state.engineOnline) {
      return const EngineOfflineState();
    }
    if (state.devices.isEmpty) {
      return const NoDevicesState();
    }
    final device = state.selectedDevice;
    if (device == null) {
      return const EmptyState(
        icon: Icons.smartphone_outlined,
        title: 'No device selected',
        subtitle: 'Pick a device to see its screen.',
      );
    }
    if (!device.online) {
      return const EmptyState(
        icon: Icons.phonelink_off_outlined,
        title: 'Device offline',
        subtitle: 'Reconnect the device to stream its screen.',
      );
    }
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Stack(
        children: [
          DeviceScreen(
            key: ValueKey(
                '${state.demoMode}/${state.baseUrl}/${device.id}'),
            connectFrames: () => state.client.frames(device.id),
            deviceWidth: device.width,
            deviceHeight: device.height,
            onTapAt: (x, y) {
              state.tap(x, y);
              if (state.demoMode) _showDemoFeedback(context, 'Tap sent');
            },
            onSwipe: (x1, y1, x2, y2, ms) {
              state.swipe(x1, y1, x2, y2, ms);
              if (state.demoMode) _showDemoFeedback(context, 'Swipe sent');
            },
          ),
          if (state.demoMode)
            const Positioned(top: 6, left: 6, child: DemoBadge()),
        ],
      ),
    );
  }

  void _showDemoFeedback(BuildContext context, String message) {
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          '$message (demo — no real device)',
          style: const TextStyle(fontSize: 12, color: OM.text),
        ),
        backgroundColor: OM.cardHover,
        behavior: SnackBarBehavior.floating,
        duration: const Duration(milliseconds: 900),
      ),
    );
  }
}

/// Engine unreachable: explains the URL being tried and offers settings/demo.
class EngineOfflineState extends StatelessWidget {
  const EngineOfflineState({super.key, this.onDemoEntered});

  /// Forwarded to [TryDemoButton] (mobile opens the control screen with it).
  final VoidCallback? onDemoEntered;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return EmptyState(
      icon: Icons.power_off_outlined,
      title: 'Engine offline',
      subtitle: 'Can\'t reach the engine at ${state.baseUrl}.\n'
          'Run `openmob serve` on your computer and make sure this device '
          'is on the same network.',
      actions: [
        OutlinedButton.icon(
          icon: const Icon(Icons.settings_outlined, size: 16),
          label: const Text('Engine settings',
              style: TextStyle(fontSize: 13)),
          onPressed: () => showEngineSettings(context),
        ),
        TryDemoButton(onEntered: onDemoEntered),
      ],
    );
  }
}

/// Engine reachable but no devices plugged in; still offers the demo.
class NoDevicesState extends StatelessWidget {
  const NoDevicesState({super.key, this.onDemoEntered});

  /// Forwarded to [TryDemoButton] (mobile opens the control screen with it).
  final VoidCallback? onDemoEntered;

  @override
  Widget build(BuildContext context) {
    return EmptyState(
      icon: Icons.usb_outlined,
      title: 'No devices',
      subtitle: 'Plug a device with USB debugging enabled '
          'into the computer running the engine.',
      actions: [TryDemoButton(onEntered: onDemoEntered)],
    );
  }
}

/// Transient error banner shown above the device pane.
class ErrorBanner extends StatelessWidget {
  const ErrorBanner({super.key, required this.message});

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

class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    this.actions = const [],
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        margin: const EdgeInsets.all(24),
        padding:
            const EdgeInsets.symmetric(horizontal: 36, vertical: 28),
        constraints: const BoxConstraints(maxWidth: 420),
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
              textAlign: TextAlign.center,
              style: const TextStyle(color: OM.textMuted, fontSize: 12),
            ),
            if (actions.isNotEmpty) ...[
              const SizedBox(height: 18),
              Wrap(
                spacing: 10,
                runSpacing: 8,
                alignment: WrapAlignment.center,
                children: actions,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
