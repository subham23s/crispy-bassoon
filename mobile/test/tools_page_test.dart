import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:cybersecra_x_mobile/main.dart';
import 'package:cybersecra_x_mobile/services/api_service.dart';

class ToolsApiFixture extends ApiService {
  ToolsApiFixture() : super(baseUrl: 'https://api.example.test');
  String? input;
  @override
  Future<Map<String, dynamic>> analyzeIoc(String text) async {
    input = text;
    return {'count': 1, 'analysis_basis': 'widget fixture'};
  }
}

void main() {
  testWidgets('defensive tools submit entered IOC text and render the response', (tester) async {
    final api = ToolsApiFixture();
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: ToolsPage(api: api))));
    await tester.enterText(find.byType(TextField), '192.0.2.1');
    await tester.ensureVisible(find.text('Classify IOCs'));
    await tester.tap(find.text('Classify IOCs'));
    await tester.pumpAndSettle();
    expect(api.input, '192.0.2.1');
    expect(find.textContaining('widget fixture'), findsOneWidget);
  });
}
