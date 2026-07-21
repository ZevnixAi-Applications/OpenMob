// OpenMob deterministic automation testbed.
//
// Designed for pixel-sample verification (no OCR):
// - Page 1: full-screen background toggles pure red <-> pure green on tap.
//   A TextField sits in the bottom 10% of the screen. While it holds N > 0
//   characters, the top 15% of the screen is a pure blue strip when N is
//   even, pure yellow when odd. N == 0 draws no strip.
// - Page 2: solid pure magenta; tapping anywhere snaps back to page 1.
// No animated color transitions: page returns use jumpToPage (zero duration)
// and color changes are instant setState swaps.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

const Color pureRed = Color(0xFFFF0000);
const Color pureGreen = Color(0xFF00FF00);
const Color pureBlue = Color(0xFF0000FF);
const Color pureYellow = Color(0xFFFFFF00);
const Color pureMagenta = Color(0xFFFF00FF);

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Draw edge to edge so samples at the very top/bottom hit our colors.
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      systemNavigationBarColor: Colors.transparent,
    ),
  );
  runApp(const TestbedApp());
}

class TestbedApp extends StatelessWidget {
  const TestbedApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      debugShowCheckedModeBanner: false,
      home: TestbedHome(),
    );
  }
}

class TestbedHome extends StatefulWidget {
  const TestbedHome({super.key});

  @override
  State<TestbedHome> createState() => _TestbedHomeState();
}

class _TestbedHomeState extends State<TestbedHome> {
  final PageController _pageController = PageController();
  final TextEditingController _textController = TextEditingController();
  bool _isRed = true;
  int _charCount = 0;

  @override
  void initState() {
    super.initState();
    _textController.addListener(() {
      final int n = _textController.text.length;
      if (n != _charCount) {
        setState(() => _charCount = n);
      }
    });
  }

  @override
  void dispose() {
    _pageController.dispose();
    _textController.dispose();
    super.dispose();
  }

  void _toggleBackground() {
    // Also collapse the keyboard so later samples/gestures are unobstructed.
    FocusManager.instance.primaryFocus?.unfocus();
    setState(() => _isRed = !_isRed);
  }

  Color? get _stripColor {
    if (_charCount == 0) return null;
    return _charCount.isEven ? pureBlue : pureYellow;
  }

  Widget _buildPageOne(BuildContext context) {
    final Size screen = MediaQuery.sizeOf(context);
    final Color? strip = _stripColor;
    // NOTE: every Stack child has a stable key. Without keys, the strip
    // appearing/disappearing shifts child indices and Flutter re-creates the
    // TextField element, silently dropping its focus + IME connection.
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        GestureDetector(
          key: const ValueKey<String>('background'),
          behavior: HitTestBehavior.opaque,
          onTap: _toggleBackground,
          child: ColoredBox(color: _isRed ? pureRed : pureGreen),
        ),
        if (strip != null)
          Positioned(
            key: const ValueKey<String>('strip'),
            top: 0,
            left: 0,
            right: 0,
            height: screen.height * 0.15,
            child: IgnorePointer(child: ColoredBox(color: strip)),
          ),
        Positioned(
          key: const ValueKey<String>('field-band'),
          bottom: 0,
          left: 0,
          right: 0,
          height: screen.height * 0.10,
          child: Material(
            color: Colors.white,
            child: Center(
              child: TextField(
                key: const Key('testbed-field'),
                controller: _textController,
                autocorrect: false,
                enableSuggestions: false,
                style: const TextStyle(color: Colors.black, fontSize: 16),
                decoration: const InputDecoration(
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.symmetric(horizontal: 12),
                  hintText: 'input',
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPageTwo() {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => _pageController.jumpToPage(0),
      child: const ColoredBox(color: pureMagenta),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // Keep the layout fixed when the soft keyboard appears so sampled
      // regions never move.
      resizeToAvoidBottomInset: false,
      body: PageView(
        controller: _pageController,
        children: <Widget>[
          _buildPageOne(context),
          _buildPageTwo(),
        ],
      ),
    );
  }
}
