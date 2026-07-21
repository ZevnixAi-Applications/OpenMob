import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../theme.dart';

/// Bottom toolbar: hardware keys + text input for the selected device.
class DeviceToolbar extends StatefulWidget {
  const DeviceToolbar({super.key});

  @override
  State<DeviceToolbar> createState() => _DeviceToolbarState();
}

class _DeviceToolbarState extends State<DeviceToolbar> {
  final TextEditingController _textController = TextEditingController();

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  void _sendText(AppState state) {
    final text = _textController.text;
    if (text.isEmpty) return;
    state.sendText(text);
    _textController.clear();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final device = state.activeDevice;
    final enabled = device?.online ?? false;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: const BoxDecoration(
        color: OM.sidebar,
        border: Border(top: BorderSide(color: OM.border)),
      ),
      child: Row(
        children: [
          // In split view the toolbar targets the focused (outlined) pane;
          // make that target explicit.
          if (state.layout == PaneLayout.split && device != null)
            Container(
              margin: const EdgeInsets.only(right: 10),
              constraints: const BoxConstraints(maxWidth: 140),
              child: Text(
                '→ ${device.name}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 11, color: OM.textMuted),
              ),
            ),
          _KeyButton(
            icon: Icons.arrow_back,
            label: 'Back',
            enabled: enabled,
            onPressed: () => state.pressKey('back'),
          ),
          _KeyButton(
            icon: Icons.radio_button_unchecked,
            label: 'Home',
            enabled: enabled,
            onPressed: () => state.pressKey('home'),
          ),
          _KeyButton(
            icon: Icons.power_settings_new,
            label: 'Power',
            enabled: enabled,
            onPressed: () => state.pressKey('power'),
          ),
          _KeyButton(
            icon: Icons.volume_down,
            label: 'Volume down',
            enabled: enabled,
            onPressed: () => state.pressKey('volume_down'),
          ),
          _KeyButton(
            icon: Icons.volume_up,
            label: 'Volume up',
            enabled: enabled,
            onPressed: () => state.pressKey('volume_up'),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: SizedBox(
              height: 32,
              child: TextField(
                controller: _textController,
                enabled: enabled,
                style: const TextStyle(fontSize: 13),
                decoration: InputDecoration(
                  hintText: 'Type text to send to device…',
                  hintStyle: const TextStyle(
                      color: OM.textMuted, fontSize: 13),
                  isDense: true,
                  contentPadding: const EdgeInsets.symmetric(
                      horizontal: 12, vertical: 8),
                  filled: true,
                  fillColor: OM.bg,
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(7),
                    borderSide: const BorderSide(color: OM.border),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(7),
                    borderSide: const BorderSide(color: OM.accent),
                  ),
                  disabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(7),
                    borderSide: const BorderSide(color: OM.border),
                  ),
                ),
                onSubmitted: (_) => _sendText(state),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Tooltip(
            message: 'Send text',
            child: IconButton(
              icon: const Icon(Icons.send, size: 16),
              color: OM.accent,
              onPressed: enabled ? () => _sendText(state) : null,
              visualDensity: VisualDensity.compact,
            ),
          ),
        ],
      ),
    );
  }
}

class _KeyButton extends StatelessWidget {
  const _KeyButton({
    required this.icon,
    required this.label,
    required this.enabled,
    required this.onPressed,
  });

  final IconData icon;
  final String label;
  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 6),
      child: Tooltip(
        message: label,
        child: Material(
          color: OM.card,
          borderRadius: BorderRadius.circular(7),
          child: InkWell(
            onTap: enabled ? onPressed : null,
            borderRadius: BorderRadius.circular(7),
            hoverColor: OM.cardHover,
            child: Container(
              width: 34,
              height: 32,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(7),
                border: Border.all(color: OM.border),
              ),
              child: Icon(
                icon,
                size: 16,
                color: enabled ? OM.text : OM.textMuted,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
