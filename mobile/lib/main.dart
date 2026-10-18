import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'services/device_stream.dart';
import 'screens/live_screen.dart';

void main() {
  runApp(const CardioWatchApp());
}

class CardioWatchApp extends StatelessWidget {
  const CardioWatchApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => DeviceStream(),
      child: MaterialApp(
        title: 'CardioWatch',
        theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
        home: const LiveScreen(),
      ),
    );
  }
}
