import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:cybersecra_x_mobile/services/api_service.dart';
import 'package:cybersecra_x_mobile/workspace_page.dart';

class WorkspaceApiFixture extends ApiService {
  WorkspaceApiFixture() : super(baseUrl: 'https://api.example.test');
  final List<Map<String, dynamic>> saved = [];
  final List<Map<String, dynamic>> notes = [];
  @override
  Future<Map<String, dynamic>> workspaces() async => {'workspaces': saved};
  @override
  Future<Map<String, dynamic>> createWorkspace(String name) async {
    final workspace = {'id': 'fixture-workspace', 'name': name};
    saved.add(workspace);
    return {'workspace': workspace};
  }
  @override
  Future<Map<String, dynamic>> workspaceNotes(String id) async => {'notes': notes};
  @override
  Future<Map<String, dynamic>> workspaceEvidence(String id) async => {'evidence': []};
  @override
  Future<Map<String, dynamic>> createNote(String id, String body) async {
    notes.add({'body': body});
    return {'note': notes.last};
  }
}

void main() {
  testWidgets('creates a workspace and saves a note through the API', (tester) async {
    final api = WorkspaceApiFixture();
    await tester.pumpWidget(MaterialApp(home: WorkspacePage(api: api)));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, 'Research fixture');
    await tester.tap(find.text('Create workspace'));
    await tester.pumpAndSettle();
    expect(api.saved.single['name'], 'Research fixture');
    final note = find.widgetWithText(TextField, 'Research note');
    await tester.ensureVisible(note);
    await tester.enterText(note, 'User-authored evidence note');
    await tester.ensureVisible(find.text('Save note'));
    await tester.tap(find.text('Save note'));
    await tester.pumpAndSettle();
    expect(api.notes.single['body'], 'User-authored evidence note');
    expect(find.text('User-authored evidence note'), findsOneWidget);
  });
}
