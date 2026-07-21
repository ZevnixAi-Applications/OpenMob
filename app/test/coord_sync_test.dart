import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:openmob/util/coord_sync.dart';

void main() {
  group('translatePoint', () {
    test('maps proportionally: 50%, 30% lands at 50%, 30%', () {
      final p = translatePoint(
        x: 540, // 50% of 1080
        y: 720, // 30% of 2400
        srcWidth: 1080,
        srcHeight: 2400,
        dstWidth: 750,
        dstHeight: 1334,
      );
      expect(p, const Point<int>(375, 400)); // 50% of 750, 30% of 1334
    });

    test('identity when source and destination match', () {
      final p = translatePoint(
        x: 123,
        y: 456,
        srcWidth: 1080,
        srcHeight: 1920,
        dstWidth: 1080,
        dstHeight: 1920,
      );
      expect(p, const Point<int>(123, 456));
    });

    test('handles non-uniform aspect ratios independently per axis', () {
      final p = translatePoint(
        x: 100,
        y: 100,
        srcWidth: 1000,
        srcHeight: 1000,
        dstWidth: 500,
        dstHeight: 2000,
      );
      expect(p, const Point<int>(50, 200));
    });

    test('origin maps to origin', () {
      final p = translatePoint(
        x: 0,
        y: 0,
        srcWidth: 1080,
        srcHeight: 1920,
        dstWidth: 750,
        dstHeight: 1334,
      );
      expect(p, const Point<int>(0, 0));
    });

    test('clamps to destination bounds at the far edge', () {
      // 1079/1080 rounds to 540 on a 540-wide target; must clamp to 539.
      final p = translatePoint(
        x: 1079,
        y: 1919,
        srcWidth: 1080,
        srcHeight: 1920,
        dstWidth: 540,
        dstHeight: 960,
      );
      expect(p!.x, lessThan(540));
      expect(p.y, lessThan(960));
      expect(p, const Point<int>(539, 959));
    });

    test('returns null for unknown dimensions', () {
      expect(
        translatePoint(
            x: 1, y: 1, srcWidth: 0, srcHeight: 100, dstWidth: 100, dstHeight: 100),
        isNull,
      );
      expect(
        translatePoint(
            x: 1, y: 1, srcWidth: 100, srcHeight: 0, dstWidth: 100, dstHeight: 100),
        isNull,
      );
      expect(
        translatePoint(
            x: 1, y: 1, srcWidth: 100, srcHeight: 100, dstWidth: 0, dstHeight: 100),
        isNull,
      );
      expect(
        translatePoint(
            x: 1, y: 1, srcWidth: 100, srcHeight: 100, dstWidth: 100, dstHeight: 0),
        isNull,
      );
    });
  });
}
