import 'package:flutter/material.dart';

class BunnyPlayer extends StatelessWidget {
  final String url;
  final VoidCallback? onEnded;
  const BunnyPlayer({super.key, required this.url, this.onEnded});
  @override
  Widget build(BuildContext context) => const Center(
    child: Text('Bunny native player will be enabled in the Android release.',
      textAlign: TextAlign.center),
  );
}
