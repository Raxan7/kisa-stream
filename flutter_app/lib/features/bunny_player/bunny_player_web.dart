// Web-only iframe player. Intentionally uses a conditional import to preserve Android builds.
// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:async';
import 'dart:ui_web' as ui_web;
import 'package:flutter/material.dart';

class BunnyPlayer extends StatefulWidget {
  final String url;
  final VoidCallback? onEnded;
  const BunnyPlayer({super.key, required this.url, this.onEnded});
  @override
  State<BunnyPlayer> createState() => _BunnyPlayerState();
}

class _BunnyPlayerState extends State<BunnyPlayer> {
  late final String viewType;
  static int next = 0;
  StreamSubscription<html.Event>? finished;

  @override
  void initState() {
    super.initState();
    viewType = 'kisa-bunny-player-${next++}';
    finished = html.window.on['kisa-bunny-ended'].listen((event) {
      if (!mounted) return;
      if (event is html.CustomEvent && event.detail == viewType) {
        widget.onEnded?.call();
      }
    });
    ui_web.platformViewRegistry.registerViewFactory(viewType, (int viewId) {
      final iframe = html.IFrameElement()
        ..src = widget.url
        ..allow = 'autoplay; encrypted-media; fullscreen; picture-in-picture'
        ..style.border = '0'
        ..style.width = '100%'
        ..style.height = '100%';
      iframe.setAttribute('referrerpolicy', 'strict-origin-when-cross-origin');
      iframe.setAttribute('data-kisa-bunny', viewType);
      iframe.onLoad.listen((_) {
        html.window.dispatchEvent(html.CustomEvent('kisa-bunny-mount', detail: iframe));
      });
      return iframe;
    });
  }

  @override
  void dispose() { finished?.cancel(); super.dispose(); }

  @override
  Widget build(BuildContext context) => HtmlElementView(viewType: viewType);
}
