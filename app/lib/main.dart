import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'screens/device_list_screen.dart';
import 'state/app_state.dart';
import 'theme.dart';
import 'widgets/device_pane.dart';
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

/// Responsive entry point: wide windows (desktop) keep the sidebar + pane
/// layout; narrow ones (phones) get a device list that navigates to a
/// full-screen control view. Both layouts reuse the same widgets.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  static const double desktopBreakpoint = 700;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= desktopBreakpoint) {
          return const _DesktopHome();
        }
        return const DeviceListScreen();
      },
    );
  }
}

class _DesktopHome extends StatelessWidget {
  const _DesktopHome();

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
                  ErrorBanner(message: state.lastError!),
                const Expanded(child: DevicePane()),
                if (state.selectedDevice != null) const DeviceToolbar(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
