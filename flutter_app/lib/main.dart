import 'package:flutter/material.dart';
import 'core/api.dart';
import 'core/store.dart';
import 'features/app.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(KisaApp(store:KisaStore(KisaApi())));
}

class KisaApp extends StatefulWidget {
  final KisaStore store;
  const KisaApp({super.key,required this.store});
  @override
  State<KisaApp> createState()=>_KisaAppState();
}
class _KisaAppState extends State<KisaApp> {
  @override
  void initState(){super.initState();widget.store.initialize();}
  @override
  void dispose(){widget.store.dispose();super.dispose();}
  @override
  Widget build(BuildContext context) => MaterialApp(
    title:'KISA',debugShowCheckedModeBanner:false,
    theme:ThemeData(useMaterial3:true,brightness:Brightness.dark,
      scaffoldBackgroundColor:const Color(0xFF100F19),
      colorScheme:ColorScheme.fromSeed(seedColor:const Color(0xFFFF527B),brightness:Brightness.dark),
      fontFamily:'Roboto',
      appBarTheme:const AppBarTheme(backgroundColor:Color(0xFF100F19),surfaceTintColor:Colors.transparent),
      snackBarTheme:const SnackBarThemeData(behavior:SnackBarBehavior.floating),
      filledButtonTheme:FilledButtonThemeData(style:FilledButton.styleFrom(
        backgroundColor:const Color(0xFFFF527B),foregroundColor:Colors.white,
        padding:const EdgeInsets.symmetric(horizontal:20,vertical:15),
        shape:RoundedRectangleBorder(borderRadius:BorderRadius.circular(16))))),
    home:KisaRoot(store:widget.store));
}
