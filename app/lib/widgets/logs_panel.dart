import 'dart:async';
import 'dart:collection';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../api/engine_client.dart';
import '../theme.dart';

/// Collapsible live log panel scoped to ONE app by default, not the whole device.
///
/// A scope selector at the top chooses what to tail: the foreground app (Android),
/// a specific installed app, or the whole device. A "Flutter only" toggle narrows to
/// Flutter framework output. The panel tails the engine's log WebSocket with the
/// current scope, plus a substring filter and pause/clear controls.
class LogsPanel extends StatefulWidget {
  const LogsPanel({
    super.key,
    required this.deviceId,
    required this.platform,
    required this.client,
  });

  final String deviceId;
  final String platform; // "android" | "ios"
  final EngineClient client;

  @override
  State<LogsPanel> createState() => _LogsPanelState();
}

/// Sentinel scope keys; any other value is `pkg:<package>`.
const String _scopeForeground = 'foreground';
const String _scopeDevice = 'device';
const String _pkgPrefix = 'pkg:';

class _LogsPanelState extends State<LogsPanel> {
  static const int _maxLines = 500;

  final ListQueue<String> _lines = ListQueue<String>();
  final TextEditingController _filterController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;
  Timer? _reconnectTimer;
  bool _expanded = false;
  bool _paused = false;
  bool _connected = false;
  bool _flutterOnly = false;
  String _filter = '';

  List<AppInfo> _apps = const [];
  bool _appsLoaded = false;

  // Default to the foreground app on Android (logs "just work" when a dev opens
  // their app); iOS has no foreground query, so start at whole device.
  late String _scope =
      widget.platform == 'android' ? _scopeForeground : _scopeDevice;

  Uri _logsUri() {
    String? package;
    String? scope;
    if (_scope == _scopeForeground) {
      scope = 'foreground';
    } else if (_scope.startsWith(_pkgPrefix)) {
      package = _scope.substring(_pkgPrefix.length);
    }
    return widget.client.logsStreamUri(
      widget.deviceId,
      filter: _filter,
      package: package,
      scope: scope,
      flutter: _flutterOnly,
    );
  }

  Future<void> _loadApps() async {
    try {
      final apps = await widget.client.apps(widget.deviceId);
      if (!mounted) return;
      setState(() {
        _apps = apps;
        _appsLoaded = true;
      });
    } catch (_) {
      if (mounted) setState(() => _appsLoaded = true);
    }
  }

  void _connect() {
    _reconnectTimer?.cancel();
    try {
      final channel = WebSocketChannel.connect(_logsUri());
      _channel = channel;
      _sub = channel.stream.listen(
        (message) {
          if (!mounted || _paused || message is! String) return;
          setState(() {
            _connected = true;
            _lines.add(message);
            while (_lines.length > _maxLines) {
              _lines.removeFirst();
            }
          });
          _scrollToBottom();
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
    if (!mounted || !_expanded) return;
    if (_connected) setState(() => _connected = false);
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 2), () {
      if (mounted && _expanded) _connect();
    });
  }

  void _disconnect() {
    _reconnectTimer?.cancel();
    _sub?.cancel();
    _sub = null;
    _channel?.sink.close();
    _channel = null;
    _connected = false;
  }

  void _reconnect() {
    _disconnect();
    _connect();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
      }
    });
  }

  void _toggleExpanded() {
    setState(() => _expanded = !_expanded);
    if (_expanded) {
      if (!_appsLoaded) _loadApps();
      _connect();
    } else {
      _disconnect();
    }
  }

  void _applyFilter(String value) {
    _filter = value.trim();
    _lines.clear();
    if (_expanded) _reconnect();
    setState(() {});
  }

  void _onScopeChanged(String? scope) {
    if (scope == null || scope == _scope) return;
    setState(() {
      _scope = scope;
      _lines.clear();
    });
    if (_expanded) _reconnect();
  }

  void _toggleFlutter() {
    setState(() {
      _flutterOnly = !_flutterOnly;
      _lines.clear();
    });
    if (_expanded) _reconnect();
  }

  /// Human label for the scoped app (null == whole device).
  String? _scopeLabel() {
    if (_scope == _scopeForeground) return 'the foreground app';
    if (_scope.startsWith(_pkgPrefix)) {
      final package = _scope.substring(_pkgPrefix.length);
      for (final app in _apps) {
        if (app.package == package) return app.name;
      }
      return package;
    }
    return null;
  }

  @override
  void dispose() {
    _disconnect();
    _filterController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: OM.card,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: OM.border),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _header(),
          if (_expanded) const Divider(height: 1),
          if (_expanded) _logList(),
        ],
      ),
    );
  }

  Widget _header() {
    return InkWell(
      onTap: _toggleExpanded,
      borderRadius: BorderRadius.circular(10),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        child: Row(
          children: [
            Icon(
              _expanded ? Icons.expand_more : Icons.chevron_right,
              size: 18,
              color: OM.textMuted,
            ),
            const SizedBox(width: 6),
            const Text(
              'Logs',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
            if (_expanded) ...[
              const SizedBox(width: 10),
              _scopeSelector(),
              if (!_connected) ...[
                const SizedBox(width: 8),
                const Text(
                  'connecting…',
                  style: TextStyle(color: OM.textMuted, fontSize: 11),
                ),
              ],
            ],
            const Spacer(),
            if (_expanded) ...[
              _flutterToggle(),
              const SizedBox(width: 6),
              SizedBox(
                width: 150,
                height: 26,
                child: TextField(
                  controller: _filterController,
                  onSubmitted: _applyFilter,
                  style: const TextStyle(fontSize: 11),
                  decoration: InputDecoration(
                    hintText: 'filter…',
                    hintStyle:
                        const TextStyle(color: OM.textMuted, fontSize: 11),
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 5),
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
              const SizedBox(width: 6),
              Tooltip(
                message: _paused ? 'Resume' : 'Pause',
                child: InkWell(
                  onTap: () => setState(() => _paused = !_paused),
                  borderRadius: BorderRadius.circular(6),
                  child: Padding(
                    padding: const EdgeInsets.all(4),
                    child: Icon(
                      _paused ? Icons.play_arrow : Icons.pause,
                      size: 16,
                      color: _paused ? OM.accent : OM.textMuted,
                    ),
                  ),
                ),
              ),
              Tooltip(
                message: 'Clear',
                child: InkWell(
                  onTap: () => setState(_lines.clear),
                  borderRadius: BorderRadius.circular(6),
                  child: const Padding(
                    padding: EdgeInsets.all(4),
                    child: Icon(Icons.block, size: 15, color: OM.textMuted),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _scopeSelector() {
    final items = <DropdownMenuItem<String>>[
      if (widget.platform == 'android')
        const DropdownMenuItem(
          value: _scopeForeground,
          child: Text('Foreground app'),
        ),
      for (final app in _sortedApps())
        DropdownMenuItem(
          value: '$_pkgPrefix${app.package}',
          child: Text(app.name, overflow: TextOverflow.ellipsis),
        ),
      const DropdownMenuItem(value: _scopeDevice, child: Text('Whole device')),
    ];
    // A previously-selected package that isn't in the list yet (apps still
    // loading) still needs a matching item so the dropdown has a valid value.
    if (!items.any((item) => item.value == _scope)) {
      items.insert(
        0,
        DropdownMenuItem(value: _scope, child: Text(_scopeLabel() ?? _scope)),
      );
    }
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 190),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: _scope,
          items: items,
          onChanged: _onScopeChanged,
          isDense: true,
          isExpanded: true,
          dropdownColor: OM.card,
          borderRadius: BorderRadius.circular(8),
          focusColor: Colors.transparent,
          icon: const Icon(Icons.arrow_drop_down, size: 18, color: OM.textMuted),
          style: const TextStyle(fontSize: 11, color: OM.text),
        ),
      ),
    );
  }

  Widget _flutterToggle() {
    return Tooltip(
      message: _flutterOnly ? 'Showing Flutter output only' : 'Flutter only',
      child: InkWell(
        onTap: _toggleFlutter,
        borderRadius: BorderRadius.circular(6),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: _flutterOnly ? OM.accent.withValues(alpha: 0.15) : OM.bg,
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: _flutterOnly ? OM.accent : OM.border,
            ),
          ),
          child: Text(
            'Flutter',
            style: TextStyle(
              fontSize: 11,
              color: _flutterOnly ? OM.accent : OM.textMuted,
              fontWeight: _flutterOnly ? FontWeight.w600 : FontWeight.w400,
            ),
          ),
        ),
      ),
    );
  }

  List<AppInfo> _sortedApps() {
    final apps = [..._apps];
    apps.sort(
      (a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()),
    );
    return apps;
  }

  Widget _logList() {
    final label = _scopeLabel();
    final emptyText = label == null
        ? 'Waiting for log output…'
        : 'Waiting for $label to produce logs…';
    return SizedBox(
      height: 180,
      child: _lines.isEmpty
          ? Center(
              child: Text(
                emptyText,
                style: const TextStyle(color: OM.textMuted, fontSize: 11),
              ),
            )
          : ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              itemCount: _lines.length,
              itemBuilder: (context, index) => SelectableText(
                _lines.elementAt(index),
                style: const TextStyle(
                  fontFamily: 'Menlo',
                  fontFamilyFallback: ['monospace'],
                  fontSize: 10.5,
                  height: 1.45,
                  color: OM.text,
                ),
              ),
            ),
    );
  }
}
