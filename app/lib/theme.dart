import 'package:flutter/material.dart';

/// OpenMob "device lab" palette: dark charcoal with a single green accent.
abstract final class OM {
  static const Color bg = Color(0xFF16181D);
  static const Color sidebar = Color(0xFF1A1D23);
  static const Color card = Color(0xFF1F232B);
  static const Color cardHover = Color(0xFF242933);
  static const Color border = Color(0xFF2A2F3A);
  static const Color text = Color(0xFFE7E9EE);
  static const Color textMuted = Color(0xFF8A919E);
  static const Color accent = Color(0xFF3DDC97);
  static const Color danger = Color(0xFFE05B5B);

  /// Sync-input mode affordance (pane borders + broadcast flash).
  static const Color sync = Color(0xFF5B8DEF);

  static ThemeData theme() {
    final base = ThemeData(
      brightness: Brightness.dark,
      useMaterial3: true,
      scaffoldBackgroundColor: bg,
      colorScheme: const ColorScheme.dark(
        primary: accent,
        secondary: accent,
        surface: card,
        onPrimary: Color(0xFF0D1512),
        onSurface: text,
        error: danger,
      ),
      splashFactory: NoSplash.splashFactory,
      dividerColor: border,
    );
    return base.copyWith(
      textTheme: base.textTheme.apply(
        bodyColor: text,
        displayColor: text,
      ),
      iconTheme: const IconThemeData(color: textMuted, size: 18),
      tooltipTheme: TooltipThemeData(
        decoration: BoxDecoration(
          color: cardHover,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: border),
        ),
        textStyle: const TextStyle(color: text, fontSize: 12),
        waitDuration: const Duration(milliseconds: 400),
      ),
      dialogTheme: base.dialogTheme.copyWith(
        backgroundColor: card,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
          side: const BorderSide(color: border),
        ),
      ),
    );
  }
}
