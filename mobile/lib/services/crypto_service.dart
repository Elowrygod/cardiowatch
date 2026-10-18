import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';

/// Шифрование данных на стороне приложения перед записью в БД —
/// тот же алгоритм AES-256-GCM, что заложен в ER-схему ЛР № 1
/// (db/init.sql: data_enc + nonce + tag). Ключ хранится только в
/// приложении и никогда не попадает на сервер БД — это и есть ответ
/// на вопрос "как защищены данные" из задания ЛР № 4.
///
/// ВАЖНО (учебное упрощение, честно отмечено и в отчёте): ключ сейчас
/// зашит в код константой. Для реального приложения его нужно
/// генерировать на устройстве при первом запуске и хранить в
/// защищённом хранилище (пакет flutter_secure_storage), а не в коде.
class CryptoService {
  static final _algorithm = AesGcm.with256bits();

  // 32 байта = 256 бит. Только для учебного стенда, см. предупреждение выше.
  static final SecretKey _demoKey = SecretKey(
    List<int>.generate(32, (i) => i), // 0,1,2,...,31 — детерминированный учебный ключ
  );

  /// Шифрует произвольные байты (например, отсчёты сигнала или JSON
  /// с признаками сеанса). Возвращает три части для трёх колонок БД:
  /// data_enc, nonce, tag — ровно как в db/init.sql.
  static Future<({Uint8List dataEnc, Uint8List nonce, Uint8List tag})> encrypt(
    Uint8List plainBytes,
  ) async {
    final box = await _algorithm.encrypt(plainBytes, secretKey: _demoKey);
    return (
      dataEnc: Uint8List.fromList(box.cipherText),
      nonce: Uint8List.fromList(box.nonce), // 12 байт
      tag: Uint8List.fromList(box.mac.bytes), // 16 байт, тег аутентичности GCM
    );
  }

  static Future<Uint8List> decrypt({
    required Uint8List dataEnc,
    required Uint8List nonce,
    required Uint8List tag,
  }) async {
    final box = SecretBox(dataEnc, nonce: nonce, mac: Mac(tag));
    final plain = await _algorithm.decrypt(box, secretKey: _demoKey);
    return Uint8List.fromList(plain);
  }

  /// Удобный хелпер: зашифровать JSON-объект (например, признаки сеанса).
  static Future<({Uint8List dataEnc, Uint8List nonce, Uint8List tag})> encryptJson(
    Map<String, dynamic> obj,
  ) {
    return encrypt(Uint8List.fromList(utf8.encode(jsonEncode(obj))));
  }
}
