import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:openmob/main.dart';
import 'package:openmob/state/app_state.dart';

void main() {
  testWidgets('renders engine-offline empty state',
      (WidgetTester tester) async {
    final state = AppState();
    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: state,
        child: const OpenMobApp(),
      ),
    );

    expect(find.text('Engine offline'), findsOneWidget);
    expect(find.text('OpenMob Engine'), findsOneWidget);
  });
}
