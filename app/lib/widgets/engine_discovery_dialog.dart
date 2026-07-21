import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/engine_discovery.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Shows the mDNS discovery dialog and applies the picked engine URL.
Future<void> showEngineDiscoveryDialog(BuildContext context) async {
  final state = context.read<AppState>();
  final url = await showDialog<String>(
    context: context,
    builder: (context) => const EngineDiscoveryDialog(),
  );
  if (url != null && url.isNotEmpty) {
    await state.setBaseUrl(url);
  }
}

/// Browses for `_openmob._tcp` engines and pops with the tapped engine's URL.
class EngineDiscoveryDialog extends StatefulWidget {
  const EngineDiscoveryDialog({super.key});

  @override
  State<EngineDiscoveryDialog> createState() => _EngineDiscoveryDialogState();
}

class _EngineDiscoveryDialogState extends State<EngineDiscoveryDialog> {
  /// Null while a search is in flight.
  List<DiscoveredEngine>? _engines;

  @override
  void initState() {
    super.initState();
    _search();
  }

  Future<void> _search() async {
    setState(() => _engines = null);
    final found = await EngineDiscovery.discover();
    if (!mounted) return;
    setState(() => _engines = found);
  }

  @override
  Widget build(BuildContext context) {
    final engines = _engines;
    return AlertDialog(
      title: const Text('Find engines on my network',
          style: TextStyle(fontSize: 16)),
      content: SizedBox(width: 380, child: _body(engines)),
      actions: [
        if (engines != null)
          TextButton(onPressed: _search, child: const Text('Search again')),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _body(List<DiscoveredEngine>? engines) {
    if (engines == null) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 12),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            SizedBox(width: 12),
            Text('Searching your network…', style: TextStyle(fontSize: 13)),
          ],
        ),
      );
    }
    if (engines.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: Text(
          'No engines found on your network.\n\n'
          'Make sure `openmob serve` is running on the host machine, then '
          'search again — or enter the engine URL manually in Engine settings.',
          style: TextStyle(color: OM.textMuted, fontSize: 13),
        ),
      );
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final engine in engines)
          ListTile(
            dense: true,
            contentPadding: const EdgeInsets.symmetric(horizontal: 8),
            leading: const Icon(Icons.dns_outlined, size: 20),
            title: Text(engine.name, style: const TextStyle(fontSize: 13)),
            subtitle: Text(
              engine.hostPort,
              style: const TextStyle(color: OM.textMuted, fontSize: 12),
            ),
            onTap: () => Navigator.of(context).pop(engine.url),
          ),
      ],
    );
  }
}
