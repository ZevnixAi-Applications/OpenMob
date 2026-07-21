import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../theme.dart';
import 'demo_badge.dart';
import 'engine_settings.dart';

/// Engine status header: status dot, name, version/demo state, settings gear.
/// Used at the top of the desktop sidebar and of the mobile device list.
class EngineHeader extends StatelessWidget {
  const EngineHeader({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
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
                  state.demoMode
                      ? 'demo mode'
                      : online
                          ? 'connected · v${state.engineVersion ?? '?'}'
                          : 'offline',
                  style: const TextStyle(
                      color: OM.textMuted, fontSize: 11),
                ),
              ],
            ),
          ),
          if (state.demoMode)
            DemoBadge(
              onExit: () => context.read<AppState>().exitDemoMode(),
            ),
          Tooltip(
            message: 'Engine settings',
            child: IconButton(
              icon: const Icon(Icons.settings_outlined, size: 16),
              visualDensity: VisualDensity.compact,
              onPressed: () => showEngineSettings(context),
            ),
          ),
        ],
      ),
    );
  }
}
