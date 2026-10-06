import 'dart:async';
import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

import 'services/api_service.dart';
import 'workspace_page.dart';

void main() => runApp(const CyberSecRaApp());

class CyberSecRaApp extends StatelessWidget {
  const CyberSecRaApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'CyberSecRA-X',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff5b9dff), brightness: Brightness.dark), scaffoldBackgroundColor: const Color(0xff080c14), useMaterial3: true),
        home: const AuthGate(),
      );
}

class AuthGate extends StatefulWidget {
  const AuthGate({super.key});
  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  late final ApiService api = ApiService(onSessionExpired: _handleSessionExpired);
  final email = TextEditingController();
  final password = TextEditingController();
  bool loading = false;
  bool restoring = true;
  String? error;

  @override
  void initState() {
    super.initState();
    _restoreSession();
  }

  Future<void> _restoreSession() async {
    final restored = await api.restoreSession();
    if (!mounted) return;
    setState(() => restoring = false);
    if (restored) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => HomeShell(api: api)),
      );
    }
  }

  void _handleSessionExpired() {
    if (!mounted) return;
    setState(() => error = 'Your session has expired. Please sign in again.');
  }

  Future<void> signIn(bool register) async {
    final address = email.text.trim();
    if (address.isEmpty || password.text.isEmpty) {
      setState(() => error = 'Email and password are required.');
      return;
    }
    setState(() { loading = true; error = null; });
    try {
      if (register) {
        await api.register(address, password.text);
      } else {
        await api.login(address, password.text);
      }
      if (mounted) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => HomeShell(api: api)),
        );
      }
    } catch (exception) {
      if (mounted) {
        setState(() => error = exception.toString());
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  void dispose() {
    email.dispose();
    password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(child: Center(child: SingleChildScrollView(padding: const EdgeInsets.all(24), child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 430), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('CX', style: TextStyle(color: Color(0xff91bcff), fontWeight: FontWeight.w900, fontSize: 34)),
          const SizedBox(height: 26),
          const Text('CyberSecRA-X', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 28)),
          const SizedBox(height: 7),
          const Text('Evidence-aware cybersecurity research intelligence.', style: TextStyle(color: Colors.white60)),
          const SizedBox(height: 34),
          TextField(controller: email, keyboardType: TextInputType.emailAddress, decoration: const InputDecoration(labelText: 'Email', border: OutlineInputBorder())),
          const SizedBox(height: 14),
          TextField(controller: password, obscureText: true, decoration: const InputDecoration(labelText: 'Password · 10+ characters', border: OutlineInputBorder())),
          if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error!, style: const TextStyle(color: Colors.orangeAccent))),
          const SizedBox(height: 22),
          if (restoring) const LinearProgressIndicator(),
          SizedBox(width: double.infinity, child: FilledButton(onPressed: loading || restoring ? null : () => signIn(false), child: Text(restoring ? 'Restoring session…' : loading ? 'Connecting…' : 'Sign in'))),
          SizedBox(width: double.infinity, child: TextButton(onPressed: loading || restoring ? null : () => signIn(true), child: const Text('Create researcher account'))),
          const SizedBox(height: 18),
          const Text('The mobile client uses the same FastAPI endpoints as the web dashboard. Configure API_BASE_URL for a physical device.', style: TextStyle(color: Colors.white38, fontSize: 12)),
        ]))))),
      );
}

class HomeShell extends StatefulWidget {
  const HomeShell({required this.api, super.key});
  final ApiService api;
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int tab = 0;
  late final pages = [DashboardPage(api: widget.api, onNavigate: (index) => setState(() => tab = index)), AskPage(api: widget.api), ToolsPage(api: widget.api), LibraryPage(api: widget.api), ResearchPage(api: widget.api)];

  @override
  void initState() {
    super.initState();
    widget.api.onSessionExpired = _handleSessionExpired;
  }

  void _handleSessionExpired() {
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const AuthGate()),
      (_) => false,
    );
  }

  Future<void> _logout() async {
    try {
      await widget.api.logout();
    } catch (_) {
      // Local credentials are cleared by ApiService even when the server is
      // unreachable, so logout remains safe offline.
    } finally {
      if (mounted) _handleSessionExpired();
    }
  }

  @override
  void dispose() {
    if (widget.api.onSessionExpired == _handleSessionExpired) {
      widget.api.onSessionExpired = null;
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('CyberSecRA-X'), actions: [IconButton(onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => SettingsPage(api: widget.api))), icon: const Icon(Icons.settings_outlined)), IconButton(onPressed: _logout, icon: const Icon(Icons.logout))]),
        body: pages[tab],
        bottomNavigationBar: NavigationBar(selectedIndex: tab, onDestinationSelected: (value) => setState(() => tab = value), destinations: const [NavigationDestination(icon: Icon(Icons.dashboard_outlined), label: 'Home'), NavigationDestination(icon: Icon(Icons.search), label: 'Ask'), NavigationDestination(icon: Icon(Icons.shield_outlined), label: 'Tools'), NavigationDestination(icon: Icon(Icons.folder_outlined), label: 'Library'), NavigationDestination(icon: Icon(Icons.science_outlined), label: 'Research')]),
      );
}

class DashboardPage extends StatelessWidget {
  const DashboardPage({required this.api, required this.onNavigate, super.key});
  final ApiService api;
  final ValueChanged<int> onNavigate;
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(18), children: [
        const Text('EVIDENCE-AWARE INTELLIGENCE', style: TextStyle(color: Color(0xff71a9ff), letterSpacing: 1.4, fontSize: 11, fontWeight: FontWeight.bold)),
        const SizedBox(height: 10), const Text('Why should I trust this answer?', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700)),
        const SizedBox(height: 10), const Text('Ask questions, inspect citations, and see when the system abstains instead of guessing.', style: TextStyle(color: Colors.white60)),
        const SizedBox(height: 22),
        _ActionCard(icon: Icons.auto_awesome, title: 'Ask a question', subtitle: 'Retrieval · verification · CERS', onTap: () => onNavigate(1)),
        _ActionCard(icon: Icons.bug_report_outlined, title: 'Investigate a CVE', subtitle: 'Use the defensive tools workspace', onTap: () => onNavigate(2)),
        _ActionCard(icon: Icons.upload_file_outlined, title: 'Upload evidence', subtitle: 'PDF, TXT, CSV, JSON with provenance', onTap: () => onNavigate(3)),
        const SizedBox(height: 20),
        Card(child: Padding(padding: const EdgeInsets.all(16), child: FutureBuilder<Map<String, dynamic>>(future: api.health(), builder: (context, snapshot) => Row(children: [Icon(snapshot.hasData ? Icons.check_circle : Icons.cloud_off, color: snapshot.hasData ? Colors.greenAccent : Colors.orangeAccent), const SizedBox(width: 10), Expanded(child: Text(snapshot.hasData ? 'Evidence API online' : 'API status unavailable · check backend URL'))])))),
      ]);
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({required this.icon, required this.title, required this.subtitle, required this.onTap});
  final IconData icon; final String title; final String subtitle; final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Card(child: ListTile(onTap: onTap, leading: Icon(icon, color: const Color(0xff75aaff)), title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)), subtitle: Text(subtitle), trailing: const Icon(Icons.chevron_right)));
}

class AskPage extends StatefulWidget {
  const AskPage({required this.api, super.key});
  final ApiService api;
  @override
  State<AskPage> createState() => _AskPageState();
}

class _AskPageState extends State<AskPage> {
  final query = TextEditingController();
  final speech = stt.SpeechToText();
  Map<String, dynamic>? result;
  bool loading = false;
  bool listening = false;
  String stage = ''; 
  String streamedAnswer = ''; 

  @override
  void dispose() {
    query.dispose();
    unawaited(speech.stop());
    super.dispose();
  }

  Future<void> ask() async {
    if (query.text.trim().isEmpty) return;
    setState(() { loading = true; stage = 'SEARCHING'; streamedAnswer = ''; result = null; });
    try {
      result = await widget.api.askStream(query.text.trim(), 'RESEARCHER', onStage: (value) { if (mounted) setState(() => stage = value); }, onDelta: (value) { if (mounted) setState(() => streamedAnswer += value); }, onReset: () { if (mounted) setState(() => streamedAnswer = ''); });
    } catch (exception) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(exception.toString()))); } finally { if (mounted) setState(() => loading = false); }
  }

  Future<void> voice() async {
    if (!await speech.initialize()) return;
    if (listening) {
      await speech.stop();
      if (mounted) setState(() => listening = false);
      return;
    }
    if (mounted) setState(() => listening = true);
    await speech.listen(
      onResult: (value) {
        if (mounted) setState(() => query.text = value.recognizedWords);
      },
    );
  }

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(18), children: [
        const Text('ASK CYBERSECRA-X', style: TextStyle(color: Color(0xff71a9ff), letterSpacing: 1.4, fontSize: 11, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8), const Text('Evidence console', style: TextStyle(fontSize: 25, fontWeight: FontWeight.w700)), const SizedBox(height: 18),
        TextField(controller: query, minLines: 4, maxLines: 8, decoration: InputDecoration(hintText: 'Ask a cybersecurity question…', border: const OutlineInputBorder(), suffixIcon: IconButton(onPressed: voice, icon: Icon(listening ? Icons.mic : Icons.mic_none)))),
        const SizedBox(height: 12), Row(children: [Expanded(child: FilledButton.icon(onPressed: loading ? null : ask, icon: const Icon(Icons.search), label: Text(loading ? '$stage…' : 'Analyze evidence'))), const SizedBox(width: 10), IconButton(onPressed: voice, icon: const Icon(Icons.mic_none))]),
        if (loading && streamedAnswer.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 18), child: Text(streamedAnswer, style: const TextStyle(height: 1.5))),
        if (result != null) ...[_AnswerView(result: result!)],
      ]);
}

class _AnswerView extends StatelessWidget {
  const _AnswerView({required this.result});
  final Map<String, dynamic> result;
  @override
  Widget build(BuildContext context) {
    final cers = ((result['cers'] as Map?)?['percentage'] as num?) ?? 0;
    final evidence = (result['evidence'] as List? ?? const []).cast<Map>();
    final claims = (result['claims'] as List? ?? const []).cast<Map>();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SizedBox(height: 24), Text(result['abstained'] == true ? 'ABSTAINED · EVIDENCE INSUFFICIENT' : 'ANSWER', style: const TextStyle(color: Color(0xffffbd73), letterSpacing: 1.2, fontSize: 11, fontWeight: FontWeight.bold)),
      const SizedBox(height: 8), Text(result['answer']?.toString() ?? '', style: const TextStyle(height: 1.6)),
      const SizedBox(height: 18), Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [const Text('CERS · project-defined reliability signal', style: TextStyle(fontWeight: FontWeight.w600)), const SizedBox(height: 8), LinearProgressIndicator(value: cers.toDouble() / 100), const SizedBox(height: 8), Text('${cers.toStringAsFixed(1)}% · not a probability of truth', style: const TextStyle(color: Colors.white60, fontSize: 12))]))),
      const SizedBox(height: 14), const Text('CLAIM VERIFICATION', style: TextStyle(color: Color(0xff71a9ff), letterSpacing: 1.2, fontSize: 11, fontWeight: FontWeight.bold)),
      ...claims.map((claim) => ListTile(contentPadding: EdgeInsets.zero, title: Text('${claim['status']} · ${claim['claim']}'), subtitle: Text(claim['explanation']?.toString() ?? ''))),
      const SizedBox(height: 14), const Text('SOURCES', style: TextStyle(color: Color(0xff71a9ff), letterSpacing: 1.2, fontSize: 11, fontWeight: FontWeight.bold)),
      ...evidence.asMap().entries.map((entry) { final item = entry.value; return Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('[C${entry.key + 1}] ${item['source'] ?? ''}', style: const TextStyle(fontWeight: FontWeight.bold)), Text(item['text']?.toString() ?? ''), if (item['url'] != null) SelectableText(item['url'].toString(), style: const TextStyle(color: Color(0xff91bcff))), if (item['page_number'] != null) Text('Page ${item['page_number']}')]))); }),
      if ((result['conflicts'] as List? ?? []).isNotEmpty) ...[const Text('POSSIBLE CONFLICTS'), SelectableText(const JsonEncoder.withIndent('  ').convert(result['conflicts']))],
      const SizedBox(height: 14), const Text('LIMITATIONS'),
      ...(result['limitations'] as List? ?? []).map((item) => Text('• $item')),
    ]);
  }
}

class ToolsPage extends StatefulWidget {
  const ToolsPage({required this.api, super.key});
  final ApiService api;
  @override
  State<ToolsPage> createState() => _ToolsPageState();
}

class _ToolsPageState extends State<ToolsPage> {
  final input = TextEditingController();
  String output = '';
  bool loading = false;

  @override
  void dispose() {
    input.dispose();
    super.dispose();
  }

  Future<void> analyze(bool ioc) async {
    if (input.text.trim().isEmpty || loading) return;
    setState(() => loading = true);
    try {
      final result = ioc
          ? await widget.api.analyzeIoc(input.text.trim())
          : await widget.api.analyzeLog(input.text.trim());
      if (mounted) setState(() => output = const JsonEncoder.withIndent('  ').convert(result));
    } catch (exception) {
      if (mounted) setState(() => output = exception.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }
  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(18),
        children: [
          const Text('DEFENSIVE TOOLS', style: TextStyle(color: Color(0xff71a9ff), letterSpacing: 1.4, fontSize: 11, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          const Text('Triage workspace', style: TextStyle(fontSize: 25, fontWeight: FontWeight.w700)),
          const SizedBox(height: 18),
          TextField(controller: input, minLines: 7, maxLines: 12, decoration: const InputDecoration(hintText: 'Paste logs, IOC text, or an alert…', border: OutlineInputBorder())),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: FilledButton(onPressed: loading ? null : () => analyze(false), child: Text(loading ? 'Analyzing…' : 'Analyze logs'))),
            const SizedBox(width: 10),
            Expanded(child: OutlinedButton(onPressed: loading ? null : () => analyze(true), child: const Text('Classify IOCs'))),
          ]),
          const SizedBox(height: 18),
          SelectableText(output, style: const TextStyle(color: Colors.white70)),
        ],
      );
}

class LibraryPage extends StatefulWidget {
  const LibraryPage({required this.api, super.key});
  final ApiService api;
  @override
  State<LibraryPage> createState() => _LibraryPageState();
}

class _LibraryPageState extends State<LibraryPage> {
  List<dynamic> documents = [];
  String message = '';
  @override
  void initState() { super.initState(); refresh(); }
  Future<void> refresh() async {
    try {
      final result = await widget.api.documents();
      if (mounted) {
        setState(() => documents = result['documents'] as List? ?? []);
      }
    } catch (exception) {
      if (mounted) setState(() => message = exception.toString());
    }
  }

  Future<void> upload() async {
    final result = await FilePicker.platform.pickFiles(withData: true);
    if (!mounted || result == null || result.files.single.bytes == null) return;
    try {
      final uploaded = await widget.api.upload(
        result.files.single.name,
        result.files.single.bytes!,
      );
      final completed = await widget.api.waitForUpload(uploaded, onStatus: (status) { if (mounted) setState(() => message = status); });
      if (mounted) setState(() => message = '${completed['status']}: ${result.files.single.name}');
      await refresh();
    } catch (exception) {
      if (mounted) setState(() => message = exception.toString());
    }
  }

  Future<void> camera() async {
    final photo = await ImagePicker().pickImage(source: ImageSource.camera);
    if (!mounted || photo == null) return;
    final bytes = await photo.readAsBytes();
    try {
      final uploaded = await widget.api.upload(photo.name, bytes);
      final completed = await widget.api.waitForUpload(uploaded, onStatus: (status) { if (mounted) setState(() => message = status); });
      if (mounted) setState(() => message = '${completed['status']}: ${photo.name}');
      await refresh();
    } catch (exception) {
      if (mounted) setState(() => message = exception.toString());
    }
  }
  Future<void> remove(String id) async {
    try { await widget.api.deleteDocument(id); await refresh(); }
    catch (exception) { if (mounted) setState(() => message = exception.toString()); }
  }
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(18), children: [Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [const Text('DOCUMENT LIBRARY', style: TextStyle(color: Color(0xff71a9ff), letterSpacing: 1.4, fontSize: 11, fontWeight: FontWeight.bold)), Row(children: [IconButton(onPressed: refresh, icon: const Icon(Icons.refresh)), IconButton(onPressed: camera, icon: const Icon(Icons.camera_alt_outlined)), IconButton(onPressed: upload, icon: const Icon(Icons.upload_file))])]), const SizedBox(height: 8), const Text('Evidence store', style: TextStyle(fontSize: 25, fontWeight: FontWeight.w700)), if (message.isNotEmpty) Padding(padding: const EdgeInsets.symmetric(vertical: 12), child: Text(message, style: const TextStyle(color: Colors.white60))), const SizedBox(height: 12), if (documents.isEmpty) const Text('No uploaded documents.'), ...documents.map((document) => Card(child: ListTile(title: Text(document['title']?.toString() ?? ''), subtitle: Text('${document['source']} · ${document['status']} · ${document['chunk_count'] ?? 0} chunks'), leading: Icon(document['status'] == 'quarantined' ? Icons.warning_amber : Icons.description_outlined, color: document['status'] == 'quarantined' ? Colors.orangeAccent : Colors.blueAccent), trailing: IconButton(tooltip: 'Delete document', onPressed: () => remove(document['document_id'].toString()), icon: const Icon(Icons.delete_outline))))) ]);
}

class ResearchPage extends StatefulWidget {
  const ResearchPage({required this.api, super.key});
  final ApiService api;
  @override
  State<ResearchPage> createState() => _ResearchPageState();
}

class _ResearchPageState extends State<ResearchPage> {
  Map<String, dynamic> data = <String, dynamic>{};
  bool loading = false;
  String query = '';

  Future<void> load(Future<Map<String, dynamic>> Function() request) async {
    setState(() => loading = true);
    try { final result = await request(); if (mounted) setState(() => data = result); } catch (exception) { if (mounted) setState(() => data = {'error': exception.toString()}); } finally { if (mounted) setState(() => loading = false); }
  }

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(18), children: [
    const Text('RESEARCH WORKSPACE', style: TextStyle(color: Color(0xff71a9ff), letterSpacing: 1.4, fontSize: 11, fontWeight: FontWeight.bold)),
    const SizedBox(height: 8), const Text('Inspect stored intelligence', style: TextStyle(fontSize: 25, fontWeight: FontWeight.w700)),
    const SizedBox(height: 14),
    TextField(decoration: const InputDecoration(labelText: 'Entity for graph search', border: OutlineInputBorder()), onChanged: (value) => query = value),
    const SizedBox(height: 10),
    Wrap(spacing: 8, runSpacing: 8, children: [
      FilledButton(onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => WorkspacePage(api: widget.api))), child: const Text('Workspaces and notes')),
      OutlinedButton(onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => HistoryPage(api: widget.api))), child: const Text('Answer history')),
      OutlinedButton(onPressed: () => load(widget.api.papers), child: const Text('Papers')),
      OutlinedButton(onPressed: () => load(widget.api.vulnerabilities), child: const Text('Vulnerabilities')),
      OutlinedButton(onPressed: () => load(widget.api.threats), child: const Text('Threats')),
      OutlinedButton(onPressed: () => load(widget.api.timeline), child: const Text('Timeline')),
      OutlinedButton(onPressed: () => load(() => widget.api.graph(query.trim())), child: const Text('Graph')),
      OutlinedButton(onPressed: () => load(widget.api.gapAnalysis), child: const Text('Research gaps')),
      OutlinedButton(onPressed: () => load(widget.api.experiments), child: const Text('Experiments')),
    ]),
    if (loading) const Padding(padding: EdgeInsets.all(18), child: CircularProgressIndicator()),
    if (!loading && data.isNotEmpty) Card(child: Padding(padding: const EdgeInsets.all(12), child: SelectableText(const JsonEncoder.withIndent('  ').convert(data)))),
  ]);
}

class HistoryPage extends StatefulWidget {
  const HistoryPage({required this.api, super.key});
  final ApiService api;
  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage> {
  late Future<Map<String, dynamic>> history = widget.api.history();
  @override
  Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: const Text('Answer history'), actions: [IconButton(onPressed: () => setState(() => history = widget.api.history()), icon: const Icon(Icons.refresh))]), body: FutureBuilder<Map<String, dynamic>>(future: history, builder: (context, snapshot) {
    if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
    if (snapshot.hasError) return Center(child: Text(snapshot.error.toString()));
    final answers = (snapshot.data?['answers'] as List? ?? []).cast<Map>();
    if (answers.isEmpty) return const Center(child: Text('No saved answers. Ask a question to begin.'));
    return ListView(padding: const EdgeInsets.all(18), children: answers.map((answer) => Card(child: ExpansionTile(title: Text(answer['query']?.toString() ?? 'Question'), subtitle: Text(answer['created_at']?.toString() ?? ''), children: [Padding(padding: const EdgeInsets.all(12), child: _AnswerView(result: Map<String, dynamic>.from(answer)))]))).toList());
  }));
}

class SettingsPage extends StatelessWidget {
  const SettingsPage({required this.api, super.key});
  final ApiService api;
  @override
  Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: const Text('Settings')), body: FutureBuilder<Map<String, dynamic>>(future: api.healthDetailed(), builder: (context, snapshot) => ListView(padding: const EdgeInsets.all(18), children: [const Text('Environment and service status', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700)), const SizedBox(height: 12), SelectableText(snapshot.hasData ? const JsonEncoder.withIndent('  ').convert(snapshot.data) : snapshot.hasError ? snapshot.error.toString() : 'Loading…')])));
}
