/// Один результат анализа одного окна (8 с), как его шлёт
/// cardiowatch.signal_service внутри Docker-контейнера (см. docstring
/// в cardiowatch/signal_service.py — формат сообщения описан там же).
class Reading {
  final double t; // время начала окна от старта сеанса, с
  final double hr; // ЧСС по этому окну, уд/мин
  final double hrSmoothed; // ЧСС, сглаженная адаптивной EMA (KAMA, ЛР № 2)
  final double sdnn;
  final double rmssd;
  final double pnn50;
  final double riskProb; // вероятность класса "повышенный риск" (нейросеть, ЛР № 3)
  final int riskClass; // 0 - норма, 1 - повышенный риск

  const Reading({
    required this.t,
    required this.hr,
    required this.hrSmoothed,
    required this.sdnn,
    required this.rmssd,
    required this.pnn50,
    required this.riskProb,
    required this.riskClass,
  });

  /// Разбор одного JSON-сообщения от WebSocket устройства.
  factory Reading.fromJson(Map<String, dynamic> j) {
    return Reading(
      t: (j['t'] as num).toDouble(),
      hr: (j['hr'] as num).toDouble(),
      hrSmoothed: (j['hr_smoothed'] as num).toDouble(),
      sdnn: (j['sdnn'] as num).toDouble(),
      rmssd: (j['rmssd'] as num).toDouble(),
      pnn50: (j['pnn50'] as num).toDouble(),
      riskProb: (j['risk_prob'] as num).toDouble(),
      riskClass: j['risk_class'] as int,
    );
  }

  bool get isRisk => riskClass == 1;
}
