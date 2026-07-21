import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/engine_client.dart';
import '../theme.dart';

/// Small panel to launch a Flutter project on a device through the engine and
/// drive a real (managed) hot reload / hot restart, plus open DevTools.
///
/// Hot reload only works from a `flutter run` session that owns the kernel
/// compiler, so OpenMob launches the app itself and speaks the `--machine`
/// daemon protocol to it. This panel is the front door to that.
class FlutterRunPanel extends StatefulWidget {
  const FlutterRunPanel({
    super.key,
    required this.client,
    required this.deviceId,
  });

  final EngineClient client;
  final String deviceId;

  @override
  State<FlutterRunPanel> createState() => _FlutterRunPanelState();
}

class _FlutterRunPanelState extends State<FlutterRunPanel> {
  final TextEditingController _pathController = TextEditingController();

  Map<String, dynamic>? _session;
  bool _busy = false;
  String? _error;
  String? _status; // transient success line (e.g. "Reloaded 1 of 733 libraries")

  bool get _running => _session?['running'] == true;

  @override
  void initState() {
    super.initState();
    _loadSession();
  }

  @override
  void didUpdateWidget(FlutterRunPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.deviceId != widget.deviceId) {
      _session = null;
      _status = null;
      _error = null;
      _loadSession();
    }
  }

  @override
  void dispose() {
    _pathController.dispose();
    super.dispose();
  }

  Future<void> _loadSession() async {
    try {
      final session = await widget.client.flutterSession(widget.deviceId);
      if (!mounted) return;
      setState(() => _session = session['running'] == true ? session : null);
    } catch (_) {
      // Engine may be momentarily unreachable; leave state as-is.
    }
  }

  Future<void> _run(Future<Map<String, dynamic>> Function() action,
      {String? successFrom}) async {
    setState(() {
      _busy = true;
      _error = null;
      _status = null;
    });
    try {
      final result = await action();
      if (!mounted) return;
      setState(() {
        if (successFrom != null) _status = result[successFrom]?.toString();
      });
      await _loadSession();
    } catch (e) {
      if (!mounted) return;
      setState(() =>
          _error = e is EngineException ? e.message : 'Engine unreachable');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _start() {
    final path = _pathController.text.trim();
    if (path.isEmpty) {
      setState(() => _error = 'Enter the Flutter project path first.');
      return;
    }
    _run(() => widget.client.flutterRun(widget.deviceId, path));
  }

  Future<void> _openDevtools() async {
    setState(() {
      _busy = true;
      _error = null;
      _status = null;
    });
    try {
      final result = await widget.client.flutterDevtools(widget.deviceId);
      final url = result['devtools_url'] as String? ??
          result['vm_service_uri'] as String?;
      if (!mounted) return;
      if (url != null) {
        await Clipboard.setData(ClipboardData(text: url));
        setState(() => _status = 'DevTools URL copied: $url');
      } else {
        setState(() => _error = 'No DevTools URL available.');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() =>
          _error = e is EngineException ? e.message : 'Engine unreachable');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: OM.card,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: OM.border),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _header(),
          const SizedBox(height: 8),
          _running ? _runningControls() : _launchControls(),
          if (_status != null) ...[
            const SizedBox(height: 6),
            Text(
              _status!,
              style: const TextStyle(color: OM.accent, fontSize: 11),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          if (_error != null) ...[
            const SizedBox(height: 6),
            Text(
              _error!,
              style: const TextStyle(color: OM.danger, fontSize: 11),
              maxLines: 3,
            ),
          ],
        ],
      ),
    );
  }

  Widget _header() {
    return Row(
      children: [
        const Icon(Icons.flutter_dash, size: 16, color: OM.accent),
        const SizedBox(width: 6),
        const Text(
          'Flutter',
          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        ),
        const SizedBox(width: 8),
        if (_busy)
          const SizedBox(
            width: 12,
            height: 12,
            child: CircularProgressIndicator(strokeWidth: 2),
          )
        else
          Text(
            _running ? 'running' : 'not running',
            style: TextStyle(
              fontSize: 11,
              color: _running ? OM.accent : OM.textMuted,
            ),
          ),
      ],
    );
  }

  Widget _launchControls() {
    return Row(
      children: [
        Expanded(
          child: SizedBox(
            height: 30,
            child: TextField(
              controller: _pathController,
              enabled: !_busy,
              onSubmitted: (_) => _start(),
              style: const TextStyle(fontSize: 11),
              decoration: InputDecoration(
                hintText: '/path/to/flutter/project',
                hintStyle: const TextStyle(color: OM.textMuted, fontSize: 11),
                isDense: true,
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                filled: true,
                fillColor: OM.bg,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: OM.border),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                  borderSide: const BorderSide(color: OM.border),
                ),
              ),
            ),
          ),
        ),
        const SizedBox(width: 8),
        FilledButton.icon(
          onPressed: _busy ? null : _start,
          icon: const Icon(Icons.play_arrow, size: 16),
          label: const Text('Run', style: TextStyle(fontSize: 12)),
        ),
      ],
    );
  }

  Widget _runningControls() {
    final appId = _session?['app_id'] as String?;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: [
            _actionButton(
              icon: Icons.bolt,
              label: 'Hot Reload',
              onPressed: () => _run(
                () => widget.client.flutterHotReload(widget.deviceId),
                successFrom: 'message',
              ),
            ),
            _actionButton(
              icon: Icons.restart_alt,
              label: 'Hot Restart',
              onPressed: () => _run(
                () => widget.client.flutterHotRestart(widget.deviceId),
              ),
            ),
            _actionButton(
              icon: Icons.dashboard_customize_outlined,
              label: 'Open DevTools',
              onPressed: _openDevtools,
            ),
            _actionButton(
              icon: Icons.stop_circle_outlined,
              label: 'Stop',
              danger: true,
              onPressed: () => _run(
                () async {
                  await widget.client.flutterStop(widget.deviceId);
                  return const {};
                },
              ),
            ),
          ],
        ),
        if (appId != null) ...[
          const SizedBox(height: 6),
          Text(
            'app: $appId',
            style: const TextStyle(
              fontFamily: 'Menlo',
              fontFamilyFallback: ['monospace'],
              fontSize: 10,
              color: OM.textMuted,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ],
    );
  }

  Widget _actionButton({
    required IconData icon,
    required String label,
    required VoidCallback onPressed,
    bool danger = false,
  }) {
    final color = danger ? OM.danger : OM.text;
    return OutlinedButton.icon(
      onPressed: _busy ? null : onPressed,
      icon: Icon(icon, size: 15, color: color),
      label: Text(label, style: TextStyle(fontSize: 11, color: color)),
      style: OutlinedButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        side: const BorderSide(color: OM.border),
        visualDensity: VisualDensity.compact,
      ),
    );
  }
}
