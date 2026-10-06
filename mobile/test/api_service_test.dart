import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cybersecra_x_mobile/services/api_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('a forbidden retried request preserves the refreshed session', () async {
    FlutterSecureStorage.setMockInitialValues({
      'access_token': 'expired-token',
      'refresh_token': 'refresh-token',
    });
    var refreshes = 0;
    final client = MockClient((request) async {
      if (request.url.path == '/auth/refresh') {
        refreshes++;
        return http.Response(jsonEncode({
          'access_token': 'fresh-token',
          'refresh_token': 'rotated-token',
        }), 200);
      }
      if (request.headers['Authorization'] == 'Bearer expired-token') {
        return http.Response('{"detail":"Expired"}', 401);
      }
      return http.Response('{"detail":"Forbidden"}', 403);
    });
    addTearDown(client.close);
    var expiredNotifications = 0;
    final api = ApiService(
      baseUrl: 'https://api.example.test',
      client: client,
      onSessionExpired: () => expiredNotifications++,
    );
    await expectLater(api.documents(), throwsA(isA<ApiException>().having((error) => error.statusCode, 'status', 403)));
    expect(refreshes, 1);
    expect(expiredNotifications, 0);
    expect(await api.storage.read(key: 'access_token'), 'fresh-token');
    expect(await api.storage.read(key: 'refresh_token'), 'rotated-token');
  });

  test('normalizes a configured API base URL', () {
    final api = ApiService(baseUrl: 'https://api.example.test///');

    expect(api.baseUrl, 'https://api.example.test');
  });

  test('rejects an API base URL without an HTTP scheme', () {
    expect(
      () => ApiService(baseUrl: 'api.example.test'),
      throwsArgumentError,
    );
  });

  test('exposes API errors without leaking implementation wording', () {
    const error = ApiException('Authentication required', statusCode: 401);

    expect(error.toString(), 'Authentication required');
    expect(error.statusCode, 401);
  });
}
