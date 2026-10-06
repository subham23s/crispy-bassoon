import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.cause});

  final String message;
  final int? statusCode;
  final Object? cause;

  @override
  String toString() => message;
}

class ApiService {
  ApiService({
    String? baseUrl,
    FlutterSecureStorage? storage,
    http.Client? client,
    this.onSessionExpired,
  })  : baseUrl = _normalizeBaseUrl(
          baseUrl ??
              const String.fromEnvironment(
                'API_BASE_URL',
                defaultValue: 'http://10.0.2.2:8000',
              ),
        ),
        storage = storage ?? const FlutterSecureStorage(),
        _client = client,
        timeout = _configuredTimeout();

  final String baseUrl;
  final FlutterSecureStorage storage;
  final Duration timeout;
  // Injected clients remain owned by their caller; ordinary requests create
  // and close their own client, preserving the existing connection lifecycle.
  final http.Client? _client;
  void Function()? onSessionExpired;

  static const _configuredTimeoutSeconds = int.fromEnvironment(
    'API_TIMEOUT_SECONDS',
    defaultValue: 20,
  );

  Future<Map<String, dynamic>>? _refreshInFlight;
  bool _sessionExpiryNotified = false;

  static Duration _configuredTimeout() => const Duration(
        seconds: _configuredTimeoutSeconds > 0 ? _configuredTimeoutSeconds : 20,
      );

  static String _normalizeBaseUrl(String value) {
    final candidate = value.trim();
    final parsed = Uri.tryParse(candidate);
    if (candidate.isEmpty ||
        parsed == null ||
        parsed.host.isEmpty ||
        !{'http', 'https'}.contains(parsed.scheme.toLowerCase())) {
      throw ArgumentError.value(
        value,
        'baseUrl',
        'API_BASE_URL must be an absolute http(s) URL',
      );
    }
    return candidate.replaceFirst(RegExp(r'/+$'), '');
  }

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool allowRefresh = true,
    bool authenticated = true,
    bool notifyOnSessionExpiry = true,
    bool clearSessionOnExpiry = true,
  }) async {
    final token = authenticated ? await storage.read(key: 'access_token') : null;
    final headers = <String, String>{'Accept': 'application/json'};
    if (body != null || method.toUpperCase() == 'POST') {
      headers['Content-Type'] = 'application/json';
    }
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }

    final uri = Uri.parse('$baseUrl$path');
    late final http.Response response;
    final client = _client ?? http.Client();
    try {
      switch (method.toUpperCase()) {
        case 'GET':
          response = await client.get(uri, headers: headers).timeout(timeout);
          break;
        case 'POST':
          response = await client
              .post(uri, headers: headers, body: jsonEncode(body ?? {}))
              .timeout(timeout);
          break;
        case 'DELETE':
          response = await client
              .delete(
                uri,
                headers: headers,
                body: body == null ? null : jsonEncode(body),
              )
              .timeout(timeout);
          break;
        default:
          throw ArgumentError.value(method, 'method', 'Unsupported HTTP method');
      }
    } on ApiException {
      rethrow;
    } on TimeoutException catch (exception) {
      throw ApiException(
        'The API request timed out. Check the backend URL and network.',
        cause: exception,
      );
    } catch (exception) {
      throw ApiException(
        'Unable to reach the API. Check API_BASE_URL and the backend status.',
        cause: exception,
      );
    } finally {
      if (_client == null) client.close();
    }

    final decoded = _decodeBody(response);
    if (response.statusCode == 401 &&
        authenticated &&
        allowRefresh &&
        path != '/auth/refresh') {
      final refreshToken = await storage.read(key: 'refresh_token');
      if (refreshToken != null && refreshToken.isNotEmpty) {
        try {
          await _refreshSession();
        } catch (exception) {
          if (clearSessionOnExpiry) {
            await _clearSession(notify: notifyOnSessionExpiry);
          }
          throw ApiException(
            'Your session has expired. Please sign in again.',
            statusCode: 401,
            cause: exception,
          );
        }
        // A successfully refreshed session must survive a subsequent 403,
        // validation failure, or network error from the original operation.
        return _request(
          method,
          path,
          body: body,
          allowRefresh: false,
          authenticated: authenticated,
          notifyOnSessionExpiry: notifyOnSessionExpiry,
          clearSessionOnExpiry: clearSessionOnExpiry,
        );
      }
    }

    if (response.statusCode == 401 && authenticated) {
      if (clearSessionOnExpiry) {
        await _clearSession(notify: notifyOnSessionExpiry);
      }
      throw const ApiException(
        'Your session has expired. Please sign in again.',
        statusCode: 401,
      );
    }
    if (response.statusCode >= 400) {
      throw ApiException(
        _errorMessage(decoded, response.statusCode),
        statusCode: response.statusCode,
      );
    }
    return decoded;
  }

  static Map<String, dynamic> _decodeBody(http.Response response) {
    final raw = response.body.trim();
    if (raw.isEmpty) return <String, dynamic>{};
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) return decoded;
      if (decoded is Map) return Map<String, dynamic>.from(decoded);
      return <String, dynamic>{'data': decoded};
    } on FormatException {
      return <String, dynamic>{};
    }
  }

  static String _errorMessage(Map<String, dynamic> body, int statusCode) {
    final detail = body['detail'];
    if (detail is String && detail.trim().isNotEmpty) return detail;
    if (detail is Map && detail['message'] is String) {
      return detail['message'] as String;
    }
    return 'Request failed ($statusCode)';
  }

  Future<Map<String, dynamic>> _refreshSession() async {
    final running = _refreshInFlight;
    if (running != null) return running;

    final future = _performRefresh();
    _refreshInFlight = future;
    try {
      return await future;
    } finally {
      if (identical(_refreshInFlight, future)) _refreshInFlight = null;
    }
  }

  Future<Map<String, dynamic>> _performRefresh() async {
    final refreshToken = await storage.read(key: 'refresh_token');
    if (refreshToken == null || refreshToken.isEmpty) {
      throw const ApiException('No refresh token is available.', statusCode: 401);
    }
    final refreshed = await _request(
      'POST',
      '/auth/refresh',
      body: {'refresh_token': refreshToken},
      allowRefresh: false,
      authenticated: false,
    );
    await saveSession(refreshed);
    return refreshed;
  }

  void _notifySessionExpired() {
    if (_sessionExpiryNotified) return;
    _sessionExpiryNotified = true;
    onSessionExpired?.call();
  }

  Future<void> _clearSession({required bool notify}) async {
    await Future.wait([
      storage.delete(key: 'access_token'),
      storage.delete(key: 'refresh_token'),
    ]);
    if (notify) _notifySessionExpired();
  }

  Future<Map<String, dynamic>> register(String email, String password) async {
    final result = await _request(
      'POST',
      '/auth/register',
      body: {'email': email, 'password': password},
      authenticated: false,
    );
    await saveSession(result);
    return result;
  }

  Future<Map<String, dynamic>> login(String email, String password) async {
    final result = await _request(
      'POST',
      '/auth/login',
      body: {'email': email, 'password': password},
      authenticated: false,
    );
    await saveSession(result);
    return result;
  }

  Future<bool> restoreSession() async {
    final accessToken = await storage.read(key: 'access_token');
    final refreshToken = await storage.read(key: 'refresh_token');
    if (accessToken == null || accessToken.isEmpty) return false;
    if (refreshToken == null || refreshToken.isEmpty) {
      await _clearSession(notify: false);
      return false;
    }
    try {
      await _request(
        'GET',
        '/auth/me',
        notifyOnSessionExpiry: false,
      );
      return true;
    } catch (_) {
      await _clearSession(notify: false);
      return false;
    }
  }

  Future<Map<String, dynamic>> health() =>
      _request('GET', '/health', authenticated: false);

  Future<Map<String, dynamic>> healthDetailed() =>
      _request('GET', '/health/detailed', authenticated: false);

  Future<Map<String, dynamic>> me() => _request('GET', '/auth/me');

  Future<Map<String, dynamic>> ask(String query, String mode, {String? workspaceId}) => _request(
        'POST',
        '/chat/query',
        body: {'query': query, 'mode': mode, if (workspaceId != null) 'workspace_id': workspaceId},
      );

  Future<Map<String, dynamic>> askStream(
    String query,
    String mode, {
    void Function(String stage)? onStage,
    void Function(String text)? onDelta,
    void Function()? onReset,
    bool retried = false,
  }) async {
    final token = await storage.read(key: 'access_token');
    final request = http.Request('POST', Uri.parse('$baseUrl/chat/stream'))
      ..headers.addAll({
        'Accept': 'text/event-stream',
        'Content-Type': 'application/json',
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
      })
      ..body = jsonEncode({'query': query, 'mode': mode});
    final streamed = await (_client?.send(request) ?? request.send()).timeout(timeout);
    if (streamed.statusCode == 401) {
      await streamed.stream.drain<void>();
      if (retried) {
        await _clearSession(notify: true);
        throw const ApiException('Your session has expired. Please sign in again.', statusCode: 401);
      }
      try { await _refreshSession(); }
      catch (_) { await _clearSession(notify: true); rethrow; }
      return askStream(query, mode, onStage: onStage, onDelta: onDelta, onReset: onReset, retried: true);
    }
    if (streamed.statusCode >= 400) {
      await streamed.stream.drain<void>();
      throw ApiException('Streaming request failed (${streamed.statusCode})', statusCode: streamed.statusCode);
    }
    final lines = streamed.stream.transform(utf8.decoder).transform(const LineSplitter()).timeout(const Duration(minutes: 3));
    String event = 'message';
    final dataLines = <String>[];
    Map<String, dynamic>? completed;
    await for (final line in lines) {
      if (line.startsWith('event:')) {
        event = line.substring(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.add(line.substring(5).trimLeft());
      } else if (line.isEmpty && dataLines.isNotEmpty) {
        final payload = jsonDecode(dataLines.join('\n'));
        dataLines.clear();
        if (payload is! Map) continue;
        final data = Map<String, dynamic>.from(payload);
        if (event == 'error') throw ApiException(data['detail']?.toString() ?? 'Streaming query failed');
        if (event == 'status') onStage?.call(data['stage']?.toString() ?? 'STATUS');
        if (event == 'answer_delta') onDelta?.call(data['text']?.toString() ?? '');
        if (event == 'answer_reset') onReset?.call();
        if (event == 'complete' && data['answer'] is Map) {
          completed = Map<String, dynamic>.from(data['answer'] as Map);
          break;
        }
        event = 'message';
      }
    }
    if (completed == null) throw const ApiException('The stream ended before verification completed. Please retry.');
    return completed;
  }

  Future<Map<String, dynamic>> analyzeLog(String content) =>
      _request('POST', '/logs/analyze', body: {'content': content});

  Future<Map<String, dynamic>> analyzeIoc(String content) =>
      _request('POST', '/ioc/analyze', body: {'content': content});

  Future<Map<String, dynamic>> documents() => _request('GET', '/documents');
  Future<Map<String, dynamic>> deleteDocument(String id) => _request('DELETE', '/documents/${Uri.encodeComponent(id)}');

  Future<Map<String, dynamic>> gapAnalysis() =>
      _request('POST', '/research/gap-analysis', body: {});

  Future<Map<String, dynamic>> papers() => _request('GET', '/papers');
  Future<Map<String, dynamic>> vulnerabilities() => _request('GET', '/vulnerabilities');
  Future<Map<String, dynamic>> threats() => _request('GET', '/threats');
  Future<Map<String, dynamic>> timeline() => _request('GET', '/timeline');
  Future<Map<String, dynamic>> graph(String query) => _request('GET', '/graph/search/${Uri.encodeComponent(query)}');
  Future<Map<String, dynamic>> evaluation() => _request('GET', '/evaluation');
  Future<Map<String, dynamic>> ragSecurityEvaluation() => _request('GET', '/rag-security/evaluate');
  Future<Map<String, dynamic>> workspaces() => _request('GET', '/research/workspaces');
  Future<Map<String, dynamic>> createWorkspace(String name) => _request('POST', '/research/workspaces', body: {'name': name});
  Future<Map<String, dynamic>> workspaceItems(String id) => _request('GET', '/research/workspaces/${Uri.encodeComponent(id)}/items');
  Future<Map<String, dynamic>> workspaceNotes(String id) => _request('GET', '/research/workspaces/${Uri.encodeComponent(id)}/notes');
  Future<Map<String, dynamic>> workspaceEvidence(String id) => _request('GET', '/research/workspaces/${Uri.encodeComponent(id)}/evidence');
  Future<Map<String, dynamic>> saveEvidence(String id, String chunkId) => _request('POST', '/research/workspaces/${Uri.encodeComponent(id)}/evidence', body: {'evidence_id': chunkId});
  Future<Map<String, dynamic>> createNote(String id, String body) => _request('POST', '/research/workspaces/${Uri.encodeComponent(id)}/notes', body: {'body': body});
  Future<Map<String, dynamic>> history() => _request('GET', '/chat/history');
  Future<Map<String, dynamic>> exportAnswer(String answerId, String format) => _request('POST', '/reports/export', body: {'answer_id': answerId, 'format': format});
  Future<Map<String, dynamic>> comparePapers(List<String> ids) => _request('POST', '/papers/compare', body: {'document_ids': ids});
  Future<Map<String, dynamic>> experiments() => _request('GET', '/experiments');
  Future<Map<String, dynamic>> compareExperiments() => _request('GET', '/experiments/compare');
  Future<Map<String, dynamic>> adminOverview() => _request('GET', '/admin/overview');

  Future<Map<String, dynamic>> upload(String filename, Uint8List bytes, {bool background = false, String sourceType = 'user_document'}) =>
      _request(
        'POST',
        '/documents/upload',
        body: {
          'filename': filename,
          'content_base64': base64Encode(bytes),
          'background': background,
          'source_type': sourceType,
        },
      );

  Future<Map<String, dynamic>> waitForUpload(Map<String, dynamic> result, {void Function(String)? onStatus}) async {
    final job = result['job'];
    if (job is! Map || job['job_id'] == null) return result;
    for (var attempt = 0; attempt < 300; attempt++) {
      final value = await _request('GET', '/documents/jobs/${Uri.encodeComponent(job['job_id'].toString())}');
      final current = Map<String, dynamic>.from(value['job'] as Map);
      onStatus?.call(current['status']?.toString() ?? 'QUEUED');
      if (current['status'] == 'FAILED') throw ApiException(current['error']?.toString() ?? 'Processing failed');
      if (current['status'] == 'COMPLETED') return {...result, 'status': current['document_status'], 'job': current};
      await Future<void>.delayed(const Duration(seconds: 1));
    }
    throw const ApiException('Processing is still pending. Check the library again later.');
  }

  Future<void> saveSession(Map<String, dynamic> session) async {
    final accessToken = session['access_token'];
    final refreshToken = session['refresh_token'];
    if (accessToken is! String || accessToken.isEmpty) {
      throw const ApiException('The API returned an invalid access token.');
    }
    if (refreshToken is! String || refreshToken.isEmpty) {
      throw const ApiException('The API returned an invalid refresh token.');
    }
    await storage.write(key: 'access_token', value: accessToken);
    await storage.write(key: 'refresh_token', value: refreshToken);
    _sessionExpiryNotified = false;
  }

  Future<void> logout() async {
    final refreshToken = await storage.read(key: 'refresh_token');
    try {
      if (refreshToken != null && refreshToken.isNotEmpty) {
        try {
          // Do not auto-refresh this request with the old refresh token. If the
          // access token expired, the fallback below rotates and revokes the
          // replacement token instead of leaving it active on the server.
          await _request(
            'POST',
            '/auth/logout',
            body: {'refresh_token': refreshToken},
            allowRefresh: false,
            notifyOnSessionExpiry: false,
            clearSessionOnExpiry: false,
          );
        } on ApiException catch (exception) {
          if (exception.statusCode != 401) rethrow;
          try {
            final refreshed = await _refreshSession();
            final rotatedRefreshToken = refreshed['refresh_token'];
            if (rotatedRefreshToken is String && rotatedRefreshToken.isNotEmpty) {
              await _request(
                'POST',
                '/auth/logout',
                body: {'refresh_token': rotatedRefreshToken},
                allowRefresh: false,
                notifyOnSessionExpiry: false,
                clearSessionOnExpiry: false,
              );
            }
          } catch (_) {}
        }
      }
    } finally {
      await _clearSession(notify: false);
    }
  }
}
