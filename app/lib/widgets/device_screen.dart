import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../theme.dart';

/// Live device screen: renders binary JPEG frames from the engine's
/// WebSocket stream and maps taps/drags back to device pixel coordinates.
class DeviceScreen extends StatefulWidget {
  const DeviceScreen({
    super.key,
    required this.streamUri,
    required this.deviceWidth,
    required this.deviceHeight,
    required this.onTapAt,
    required this.onSwipe,
  });

  final Uri streamUri;
  final int deviceWidth;
  final int deviceHeight;
  final void Function(int x, int y) onTapAt;
  final void Function(int x1, int y1, int x2, int y2, int durationMs)
      onSwipe;

  @override
  State<DeviceScreen> createState() => _DeviceScreenState();
}

class _DeviceScreenState extends State<DeviceScreen> {
  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;
  Timer? _reconnectTimer;
  Uint8List? _frame;
  bool _connected = false;

  // Drag tracking (in widget-local coordinates).
  Offset? _dragStart;
  Offset? _dragLast;
  DateTime? _dragStartTime;

  @override
  void initState() {
    super.initState();
    _connect();
  }

  @override
  void didUpdateWidget(DeviceScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.streamUri != widget.streamUri) {
      _disconnect();
      _connect();
    }
  }

  void _connect() {
    _reconnectTimer?.cancel();
    try {
      final channel = WebSocketChannel.connect(widget.streamUri);
      _channel = channel;
      _sub = channel.stream.listen(
        (message) {
          if (!mounted) return;
          if (message is List<int>) {
            setState(() {
              _frame = message is Uint8List
                  ? message
                  : Uint8List.fromList(message);
              _connected = true;
            });
          }
        },
        onError: (Object _) => _scheduleReconnect(),
        onDone: _scheduleReconnect,
        cancelOnError: true,
      );
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (!mounted) return;
    if (_connected) setState(() => _connected = false);
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 2), () {
      if (mounted) _connect();
    });
  }

  void _disconnect() {
    _reconnectTimer?.cancel();
    _sub?.cancel();
    _sub = null;
    _channel?.sink.close();
    _channel = null;
    _frame = null;
    _connected = false;
  }

  @override
  void dispose() {
    _disconnect();
    super.dispose();
  }

  /// Maps a widget-local position to device pixel coordinates, taking the
  /// BoxFit.contain letterboxing into account. Returns null when the point
  /// falls outside the rendered screen area.
  Offset? _toDevice(Offset local, Size box) {
    final dw = widget.deviceWidth;
    final dh = widget.deviceHeight;
    if (dw <= 0 || dh <= 0 || box.isEmpty) return null;
    final scale = _scaleFor(box);
    final offsetX = (box.width - dw * scale) / 2;
    final offsetY = (box.height - dh * scale) / 2;
    final x = (local.dx - offsetX) / scale;
    final y = (local.dy - offsetY) / scale;
    if (x < 0 || y < 0 || x >= dw || y >= dh) return null;
    return Offset(x, y);
  }

  double _scaleFor(Size box) {
    final dw = widget.deviceWidth;
    final dh = widget.deviceHeight;
    final sx = box.width / dw;
    final sy = box.height / dh;
    return sx < sy ? sx : sy;
  }

  void _handleTapUp(TapUpDetails details, Size box) {
    final p = _toDevice(details.localPosition, box);
    if (p == null) return;
    widget.onTapAt(p.dx.round(), p.dy.round());
  }

  void _handlePanStart(DragStartDetails details) {
    _dragStart = details.localPosition;
    _dragLast = details.localPosition;
    _dragStartTime = DateTime.now();
  }

  void _handlePanUpdate(DragUpdateDetails details) {
    _dragLast = details.localPosition;
  }

  void _handlePanEnd(DragEndDetails details, Size box) {
    final start = _dragStart;
    final end = _dragLast;
    final startTime = _dragStartTime;
    _dragStart = null;
    _dragLast = null;
    _dragStartTime = null;
    if (start == null || end == null || startTime == null) return;

    final p1 = _toDevice(start, box);
    final p2 = _toDevice(end, box);
    if (p1 == null || p2 == null) return;

    final elapsed = DateTime.now().difference(startTime).inMilliseconds;
    final duration = elapsed.clamp(100, 1000);
    widget.onSwipe(
      p1.dx.round(),
      p1.dy.round(),
      p2.dx.round(),
      p2.dy.round(),
      duration,
    );
  }

  @override
  Widget build(BuildContext context) {
    final frame = _frame;
    if (frame == null) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: OM.accent,
              ),
            ),
            SizedBox(height: 14),
            Text(
              'Connecting to screen stream…',
              style: TextStyle(color: OM.textMuted, fontSize: 12),
            ),
          ],
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final box = Size(constraints.maxWidth, constraints.maxHeight);
        return MouseRegion(
          cursor: SystemMouseCursors.click,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapUp: (d) => _handleTapUp(d, box),
            onPanStart: _handlePanStart,
            onPanUpdate: _handlePanUpdate,
            onPanEnd: (d) => _handlePanEnd(d, box),
            child: Stack(
              fit: StackFit.expand,
              children: [
                Image.memory(
                  frame,
                  gaplessPlayback: true,
                  fit: BoxFit.contain,
                  filterQuality: FilterQuality.medium,
                ),
                if (!_connected)
                  const Positioned(
                    top: 10,
                    right: 12,
                    child: Text(
                      'stream lost — reconnecting…',
                      style:
                          TextStyle(color: OM.danger, fontSize: 11),
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}
