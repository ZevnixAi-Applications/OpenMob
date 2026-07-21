import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../theme.dart';

/// Small accent chip marking demo mode. Optionally shows an exit button.
class DemoBadge extends StatelessWidget {
  const DemoBadge({super.key, this.onExit});

  /// When non-null an "exit demo" close button is shown next to the badge.
  final VoidCallback? onExit;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: OM.accent.withValues(alpha: 0.14),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: OM.accent.withValues(alpha: 0.6)),
          ),
          child: const Text(
            'DEMO',
            style: TextStyle(
              color: OM.accent,
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.2,
            ),
          ),
        ),
        if (onExit != null)
          Tooltip(
            message: 'Exit demo',
            child: IconButton(
              icon: const Icon(Icons.close, size: 16),
              visualDensity: VisualDensity.compact,
              onPressed: onExit,
            ),
          ),
      ],
    );
  }
}

/// "Try demo" button shown on connect/empty states so the app can be
/// exercised without a real engine (e.g. by store reviewers).
class TryDemoButton extends StatelessWidget {
  const TryDemoButton({super.key, this.onEntered});

  /// Called after demo mode is active (mobile uses this to open the
  /// device-control screen directly).
  final VoidCallback? onEntered;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      icon: const Icon(Icons.play_circle_outline, size: 16, color: OM.accent),
      label: const Text(
        'Try demo',
        style: TextStyle(color: OM.accent, fontSize: 13),
      ),
      style: OutlinedButton.styleFrom(
        side: BorderSide(color: OM.accent.withValues(alpha: 0.55)),
      ),
      onPressed: () async {
        await context.read<AppState>().enterDemoMode();
        onEntered?.call();
      },
    );
  }
}
