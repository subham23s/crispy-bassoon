import 'package:flutter/material.dart';
import 'services/api_service.dart';

/// Persistent workspace operations use the same owner-scoped API as the web.
class WorkspacePage extends StatefulWidget {
  const WorkspacePage({required this.api, super.key});
  final ApiService api;
  @override
  State<WorkspacePage> createState() => _WorkspacePageState();
}

class _WorkspacePageState extends State<WorkspacePage> {
  final name = TextEditingController();
  final note = TextEditingController();
  final query = TextEditingController();
  List<Map<String, dynamic>> workspaces = [];
  List<Map<String, dynamic>> notes = [];
  List<Map<String, dynamic>> evidence = [];
  Map<String, dynamic>? answer;
  String? selected;
  String? error;
  bool busy = false;

  @override
  void initState() { super.initState(); run(load); }
  @override
  void dispose() { name.dispose(); note.dispose(); query.dispose(); super.dispose(); }

  List<Map<String, dynamic>> records(dynamic value) => (value as List? ?? []).map((row) => Map<String, dynamic>.from(row as Map)).toList();

  Future<void> run(Future<void> Function() action) async {
    if (busy) return;
    setState(() { busy = true; error = null; });
    try { await action(); }
    catch (exception) { if (mounted) setState(() => error = exception.toString()); }
    finally { if (mounted) setState(() => busy = false); }
  }

  Future<void> load() async {
    final result = await widget.api.workspaces();
    if (!mounted) return;
    setState(() => workspaces = records(result['workspaces']));
    if (selected != null) await loadSelected();
  }

  Future<void> loadSelected() async {
    final id = selected;
    if (id == null) return;
    final results = await Future.wait([widget.api.workspaceNotes(id), widget.api.workspaceEvidence(id)]);
    if (!mounted || id != selected) return;
    setState(() { notes = records(results[0]['notes']); evidence = records(results[1]['evidence']); });
  }

  Future<void> create() async {
    final result = await widget.api.createWorkspace(name.text.trim());
    if (!mounted) return;
    selected = (result['workspace'] as Map)['id'].toString();
    name.clear();
    await load();
  }

  Future<void> ask() async {
    final result = await widget.api.ask(query.text.trim(), 'RESEARCHER', workspaceId: selected);
    if (mounted) setState(() => answer = result);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Research workspaces'), actions: [IconButton(onPressed: busy ? null : () => run(load), icon: const Icon(Icons.refresh))]),
    body: ListView(padding: const EdgeInsets.all(18), children: [
      if (busy) const LinearProgressIndicator(),
      if (error != null) Text(error!, style: const TextStyle(color: Colors.orangeAccent)),
      TextField(controller: name, decoration: const InputDecoration(labelText: 'New workspace name')),
      FilledButton(onPressed: busy ? null : () { if (name.text.trim().isNotEmpty) run(create); }, child: const Text('Create workspace')),
      if (workspaces.isEmpty && !busy) const Text('Create a workspace to save research notes and evidence.'),
      if (workspaces.isNotEmpty) DropdownButtonFormField<String>(
        // Keep compatibility with the documented Flutter 3.22 minimum.
        // ignore: deprecated_member_use
        value: selected,
        decoration: const InputDecoration(labelText: 'Workspace'),
        items: workspaces.map((row) => DropdownMenuItem(value: row['id'].toString(), child: Text(row['name'].toString()))).toList(),
        onChanged: busy ? null : (value) { setState(() { selected = value; notes = []; evidence = []; answer = null; }); run(loadSelected); },
      ),
      if (selected != null) ...[
        const SizedBox(height: 18),
        TextField(controller: query, minLines: 2, maxLines: 5, decoration: const InputDecoration(labelText: 'Research question')),
        FilledButton(onPressed: busy ? null : () { if (query.text.trim().isNotEmpty) run(ask); }, child: const Text('Ask and save answer')),
        if (answer != null) ...[
          Text(answer!['abstained'] == true ? 'ABSTAINED · insufficient evidence' : 'Verified pipeline result', style: const TextStyle(color: Colors.orangeAccent)),
          SelectableText(answer!['answer']?.toString() ?? ''),
          ...records(answer!['evidence']).map((item) => Card(child: ListTile(
            title: Text(item['source']?.toString() ?? 'Source'),
            subtitle: Text(item['text']?.toString() ?? ''),
            trailing: IconButton(tooltip: 'Save evidence', icon: const Icon(Icons.bookmark_add_outlined), onPressed: busy ? null : () => run(() async {
              await widget.api.saveEvidence(selected!, item['chunk_id'].toString());
              await loadSelected();
            })),
          ))),
        ],
        const SizedBox(height: 18),
        TextField(controller: note, minLines: 2, maxLines: 5, decoration: const InputDecoration(labelText: 'Research note')),
        OutlinedButton(onPressed: busy ? null : () { if (note.text.trim().isNotEmpty) run(() async { await widget.api.createNote(selected!, note.text.trim()); if (mounted) note.clear(); await loadSelected(); }); }, child: const Text('Save note')),
        const Text('SAVED NOTES', style: TextStyle(fontWeight: FontWeight.bold)),
        if (notes.isEmpty) const Text('No notes in this workspace.'),
        ...notes.map((row) => Card(child: Padding(padding: const EdgeInsets.all(12), child: SelectableText(row['body']?.toString() ?? '')))),
        const SizedBox(height: 18), const Text('SAVED EVIDENCE', style: TextStyle(fontWeight: FontWeight.bold)),
        if (evidence.isEmpty) const Text('No saved evidence in this workspace.'),
        ...evidence.map((row) { final snapshot = row['snapshot'] as Map? ?? {}; return Card(child: ListTile(title: Text(snapshot['source']?.toString() ?? ''), subtitle: Text(snapshot['text']?.toString() ?? ''))); }),
      ],
    ]),
  );
}
