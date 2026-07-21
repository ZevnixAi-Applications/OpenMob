import 'dart:io';

/// Launches the OpenMob engine from the desktop app (macOS only).
class EngineLauncher {
  static bool get isSupported => Platform.isMacOS;

  /// The command runs through a login shell so it sees the user's normal PATH
  /// (Homebrew's `uv` etc.), which GUI apps do not inherit.
  static const String shell = '/bin/zsh';

  static List<String> shellArgs(String command) => ['-l', '-c', command];

  /// Default engine command shown (and used) until the user overrides it.
  ///
  /// When the app runs out of a checkout of the repo (dev builds live under
  /// app/build/...), the engine project is located by walking up from the
  /// working directory / executable looking for engine/pyproject.toml and the
  /// command becomes `uv run --project <repo>/engine openmob serve`. Outside a
  /// checkout we fall back to `openmob serve` (engine installed on PATH); the
  /// field in Engine settings lets the user point anywhere else.
  static String defaultCommand() {
    final engineDir = findEngineDir();
    if (engineDir != null) {
      return 'uv run --project "$engineDir" openmob serve';
    }
    return 'openmob serve';
  }

  /// Nearest ancestor `engine/` directory containing a pyproject.toml, or null.
  static String? findEngineDir() {
    final starts = [
      Directory.current.path,
      File(Platform.resolvedExecutable).parent.path,
    ];
    for (final start in starts) {
      var dir = Directory(start);
      for (var i = 0; i < 12; i++) {
        final candidate = '${dir.path}${Platform.pathSeparator}engine';
        if (File('$candidate${Platform.pathSeparator}pyproject.toml')
            .existsSync()) {
          return candidate;
        }
        final parent = dir.parent;
        if (parent.path == dir.path) break;
        dir = parent;
      }
    }
    return null;
  }

  /// Starts [command] detached, so the engine keeps running if the app quits.
  ///
  /// Detached also means stdout/stderr are not captured; success is judged by
  /// polling the engine's /health endpoint (see AppState.startEngine).
  static Future<void> start(String command) async {
    await Process.start(
      shell,
      shellArgs(command),
      mode: ProcessStartMode.detached,
    );
  }
}
