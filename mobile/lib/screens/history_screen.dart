import 'package:flutter/material.dart';

import '../services/db_service.dart';

/// Чтение истории сеансов из PostgreSQL (последний пункт задания ЛР № 4).
class HistoryScreen extends StatefulWidget {
  final String dbHost;
  const HistoryScreen({super.key, required this.dbHost});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  final _db = DbService();
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() async {
    await _db.connect(host: widget.dbHost);
    return _db.listSessions();
  }

  @override
  void dispose() {
    _db.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('История сеансов')),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('Ошибка: ${snap.error}'));
          }
          final rows = snap.data!;
          if (rows.isEmpty) {
            return const Center(child: Text('Сеансов пока нет'));
          }
          return ListView.separated(
            itemCount: rows.length,
            separatorBuilder: (_, __) => const Divider(height: 1),
            itemBuilder: (context, i) {
              final r = rows[i];
              final isRisk = (r['risk_class'] as int) == 1;
              return ListTile(
                leading: Icon(
                  isRisk ? Icons.warning_amber_rounded : Icons.favorite,
                  color: isRisk ? Colors.red : Colors.green,
                ),
                title: Text('${r['started_at']}'),
                subtitle: Text(
                  'ЧСС ${(r['hr'] as double).toStringAsFixed(0)} уд/мин · '
                  'SDNN ${(r['sdnn'] as double).toStringAsFixed(0)} · '
                  'p=${(r['probability'] as double).toStringAsFixed(2)}',
                ),
                trailing: Text('${r['duration_s']} с'),
              );
            },
          );
        },
      ),
    );
  }
}
