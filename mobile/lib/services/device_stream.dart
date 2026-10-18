import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/reading.dart';

/// Подключение к устройству CardioWatch (контейнер Docker, ЛР № 3) по
/// WebSocket. Хранит всю историю сеанса в памяти (для графика) и
/// уведомляет экран о каждом новом результате через ChangeNotifier —
/// этого достаточно для одного экрана "в реальном времени", без Riverpod
/// или Bloc (см. обсуждение выбора state management в отчёте).
class DeviceStream extends ChangeNotifier {
  WebSocketChannel? _channel;
  StreamSubscription? _sub;

  final List<Reading> history = []; // все окна текущего сеанса, по порядку
  bool get isConnected => _channel != null;
  String? lastError;

  /// uri, например: ws://10.0.2.2:8765 (эмулятор Android) или
  /// ws://192.168.1.50:8765 (физический телефон в той же сети, что Docker).
  Future<void> connect(String uri) async {
    disconnect(); // на случай повторного подключения — сначала закрываем старое
    lastError = null;
    history.clear();
    try {
      _channel = WebSocketChannel.connect(Uri.parse(uri));
      _sub = _channel!.stream.listen(
        _onMessage,
        onError: (e) {
          lastError = 'Ошибка соединения: $e';
          notifyListeners();
        },
        onDone: () {
          _channel = null;
          notifyListeners();
        },
      );
      notifyListeners();
    } catch (e) {
      lastError = 'Не удалось подключиться: $e';
      _channel = null;
      notifyListeners();
    }
  }

  void _onMessage(dynamic raw) {
    final json = jsonDecode(raw as String) as Map<String, dynamic>;
    history.add(Reading.fromJson(json));
    notifyListeners(); // перерисовать график и бейдж риска
  }

  Reading? get last => history.isEmpty ? null : history.last;

  void disconnect() {
    _sub?.cancel();
    _channel?.sink.close();
    _channel = null;
    _sub = null;
  }

  @override
  void dispose() {
    disconnect();
    super.dispose();
  }
}
