import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import 'engine_client.dart';

/// In-memory fake engine used by "Try demo" so the app can be exercised
/// (and reviewed for the stores) without a real engine on the network.
///
/// Exposes one fake device whose "stream" loops over a few programmatically
/// rendered phone-screen-like frames. All actions succeed and do nothing.
class DemoEngineClient implements EngineClient {
  DemoEngineClient._(this._frames);

  static const Device demoDevice = Device(
    id: 'demo-phone',
    name: 'Demo Phone',
    platform: 'android',
    status: 'online',
    width: 1080,
    height: 2340,
  );

  final List<Uint8List> _frames;

  /// Renders the demo frames once and returns a ready client.
  static Future<DemoEngineClient> create() async {
    final frames = await _renderDemoFrames(1080, 2340);
    return DemoEngineClient._(frames);
  }

  @override
  String get baseUrl => 'demo';

  @override
  Future<String> health() async => 'demo';

  @override
  Future<List<Device>> devices() async => const [demoDevice];

  @override
  Future<void> tap(String deviceId, int x, int y) async {}

  @override
  Future<void> swipe(
    String deviceId, {
    required int x1,
    required int y1,
    required int x2,
    required int y2,
    required int durationMs,
  }) async {}

  @override
  Future<void> sendText(String deviceId, String text) async {}

  @override
  Future<void> pressKey(String deviceId, String key) async {}

  @override
  Stream<Uint8List> frames(String deviceId) async* {
    var i = 0;
    while (true) {
      yield _frames[i % _frames.length];
      i++;
      await Future<void>.delayed(const Duration(milliseconds: 1600));
    }
  }
}

// --- Frame rendering -------------------------------------------------------
//
// Each frame is drawn with Canvas/PictureRecorder at the demo device's pixel
// size and encoded to PNG bytes, so the normal Image.memory mirror path is
// exercised exactly as with a real engine stream.

Future<List<Uint8List>> _renderDemoFrames(int w, int h) async {
  return [
    await _renderFrame(w, h, _drawHomeScreen),
    await _renderFrame(w, h, _drawSettingsScreen),
    await _renderFrame(w, h, _drawMessagesScreen),
  ];
}

Future<Uint8List> _renderFrame(
  int w,
  int h,
  void Function(Canvas canvas, Size size) draw,
) async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  draw(canvas, Size(w.toDouble(), h.toDouble()));
  final picture = recorder.endRecording();
  final image = await picture.toImage(w, h);
  picture.dispose();
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  return data!.buffer.asUint8List();
}

void _text(
  Canvas canvas,
  String text,
  Offset topLeft, {
  double size = 40,
  Color color = Colors.white,
  FontWeight weight = FontWeight.w500,
  double? centerWidth,
}) {
  final painter = TextPainter(
    text: TextSpan(
      text: text,
      style: TextStyle(fontSize: size, color: color, fontWeight: weight),
    ),
    textDirection: TextDirection.ltr,
  )..layout();
  var offset = topLeft;
  if (centerWidth != null) {
    offset = Offset(topLeft.dx + (centerWidth - painter.width) / 2, topLeft.dy);
  }
  painter.paint(canvas, offset);
}

void _statusBar(Canvas canvas, Size size, {Color color = Colors.white}) {
  _text(canvas, '9:41', const Offset(60, 40),
      size: 42, color: color, weight: FontWeight.w600);
  // Battery pill.
  final battery = RRect.fromRectAndRadius(
    Rect.fromLTWH(size.width - 150, 52, 84, 40),
    const Radius.circular(10),
  );
  canvas.drawRRect(
      battery,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 4
        ..color = color.withValues(alpha: 0.8));
  canvas.drawRRect(
    RRect.fromRectAndRadius(
      Rect.fromLTWH(size.width - 144, 58, 60, 28),
      const Radius.circular(6),
    ),
    Paint()..color = color,
  );
  // Signal bars.
  for (var i = 0; i < 4; i++) {
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(size.width - 280 + i * 24, 88.0 - (12 + i * 8),
            14, (12 + i * 8).toDouble()),
        const Radius.circular(3),
      ),
      Paint()..color = color.withValues(alpha: i < 3 ? 1 : 0.35),
    );
  }
}

/// Frame 1: wallpaper + clock widget + app icon grid + dock.
void _drawHomeScreen(Canvas canvas, Size size) {
  canvas.drawRect(
    Offset.zero & size,
    Paint()
      ..shader = ui.Gradient.linear(
        Offset.zero,
        Offset(size.width * 0.4, size.height),
        [const Color(0xFF14243A), const Color(0xFF0E1A2A), const Color(0xFF1C1430)],
        [0.0, 0.55, 1.0],
      ),
  );
  // Soft wallpaper blobs.
  canvas.drawCircle(Offset(size.width * 0.85, size.height * 0.22), 340,
      Paint()..color = const Color(0xFF3DDC97).withValues(alpha: 0.08));
  canvas.drawCircle(Offset(size.width * 0.12, size.height * 0.72), 420,
      Paint()..color = const Color(0xFF4A6CF7).withValues(alpha: 0.10));

  _statusBar(canvas, size);

  // Clock widget.
  _text(canvas, '9:41', const Offset(0, 200),
      size: 190, weight: FontWeight.w300, centerWidth: 1080);
  _text(canvas, 'Mon, July 20', const Offset(0, 420),
      size: 52, color: Colors.white70, centerWidth: 1080);

  // App icon grid: 4 x 5 rounded squares.
  const iconColors = [
    Color(0xFFE0645B), Color(0xFF5B9BE0), Color(0xFF3DDC97), Color(0xFFE0B85B),
    Color(0xFF9B6CE0), Color(0xFF5BC8E0), Color(0xFFE05B9B), Color(0xFF8BC34A),
    Color(0xFF607D8B), Color(0xFFE0885B), Color(0xFF6C7AE0), Color(0xFF4DB6AC),
    Color(0xFFB0885B), Color(0xFF7986CB), Color(0xFFD4E157), Color(0xFFEF9A9A),
    Color(0xFF90A4AE), Color(0xFF66BB6A), Color(0xFFBA68C8), Color(0xFF4FC3F7),
  ];
  const cols = 4;
  const iconSize = 170.0;
  const gapX = (1080 - cols * iconSize) / (cols + 1);
  for (var i = 0; i < iconColors.length; i++) {
    final col = i % cols;
    final row = i ~/ cols;
    final x = gapX + col * (iconSize + gapX);
    final y = 620 + row * 280.0;
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(x, y, iconSize, iconSize),
        const Radius.circular(46),
      ),
      Paint()..color = iconColors[i].withValues(alpha: 0.92),
    );
    // Label placeholder bar under each icon.
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(x + 25, y + iconSize + 26, iconSize - 50, 18),
        const Radius.circular(9),
      ),
      Paint()..color = Colors.white.withValues(alpha: 0.35),
    );
  }

  // Dock.
  canvas.drawRRect(
    RRect.fromRectAndRadius(
      Rect.fromLTWH(40, size.height - 290, size.width - 80, 230),
      const Radius.circular(60),
    ),
    Paint()..color = Colors.white.withValues(alpha: 0.10),
  );
  const dockColors = [
    Color(0xFF3DDC97), Color(0xFF5B9BE0), Color(0xFFE0B85B), Color(0xFFE0645B),
  ];
  for (var i = 0; i < dockColors.length; i++) {
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(120 + i * 230.0, size.height - 260, iconSize, iconSize),
        const Radius.circular(46),
      ),
      Paint()..color = dockColors[i],
    );
  }
}

/// Frame 2: settings-like list.
void _drawSettingsScreen(Canvas canvas, Size size) {
  canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF14161B));
  _statusBar(canvas, size);

  _text(canvas, 'Settings', const Offset(70, 170),
      size: 96, weight: FontWeight.w600);

  // Search pill.
  canvas.drawRRect(
    RRect.fromRectAndRadius(
      Rect.fromLTWH(70, 330, size.width - 140, 110),
      const Radius.circular(55),
    ),
    Paint()..color = const Color(0xFF23262E),
  );
  _text(canvas, 'Search settings', const Offset(140, 358),
      size: 44, color: const Color(0xFF8A919E));

  const rows = [
    ('Wi-Fi', 'DemoNet-5G', Color(0xFF5B9BE0)),
    ('Bluetooth', 'On', Color(0xFF6C7AE0)),
    ('Display', 'Dark theme', Color(0xFFE0B85B)),
    ('Sound & vibration', 'Ring volume 80%', Color(0xFFE0645B)),
    ('Battery', '92% — charging', Color(0xFF3DDC97)),
    ('Storage', '64 GB used of 128 GB', Color(0xFF9B6CE0)),
    ('Apps', '117 apps installed', Color(0xFF5BC8E0)),
    ('About phone', 'Demo Phone', Color(0xFF90A4AE)),
  ];
  for (var i = 0; i < rows.length; i++) {
    final (title, subtitle, color) = rows[i];
    final y = 540 + i * 210.0;
    // Icon circle.
    canvas.drawCircle(Offset(140, y + 70), 56, Paint()..color = color);
    _text(canvas, title, Offset(250, y + 10), size: 48, weight: FontWeight.w500);
    _text(canvas, subtitle, Offset(250, y + 80),
        size: 38, color: const Color(0xFF8A919E));
    // Chevron.
    final chevron = Path()
      ..moveTo(size.width - 130, y + 40)
      ..lineTo(size.width - 95, y + 70)
      ..lineTo(size.width - 130, y + 100);
    canvas.drawPath(
      chevron,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 8
        ..strokeCap = StrokeCap.round
        ..color = const Color(0xFF8A919E),
    );
    // Divider.
    if (i < rows.length - 1) {
      canvas.drawRect(
        Rect.fromLTWH(250, y + 175, size.width - 320, 2),
        Paint()..color = const Color(0xFF23262E),
      );
    }
  }
}

/// Frame 3: chat conversation.
void _drawMessagesScreen(Canvas canvas, Size size) {
  canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF101216));
  _statusBar(canvas, size);

  // App bar.
  canvas.drawRect(
    Rect.fromLTWH(0, 120, size.width, 170),
    Paint()..color = const Color(0xFF171A20),
  );
  canvas.drawCircle(
      const Offset(190, 205), 58, Paint()..color = const Color(0xFF3DDC97));
  _text(canvas, 'OM', const Offset(150, 178),
      size: 44, color: const Color(0xFF0D1512), weight: FontWeight.w700,
      centerWidth: 80);
  _text(canvas, 'OpenMob Engine', const Offset(290, 150),
      size: 50, weight: FontWeight.w600);
  _text(canvas, 'online', const Offset(290, 218),
      size: 36, color: const Color(0xFF3DDC97));

  void bubble(String text, double y, {required bool mine}) {
    final painter = TextPainter(
      text: TextSpan(
        text: text,
        style: const TextStyle(fontSize: 42, color: Colors.white, height: 1.3),
      ),
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: 640);
    final w = painter.width + 90;
    final h = painter.height + 70;
    final x = mine ? size.width - 70 - w : 70.0;
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(x, y, w, h),
        const Radius.circular(42),
      ),
      Paint()
        ..color = mine ? const Color(0xFF1E5C43) : const Color(0xFF23262E),
    );
    painter.paint(canvas, Offset(x + 45, y + 34));
  }

  bubble('Hi! This is OpenMob demo mode.', 400, mine: false);
  bubble('These frames are generated on-device — no engine needed.', 570,
      mine: false);
  bubble('So I can review the app without a Mac nearby?', 830, mine: true);
  bubble('Exactly. Connect a real engine any time from settings.', 1000,
      mine: false);
  bubble('Nice.', 1260, mine: true);

  // Input bar.
  canvas.drawRRect(
    RRect.fromRectAndRadius(
      Rect.fromLTWH(60, size.height - 200, size.width - 280, 130),
      const Radius.circular(65),
    ),
    Paint()..color = const Color(0xFF23262E),
  );
  _text(canvas, 'Message', Offset(140, size.height - 165),
      size: 44, color: const Color(0xFF8A919E));
  canvas.drawCircle(Offset(size.width - 125, size.height - 135), 65,
      Paint()..color = const Color(0xFF3DDC97));
}
