import 'dart:convert';
import 'dart:async';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter/foundation.dart' show kDebugMode;

const apiBaseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000');
const billingMode = String.fromEnvironment('BILLING_MODE', defaultValue: 'play');
const productId = String.fromEnvironment('PLAY_PRODUCT_ID', defaultValue: 'coins_30_tzs_1000');

class ApiError implements Exception {
  final int status;
  final String message;
  const ApiError(this.status, this.message);
  @override
  String toString() => message;
}

class KisaApi {
  final http.Client client;
  final FlutterSecureStorage storage;
  String? token;
  KisaApi({http.Client? client, FlutterSecureStorage? storage})
      : client = client ?? http.Client(), storage = storage ?? const FlutterSecureStorage();

  Future<void> initialize() async {
    token = await storage.read(key: 'kisa_access_token');
    if (token != null) {
      try {
        await get('/v1/me');
        return;
      } on ApiError catch (e) {
        if (e.status != 401) rethrow;
        await storage.delete(key: 'kisa_access_token');
      }
    }
    final response = await post('/v1/auth/guest', {});
    token = response['access_token'] as String;
    await storage.write(key: 'kisa_access_token', value: token);
  }

  Future<void> saveAccessToken(String accessToken) async {
    token = accessToken;
    await storage.write(key: 'kisa_access_token', value: accessToken);
  }

  Future<Map<String, dynamic>> get(String path) => _send('GET', path);
  Future<Map<String, dynamic>> post(String path, [Map<String, dynamic> data = const {}]) => _send('POST', path, data);

  Future<Map<String, dynamic>> _send(String method, String path, [Map<String, dynamic>? data]) async {
    final base = Uri.tryParse(apiBaseUrl);
    final local = base != null &&
        (base.host == 'localhost' || base.host == '127.0.0.1' || base.host == '10.0.2.2');
    if (base == null || !base.hasAuthority ||
        (base.scheme != 'https' && !(base.scheme == 'http' && local))) {
      throw const ApiError(0, 'API_BASE_URL must use HTTPS (local development hosts may use HTTP).');
    }
    try {
      final uri = Uri.parse('$apiBaseUrl$path');
      final headers = <String, String>{'Accept': 'application/json', 'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token'};
      final response = await (method == 'POST'
          ? client.post(uri, headers: headers, body: jsonEncode(data ?? {}))
          : client.get(uri, headers: headers)).timeout(const Duration(seconds: 15));
      final dynamic decoded;
      try {
        decoded = jsonDecode(response.body);
      } on FormatException {
        throw ApiError(response.statusCode, 'API response was not JSON ($path, HTTP ${response.statusCode}). Check the backend URL.');
      }
      final result = decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
      if (response.statusCode >= 400) {
        final detail = result['detail'];
        String msg;
        if (detail is Map) {
          msg = (detail['code'] ?? detail['message'] ?? 'Request failed').toString();
        } else {
          msg = (detail ?? 'Request failed (${response.statusCode})').toString();
        }
        throw ApiError(response.statusCode, msg);
      }
      return result;
    } on ApiError {
      rethrow;
    } on TimeoutException {
      throw ApiError(0, 'API timed out: $apiBaseUrl. Check that the backend is running on port 8000.');
    } on http.ClientException catch (e) {
      final detail = kDebugMode ? ' (${e.message})' : '';
      throw ApiError(0,
          'Cannot reach $apiBaseUrl$detail. Verify the backend and allow the web origin in CORS.');
    } catch (e) {
      final detail = kDebugMode ? ': $e' : '';
      throw ApiError(0, 'Request to $apiBaseUrl failed$detail');
    }
  }

  void close() => client.close();
}
