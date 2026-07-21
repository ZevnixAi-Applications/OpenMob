import 'dart:math';

/// Translates a point on a source device screen to the proportionally
/// equivalent point on a destination device screen.
///
/// A tap at (50%, 30%) of the source lands at (50%, 30%) of the target,
/// regardless of resolution or aspect ratio. The result is clamped to the
/// destination bounds. Returns null when any dimension is unknown (<= 0),
/// in which case the caller should skip that device.
Point<int>? translatePoint({
  required int x,
  required int y,
  required int srcWidth,
  required int srcHeight,
  required int dstWidth,
  required int dstHeight,
}) {
  if (srcWidth <= 0 || srcHeight <= 0 || dstWidth <= 0 || dstHeight <= 0) {
    return null;
  }
  final dx = (x * dstWidth / srcWidth).round().clamp(0, dstWidth - 1);
  final dy = (y * dstHeight / srcHeight).round().clamp(0, dstHeight - 1);
  return Point<int>(dx, dy);
}
