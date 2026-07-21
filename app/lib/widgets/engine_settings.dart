import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';

/// Engine URL settings dialog, shared by desktop (sidebar gear) and mobile
/// (app bar gear / offline empty state). Validates the URL before saving.
Future<void> showEngineSettings(BuildContext context) async {
  final state = context.read<AppState>();
  final result = await showDialog<String>(
    context: context,
    builder: (context) => _EngineSettingsDialog(initialUrl: state.baseUrl),
  );
  if (result != null) {
    await state.setBaseUrl(result);
  }
}

class _EngineSettingsDialog extends StatefulWidget {
  const _EngineSettingsDialog({required this.initialUrl});

  final String initialUrl;

  @override
  State<_EngineSettingsDialog> createState() => _EngineSettingsDialogState();
}

class _EngineSettingsDialogState extends State<_EngineSettingsDialog> {
  late final TextEditingController _controller;
  String? _error;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialUrl);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _save() {
    final error = AppState.validateEngineUrl(_controller.text);
    if (error != null) {
      setState(() => _error = error);
      return;
    }
    Navigator.of(context).pop(_controller.text);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Engine settings', style: TextStyle(fontSize: 16)),
      content: ConstrainedBox(
        constraints: const BoxConstraints(minWidth: 280, maxWidth: 360),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _controller,
              autofocus: true,
              keyboardType: TextInputType.url,
              autocorrect: false,
              style: const TextStyle(fontSize: 13),
              decoration: InputDecoration(
                labelText: 'Engine base URL',
                hintText: AppState.defaultBaseUrl,
                border: const OutlineInputBorder(),
                errorText: _error,
                errorMaxLines: 3,
              ),
              onChanged: (_) {
                if (_error != null) setState(() => _error = null);
              },
              onSubmitted: (_) => _save(),
            ),
            const SizedBox(height: 10),
            Text(
              'Run `openmob serve` on your computer, then enter its address '
              'as seen from this device (e.g. http://192.168.1.50:8930).',
              style: TextStyle(
                fontSize: 11,
                color: Theme.of(context).colorScheme.onSurface
                    .withValues(alpha: 0.6),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _save,
          child: const Text('Save'),
        ),
      ],
    );
  }
}
