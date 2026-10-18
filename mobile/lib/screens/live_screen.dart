import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:provider/provider.dart';

import '../models/reading.dart';
import '../services/device_stream.dart';
import '../services/db_service.dart';
import 'history_screen.dart';

class LiveScreen extends StatefulWidget {
  const LiveScreen({super.key});

  @override
  State<LiveScreen> createState() => _LiveScreenState();
}

class _LiveScreenState extends State<LiveScreen> {
  // Значения по умолчанию рассчитаны на эмулятор Android (10.0.2.2 — это
  // "localhost хоста" с точки зрения эмулятора); для физического телефона
  // нужно подставить реальный IP компьютера с Docker в локальной сети.
  final _deviceUriCtrl = TextEditingController(text: 'ws://10.0.2.2:8765');
  final _dbHostCtrl = TextEditingController(text: '10.0.2.2');
  final _db = DbService();
  bool _saving = false;

  @override
  void dispose() {
    _deviceUriCtrl.dispose();
    _dbHostCtrl.dispose();
    _db.close();
    super.dispose();
  }

  Future<void> _saveSession(DeviceStream stream) async {
    if (stream.history.isEmpty) return;
    setState(() => _saving = true);
    try {
      if (!_db.isConnected) {
        await _db.connect(host: _dbHostCtrl.text.trim());
      }
      final id = await _db.saveSession(stream.history);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Сеанс №$id сохранён')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Не удалось сохранить: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final stream = context.watch<DeviceStream>();
    final last = stream.last;

    return Scaffold(
      appBar: AppBar(
        title: const Text('CardioWatch'),
        actions: [
          IconButton(
            icon: const Icon(Icons.history),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => HistoryScreen(dbHost: _dbHostCtrl.text.trim())),
            ),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (!stream.isConnected) ...[
              TextField(
                controller: _deviceUriCtrl,
                decoration: const InputDecoration(labelText: 'Адрес устройства (WebSocket)'),
              ),
              TextField(
                controller: _dbHostCtrl,
                decoration: const InputDecoration(labelText: 'Адрес БД (хост)'),
              ),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => stream.connect(_deviceUriCtrl.text.trim()),
                child: const Text('Подключиться'),
              ),
              if (stream.lastError != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(stream.lastError!, style: const TextStyle(color: Colors.red)),
                ),
            ] else ...[
              _RiskBadge(last: last),
              const SizedBox(height: 12),
              Expanded(child: _HrChart(history: stream.history)),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: stream.disconnect,
                      child: const Text('Отключиться'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: _saving ? null : () => _saveSession(stream),
                      child: _saving
                          ? const SizedBox(
                              height: 18, width: 18,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Text('Сохранить сеанс'),
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _RiskBadge extends StatelessWidget {
  final Reading? last;
  const _RiskBadge({required this.last});

  @override
  Widget build(BuildContext context) {
    final reading = last;
    if (reading == null) {
      return const Text('Ожидание первого окна анализа (8 с)…');
    }
    final isRisk = reading.isRisk;
    final color = isRisk ? Colors.red : Colors.green;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
      decoration: BoxDecoration(color: color.withOpacity(0.12), borderRadius: BorderRadius.circular(12)),
      child: Row(
        children: [
          Icon(isRisk ? Icons.warning_amber_rounded : Icons.favorite, color: color),
          const SizedBox(width: 12),
          Text(
            '${isRisk ? "Повышенный риск" : "Норма"} · ЧСС ${reading.hrSmoothed.toStringAsFixed(0)} уд/мин '
            '(p=${reading.riskProb.toStringAsFixed(2)})',
            style: TextStyle(color: color, fontWeight: FontWeight.bold),
          ),
        ],
      ),
    );
  }
}

class _HrChart extends StatelessWidget {
  final List<Reading> history;
  const _HrChart({required this.history});

  @override
  Widget build(BuildContext context) {
    if (history.isEmpty) {
      return const Center(child: Text('Нет данных'));
    }
    final spots = [for (final r in history) FlSpot(r.t, r.hrSmoothed)];
    return LineChart(
      LineChartData(
        minY: 40, maxY: 160,
        titlesData: const FlTitlesData(
          topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: Colors.teal,
            barWidth: 2,
            dotData: const FlDotData(show: false),
          ),
        ],
      ),
    );
  }
}
