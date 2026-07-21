import 'package:flutter_test/flutter_test.dart';
import 'package:openmob/api/engine_client.dart';

void main() {
  group('CreateOptions.fromJson', () {
    test('parses android and ios sections', () {
      final options = CreateOptions.fromJson({
        'android': {
          'available': true,
          'reason': null,
          'device_profiles': [
            {'id': 'pixel_7', 'name': 'Pixel 7'},
          ],
          'system_images': [
            {
              'id': 'system-images;android-35;google_apis;arm64-v8a',
              'api': '35',
              'tag': 'google_apis',
              'abi': 'arm64-v8a',
              'installed': false,
            },
          ],
        },
        'ios': {
          'available': true,
          'reason': null,
          'device_types': [
            {'id': 'dt.iPhone-17', 'name': 'iPhone 17'},
          ],
          'runtimes': [
            {'id': 'rt.iOS-26-3', 'name': 'iOS 26.3', 'available': true},
          ],
        },
      });

      expect(options.android.available, isTrue);
      expect(options.android.deviceProfiles.single.id, 'pixel_7');
      final image = options.android.systemImages.single;
      expect(image.installed, isFalse);
      expect(image.label, 'Android 35 · google_apis · arm64-v8a');
      expect(options.ios.deviceTypes.single.name, 'iPhone 17');
      expect(options.ios.runtimes.single.available, isTrue);
    });

    test('marks a platform unavailable with a reason', () {
      final options = CreateOptions.fromJson({
        'android': {
          'available': false,
          'reason': 'sdkmanager not found',
          'device_profiles': [],
          'system_images': [],
        },
        'ios': {
          'available': false,
          'reason': 'no iOS runtimes installed',
          'device_types': [],
          'runtimes': [],
        },
      });

      expect(options.android.available, isFalse);
      expect(options.android.reason, 'sdkmanager not found');
      expect(options.ios.reason, 'no iOS runtimes installed');
    });
  });

  group('CreateJob.fromJson', () {
    test('parses a running download job', () {
      final job = CreateJob.fromJson({
        'id': 'abc',
        'platform': 'android',
        'name': 'Test_AVD',
        'status': 'running',
        'progress': 42,
        'log': ['Installing…', 'fetch 42%'],
        'error': null,
        'device_id': null,
      });

      expect(job.done, isFalse);
      expect(job.progress, 42);
      expect(job.log.last, 'fetch 42%');
    });

    test('parses a succeeded job with a device id', () {
      final job = CreateJob.fromJson({
        'id': 'abc',
        'platform': 'ios',
        'name': 'My iPhone',
        'status': 'succeeded',
        'progress': null,
        'log': ['done'],
        'error': null,
        'device_id': 'UDID-1',
      });

      expect(job.succeeded, isTrue);
      expect(job.done, isTrue);
      expect(job.deviceId, 'UDID-1');
    });

    test('flags a failed job', () {
      final job = CreateJob.fromJson({
        'id': 'abc',
        'platform': 'ios',
        'name': 'Bad',
        'status': 'failed',
        'progress': null,
        'log': <String>[],
        'error': 'boom',
        'device_id': null,
      });

      expect(job.failed, isTrue);
      expect(job.error, 'boom');
    });
  });
}
