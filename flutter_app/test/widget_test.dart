import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kisa_stream/core/models.dart';
import 'package:kisa_stream/features/app.dart';
void main(){
  testWidgets('artwork renders title', (tester) async {
    const show=KisaShow(id:'1',title:'Secret Heart',synopsis:'A tale',genre:'Romance',accent:'#FF5577');
    await tester.pumpWidget(const MaterialApp(home:Scaffold(body:Artwork(show:show,height:220))));
    expect(find.text('Secret Heart'),findsOneWidget);
  });
}
