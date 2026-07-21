import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/engine_client.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Dialog for creating a new Android AVD or iOS Simulator.
///
/// Fetches create-options from the engine, lets the user pick a hardware profile
/// and a system image / runtime, then starts a create job. Android jobs may
/// download a system image, so the job is polled and its progress shown; iOS is
/// fast. On success the new device shows up in the sidebar via the normal poll.
class CreateDeviceDialog extends StatefulWidget {
  const CreateDeviceDialog({super.key});

  @override
  State<CreateDeviceDialog> createState() => _CreateDeviceDialogState();
}

class _CreateDeviceDialogState extends State<CreateDeviceDialog> {
  final _nameController = TextEditingController();

  String _platform = 'android';
  CreateOptions? _options;
  bool _loading = true;
  String? _loadError;

  // Android selections.
  String? _profileId;
  String? _imageId;

  // iOS selections.
  String? _deviceTypeId;
  String? _runtimeId;

  // Job state.
  CreateJob? _job;
  bool _creating = false;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final options = await context.read<AppState>().client.createOptions();
      if (!mounted) return;
      setState(() {
        _options = options;
        _loading = false;
        _applyDefaults();
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadError = e is EngineException ? e.message : 'Engine unreachable';
      });
    }
  }

  void _applyDefaults() {
    final options = _options;
    if (options == null) return;
    final android = options.android;
    // Prefer an installed image so creation is fast and needs no download.
    final images = _sortedImages(android.systemImages);
    _imageId = images.isNotEmpty ? images.first.id : null;
    _profileId = _preferredProfile(android.deviceProfiles);
    final ios = options.ios;
    _deviceTypeId =
        ios.deviceTypes.isNotEmpty ? ios.deviceTypes.first.id : null;
    final available = ios.runtimes.where((r) => r.available).toList();
    _runtimeId = available.isNotEmpty
        ? available.first.id
        : (ios.runtimes.isNotEmpty ? ios.runtimes.first.id : null);
  }

  /// Installed images first, then by descending API level.
  List<SystemImage> _sortedImages(List<SystemImage> images) {
    final sorted = [...images];
    sorted.sort((a, b) {
      if (a.installed != b.installed) return a.installed ? -1 : 1;
      return b.api.compareTo(a.api);
    });
    return sorted;
  }

  String? _preferredProfile(List<DeviceProfile> profiles) {
    for (final p in profiles) {
      if (p.id == 'pixel_7') return p.id;
    }
    for (final p in profiles) {
      if (p.id.toLowerCase().startsWith('pixel')) return p.id;
    }
    return profiles.isNotEmpty ? profiles.first.id : null;
  }

  bool get _canCreate {
    if (_creating) return false;
    if (_nameController.text.trim().isEmpty) return false;
    if (_platform == 'android') {
      return _profileId != null && _imageId != null;
    }
    return _deviceTypeId != null && _runtimeId != null;
  }

  Future<void> _create() async {
    final state = context.read<AppState>();
    final name = _nameController.text.trim();
    setState(() {
      _creating = true;
      _job = null;
    });
    try {
      final job = _platform == 'android'
          ? await state.client.createVirtualDevice(
              platform: 'android',
              name: name,
              deviceProfile: _profileId,
              systemImage: _imageId,
            )
          : await state.client.createVirtualDevice(
              platform: 'ios',
              name: name,
              deviceType: _deviceTypeId,
              runtime: _runtimeId,
            );
      if (!mounted) return;
      setState(() => _job = job);
      _poll(job.id);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _creating = false;
        _job = null;
        _loadError = e is EngineException ? e.message : 'Engine unreachable';
      });
    }
  }

  void _poll(String jobId) {
    _pollTimer?.cancel();
    _pollTimer =
        Timer.periodic(const Duration(milliseconds: 1200), (timer) async {
      final state = context.read<AppState>();
      try {
        final job = await state.client.createJob(jobId);
        if (!mounted) return;
        setState(() => _job = job);
        if (job.done) {
          timer.cancel();
          setState(() => _creating = false);
          if (job.succeeded) {
            // Surface the new (stopped) device in the sidebar immediately.
            await state.refresh();
            if (mounted) Navigator.of(context).pop();
          }
        }
      } catch (_) {
        // Transient poll failure; keep trying until the timer is cancelled.
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('New virtual device', style: TextStyle(fontSize: 16)),
      content: SizedBox(width: 440, child: _content()),
      actions: _actions(),
    );
  }

  Widget _content() {
    if (_loading) {
      return const SizedBox(
        height: 120,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_job != null && (_creating || _job!.done)) {
      return _progressView(_job!);
    }
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _platformToggle(),
          const SizedBox(height: 16),
          TextField(
            controller: _nameController,
            autofocus: true,
            style: const TextStyle(fontSize: 13),
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(
              labelText: 'Device name',
              hintText: 'e.g. Pixel_7_API_35',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          if (_platform == 'android') ..._androidFields() else ..._iosFields(),
          if (_loadError != null) ...[
            const SizedBox(height: 12),
            Text(_loadError!,
                style: const TextStyle(color: OM.danger, fontSize: 12)),
          ],
        ],
      ),
    );
  }

  Widget _platformToggle() {
    return SegmentedButton<String>(
      segments: const [
        ButtonSegment(
          value: 'android',
          label: Text('Android'),
          icon: Icon(Icons.phone_android, size: 16),
        ),
        ButtonSegment(
          value: 'ios',
          label: Text('iOS'),
          icon: Icon(Icons.phone_iphone, size: 16),
        ),
      ],
      selected: {_platform},
      onSelectionChanged: (selection) =>
          setState(() => _platform = selection.first),
      style: ButtonStyle(
        visualDensity: VisualDensity.compact,
        textStyle: WidgetStateProperty.all(const TextStyle(fontSize: 12)),
      ),
    );
  }

  List<Widget> _androidFields() {
    final android = _options?.android;
    if (android == null) return const [];
    if (!android.available) {
      return [_unavailableNote(android.reason ?? 'Android SDK not available.')];
    }
    final images = _sortedImages(android.systemImages);
    return [
      _dropdown<String>(
        label: 'Hardware profile',
        value: _profileId,
        items: [
          for (final p in android.deviceProfiles)
            DropdownMenuItem(value: p.id, child: Text(p.name)),
        ],
        onChanged: (v) => setState(() => _profileId = v),
      ),
      const SizedBox(height: 12),
      _dropdown<String>(
        label: 'System image',
        value: _imageId,
        items: [
          for (final img in images)
            DropdownMenuItem(
              value: img.id,
              child: Text(
                img.installed ? img.label : '${img.label}  (download)',
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        onChanged: (v) => setState(() => _imageId = v),
      ),
      if (_imageId != null && !_isInstalled(_imageId!, images)) ...[
        const SizedBox(height: 8),
        const Text(
          'This image is not installed yet — it will be downloaded first, '
          'which can take several minutes.',
          style: TextStyle(color: OM.textMuted, fontSize: 11),
        ),
      ],
    ];
  }

  bool _isInstalled(String id, List<SystemImage> images) {
    for (final img in images) {
      if (img.id == id) return img.installed;
    }
    return false;
  }

  List<Widget> _iosFields() {
    final ios = _options?.ios;
    if (ios == null) return const [];
    if (!ios.available) {
      return [_unavailableNote(ios.reason ?? 'iOS simulators not available.')];
    }
    return [
      _dropdown<String>(
        label: 'Device type',
        value: _deviceTypeId,
        items: [
          for (final d in ios.deviceTypes)
            DropdownMenuItem(value: d.id, child: Text(d.name)),
        ],
        onChanged: (v) => setState(() => _deviceTypeId = v),
      ),
      const SizedBox(height: 12),
      _dropdown<String>(
        label: 'Runtime',
        value: _runtimeId,
        items: [
          for (final r in ios.runtimes)
            DropdownMenuItem(
              value: r.id,
              child: Text(r.available ? r.name : '${r.name}  (unavailable)'),
            ),
        ],
        onChanged: (v) => setState(() => _runtimeId = v),
      ),
    ];
  }

  Widget _unavailableNote(String reason) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: OM.bg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: OM.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline, size: 16, color: OM.textMuted),
          const SizedBox(width: 8),
          Expanded(
            child: Text(reason,
                style: const TextStyle(color: OM.textMuted, fontSize: 12)),
          ),
        ],
      ),
    );
  }

  Widget _dropdown<T>({
    required String label,
    required T? value,
    required List<DropdownMenuItem<T>> items,
    required ValueChanged<T?> onChanged,
  }) {
    return DropdownButtonFormField<T>(
      initialValue: value,
      isExpanded: true,
      style: const TextStyle(fontSize: 13, color: OM.text),
      dropdownColor: OM.card,
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
        isDense: true,
      ),
      items: items,
      onChanged: onChanged,
    );
  }

  Widget _progressView(CreateJob job) {
    final downloading = job.progress != null && !job.done;
    final logLine = job.log.isNotEmpty ? job.log.last : '';
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            if (job.succeeded)
              const Icon(Icons.check_circle, color: OM.accent, size: 18)
            else if (job.failed)
              const Icon(Icons.error_outline, color: OM.danger, size: 18)
            else
              const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                job.succeeded
                    ? 'Created ${job.name}'
                    : job.failed
                        ? 'Failed to create ${job.name}'
                        : downloading
                            ? 'Downloading system image…'
                            : 'Creating ${job.name}…',
                style: const TextStyle(fontSize: 13),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        LinearProgressIndicator(
          value: downloading ? job.progress! / 100.0 : null,
          minHeight: 4,
          backgroundColor: OM.border,
        ),
        if (job.progress != null && !job.done) ...[
          const SizedBox(height: 6),
          Text('${job.progress}%',
              style: const TextStyle(color: OM.textMuted, fontSize: 11)),
        ],
        if (logLine.isNotEmpty) ...[
          const SizedBox(height: 10),
          Text(
            logLine,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: OM.textMuted, fontSize: 11),
          ),
        ],
        if (job.failed && job.error != null) ...[
          const SizedBox(height: 8),
          Text(job.error!,
              style: const TextStyle(color: OM.danger, fontSize: 12)),
        ],
      ],
    );
  }

  List<Widget> _actions() {
    final job = _job;
    if (job != null && job.failed) {
      return [
        TextButton(
          onPressed: () => setState(() {
            _job = null;
            _loadError = null;
          }),
          child: const Text('Back'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ];
    }
    if (_creating) {
      // Android downloads run on the engine; let the user close and keep waiting.
      return [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Run in background'),
        ),
      ];
    }
    return [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: _canCreate ? _create : null,
        child: const Text('Create'),
      ),
    ];
  }
}
