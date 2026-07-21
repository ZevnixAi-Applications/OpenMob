import 'package:flutter/material.dart';

import '../api/engine_client.dart';
import '../theme.dart';
import 'device_screen.dart';

/// One device pane in split view: a slim header (name + close) above the
/// live mirror. Clicking anywhere focuses the pane (making it the target of
/// the global toolbar). While sync mode is on, every pane gets a colored
/// border and mirrored panes flash briefly when a broadcast fires.
class DevicePane extends StatefulWidget {
  const DevicePane({
    super.key,
    required this.device,
    required this.streamUri,
    required this.focused,
    required this.syncOn,
    required this.flashTick,
    required this.flashSourceId,
    required this.onFocus,
    required this.onClose,
    required this.onTapAt,
    required this.onSwipe,
  });

  final Device device;
  final Uri streamUri;
  final bool focused;
  final bool syncOn;

  /// Monotonic counter bumped on every sync broadcast.
  final int flashTick;

  /// Device that originated the last broadcast (does not flash).
  final String? flashSourceId;

  final VoidCallback onFocus;
  final VoidCallback onClose;
  final void Function(int x, int y) onTapAt;
  final void Function(int x1, int y1, int x2, int y2, int durationMs) onSwipe;

  @override
  State<DevicePane> createState() => _DevicePaneState();
}

class _DevicePaneState extends State<DevicePane>
    with SingleTickerProviderStateMixin {
  late final AnimationController _flash = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 350),
  );

  @override
  void didUpdateWidget(DevicePane oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.flashTick != oldWidget.flashTick &&
        widget.syncOn &&
        widget.device.online &&
        widget.flashSourceId != widget.device.id) {
      _flash.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _flash.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final device = widget.device;
    final borderColor = widget.syncOn
        ? OM.sync
        : (widget.focused ? OM.accent : OM.border);

    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: (_) => widget.onFocus(),
      child: Container(
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(
          color: OM.bg,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: borderColor,
            width: widget.focused ? 2 : 1,
          ),
        ),
        child: Column(
          children: [
            _PaneHeader(
              device: device,
              focused: widget.focused,
              onClose: widget.onClose,
            ),
            Expanded(
              child: Stack(
                fit: StackFit.expand,
                children: [
                  if (device.online)
                    DeviceScreen(
                      key: ValueKey('pane_stream_${widget.streamUri}'),
                      streamUri: widget.streamUri,
                      deviceWidth: device.width,
                      deviceHeight: device.height,
                      onTapAt: widget.onTapAt,
                      onSwipe: widget.onSwipe,
                    )
                  else
                    _OfflineBody(syncOn: widget.syncOn),
                  // Brief flash overlay when a sync broadcast is mirrored
                  // onto this pane.
                  AnimatedBuilder(
                    animation: _flash,
                    builder: (context, _) {
                      final v =
                          _flash.isAnimating ? (1 - _flash.value) : 0.0;
                      if (v == 0) return const SizedBox.shrink();
                      return IgnorePointer(
                        child: Container(
                          color: OM.sync.withValues(alpha: 0.28 * v),
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PaneHeader extends StatelessWidget {
  const _PaneHeader({
    required this.device,
    required this.focused,
    required this.onClose,
  });

  final Device device;
  final bool focused;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 26,
      padding: const EdgeInsets.only(left: 8, right: 2),
      decoration: const BoxDecoration(
        color: OM.sidebar,
        border: Border(bottom: BorderSide(color: OM.border)),
      ),
      child: Row(
        children: [
          Icon(
            device.isIos ? Icons.phone_iphone : Icons.phone_android,
            size: 12,
            color: device.online
                ? (focused ? OM.accent : OM.textMuted)
                : OM.textMuted.withValues(alpha: 0.6),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              device.name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w500,
                color: device.online ? OM.text : OM.textMuted,
              ),
            ),
          ),
          if (!device.online)
            const Padding(
              padding: EdgeInsets.only(right: 4),
              child: Text(
                'offline',
                style: TextStyle(fontSize: 10, color: OM.danger),
              ),
            ),
          Tooltip(
            message: 'Close',
            child: IconButton(
              key: ValueKey('pane_close_${device.id}'),
              icon: const Icon(Icons.close, size: 12),
              onPressed: onClose,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
              visualDensity: VisualDensity.compact,
            ),
          ),
        ],
      ),
    );
  }
}

class _OfflineBody extends StatelessWidget {
  const _OfflineBody({required this.syncOn});

  final bool syncOn;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.phonelink_off_outlined,
              size: 22, color: OM.textMuted),
          const SizedBox(height: 8),
          const Text(
            'Device offline',
            style: TextStyle(fontSize: 12, color: OM.textMuted),
          ),
          if (syncOn) ...[
            const SizedBox(height: 4),
            const Text(
              'sync input skips this device',
              style: TextStyle(fontSize: 10, color: OM.textMuted),
            ),
          ],
        ],
      ),
    );
  }
}
