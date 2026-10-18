import 'dart:convert';
import 'dart:typed_data';

import 'package:postgres/postgres.dart';

import '../models/reading.dart';
import 'crypto_service.dart';

/// Прямое подключение Flutter-приложения к PostgreSQL (ЛР № 4): приём
/// обработанных данных сеанса -> шифрование -> запись -> чтение истории.
/// Схема — db/init.sql, та же ER-диаграмма, что в отчёте по ЛР № 1.
///
/// ВАЖНО (честное ограничение, см. отчёт): логин/пароль к БД ниже
/// захардкожены и подключение идёт без TLS — нормально для учебного
/// стенда в одной локальной сети, но не для продакшена. Там же отмечено,
/// почему raw_signals хранит не сырые отсчёты ФПГ, а зашифрованный ряд
/// ЧСС по окнам сеанса: устройство (ЛР № 3) отдаёт в поток уже
/// обработанный результат, сырых отсчётов на клиенте просто нет.
class DbService {
  Connection? _conn;

  Future<void> connect({
    required String host,
    int port = 5432,
    String database = 'cardiowatch',
    String username = 'cardiowatch',
    String password = 'cardiowatch',
  }) async {
    _conn = await Connection.open(
      Endpoint(
        host: host,
        port: port,
        database: database,
        username: username,
        password: password,
      ),
      settings: const ConnectionSettings(sslMode: SslMode.disable), // локальный docker без TLS, см. предупреждение выше
    );
  }

  bool get isConnected => _conn != null && _conn!.isOpen;

  /// Гарантирует существование пользователя с id=1 — в приложении нет
  /// экрана авторизации (сознательно упрощено), все сеансы пишутся от
  /// имени одного демо-пользователя.
  Future<int> ensureDemoUser() async {
    final conn = _conn!;
    final existing = await conn.execute(Sql.named('SELECT user_id FROM users WHERE user_id = 1'));
    if (existing.isNotEmpty) return 1;
    final enc = await CryptoService.encryptJson({'name': 'Демо-пользователь'});
    await conn.execute(
      Sql.named('INSERT INTO users (user_id, full_name_enc, birth_year) '
          'VALUES (1, @name, NULL)'),
      parameters: {'name': enc.dataEnc},
    );
    return 1;
  }

  /// Сохраняет сеанс целиком: метаданные (sessions), зашифрованный ряд
  /// ЧСС (raw_signals), усреднённые признаки (features) и решение
  /// нейросети (predictions) — пункты 4-8 задания ЛР № 4.
  Future<int> saveSession(List<Reading> history, {int fsHz = 100}) async {
    if (history.isEmpty) {
      throw ArgumentError('Нечего сохранять — список окон пуст');
    }
    final conn = _conn!;
    final userId = await ensureDemoUser();

    return conn.runTx((tx) async {
      final durationS = history.last.t.round() + 8; // + длительность последнего окна

      final sessionRow = await tx.execute(
        Sql.named('INSERT INTO sessions (user_id, duration_s, fs_hz) '
            'VALUES (@uid, @dur, @fs) RETURNING session_id'),
        parameters: {'uid': userId, 'dur': durationS, 'fs': fsHz},
      );
      final sessionId = sessionRow.first.toColumnMap()['session_id'] as int;

      // "Сырые данные" сеанса: у клиента нет сырого ФПГ (устройство шлёт
      // уже обработанный результат, см. предупреждение в начале файла),
      // поэтому шифруем и сохраняем сам ряд (t, ЧСС) по окнам сеанса.
      final series = history.map((r) => {'t': r.t, 'hr': r.hrSmoothed}).toList();
      final enc = await CryptoService.encrypt(
        Uint8List.fromList(utf8.encode(jsonEncode(series))),
      );
      await tx.execute(
        Sql.named('INSERT INTO raw_signals (session_id, data_enc, nonce, tag) '
            'VALUES (@sid, @data, @nonce, @tag)'),
        parameters: {'sid': sessionId, 'data': enc.dataEnc, 'nonce': enc.nonce, 'tag': enc.tag},
      );

      // Признаки — средние по всем окнам сеанса.
      final n = history.length;
      final avgHr = history.map((r) => r.hr).reduce((a, b) => a + b) / n;
      final avgSdnn = history.map((r) => r.sdnn).reduce((a, b) => a + b) / n;
      final avgRmssd = history.map((r) => r.rmssd).reduce((a, b) => a + b) / n;
      final avgPnn50 = history.map((r) => r.pnn50).reduce((a, b) => a + b) / n;
      await tx.execute(
        Sql.named('INSERT INTO features (session_id, hr, sdnn, rmssd, pnn50) '
            'VALUES (@sid, @hr, @sdnn, @rmssd, @pnn50)'),
        parameters: {'sid': sessionId, 'hr': avgHr, 'sdnn': avgSdnn, 'rmssd': avgRmssd, 'pnn50': avgPnn50},
      );

      // Решение по сеансу — средняя вероятность риска по всем окнам.
      final avgProb = history.map((r) => r.riskProb).reduce((a, b) => a + b) / n;
      await tx.execute(
        Sql.named('INSERT INTO predictions (session_id, risk_class, probability, model_version) '
            'VALUES (@sid, @cls, @prob, @ver)'),
        parameters: {
          'sid': sessionId,
          'cls': avgProb >= 0.5 ? 1 : 0,
          'prob': avgProb,
          'ver': 'risknet-mlp-4-8-1-v1',
        },
      );

      return sessionId;
    });
  }

  /// Список прошлых сеансов для экрана истории (без сырых данных —
  /// их расшифровка нужна только при открытии конкретного сеанса).
  Future<List<Map<String, dynamic>>> listSessions() async {
    final conn = _conn!;
    final result = await conn.execute(Sql.named(
      'SELECT s.session_id, s.started_at, s.duration_s, '
      'f.hr, f.sdnn, f.rmssd, f.pnn50, p.risk_class, p.probability '
      'FROM sessions s '
      'JOIN features f ON f.session_id = s.session_id '
      'JOIN predictions p ON p.session_id = s.session_id '
      'ORDER BY s.started_at DESC',
    ));
    return result.map((row) => row.toColumnMap()).toList();
  }

  Future<void> close() async {
    await _conn?.close();
    _conn = null;
  }
}
