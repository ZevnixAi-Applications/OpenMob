import 'package:flutter_test/flutter_test.dart';

import 'package:openmob_testbed/main.dart';

void main() {
  testWidgets('Testbed builds', (WidgetTester tester) async {
    await tester.pumpWidget(const TestbedApp());
    expect(find.byType(TestbedHome), findsOneWidget);
  });
}
