import 'dart:async';
import 'dart:collection';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../theme.dart';

/// Collapsible live log panel: tails the engine's log WebSocket for a device,
/// with a substring filter and a pause toggle.
class LogsPanel extends StatefulWidget {
  const LogsPanel({super.key, required this.logsUriBuilder});

  /// Builds the WS URI for the current device with an optional filter.
  final Uri Function({String? filter}) logsUriBuilder;

  @override
  State<LogsPanel> createState() => _LogsPanelState();
}

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
  String _filter = '';

  @override
  void didUpdateWidget(LogsPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.logsUriBuilder != widget.logsUriBuilder) {
      _lines.clear();
      if (_expanded) _reconnect();
    }
  }

  void _connect() {
    _reconnectTimer?.cancel();
    try {
      final channel = WebSocketChannel.connect(
        widget.logsUriBuilder(filter: _filter),
      );
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
            if (_expanded && !_connected) ...[
              const SizedBox(width: 8),
              const Text(
                'connecting…',
                style: TextStyle(color: OM.textMuted, fontSize: 11),
              ),
            ],
            const Spacer(),
            if (_expanded) ...[
              SizedBox(
                width: 200,
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

  Widget _logList() {
    return SizedBox(
      height: 180,
      child: _lines.isEmpty
          ? const Center(
              child: Text(
                'Waiting for log output…',
                style: TextStyle(color: OM.textMuted, fontSize: 11),
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
