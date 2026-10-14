import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import 'package:flutter/foundation.dart' show kIsWeb;
import 'bunny_player/bunny_player.dart';
import 'package:video_player/video_player.dart';
import 'package:in_app_purchase/in_app_purchase.dart';
import 'package:in_app_purchase_android/in_app_purchase_android.dart';
import 'package:url_launcher/url_launcher.dart';
import '../core/api.dart';
import '../core/models.dart';
import '../core/store.dart';

const coral = Color(0xFFFF527B);
const ink = Color(0xFF100F19);
const panel = Color(0xFF201F2D);
const pale = Color(0xFFB8B6CA);

Color parseHex(String value) {
  try { return Color(int.parse('FF${value.replaceAll('#', '')}',radix:16)); }
  catch (_) { return coral; }
}
void notice(BuildContext context,String message) {
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text(message),backgroundColor:panel));
}

class KisaRoot extends StatefulWidget {
  final KisaStore store;
  const KisaRoot({super.key,required this.store});
  @override
  State<KisaRoot> createState()=>_KisaRootState();
}
class _KisaRootState extends State<KisaRoot> {
  int index=0;
  bool walletVisited=false;
  bool openedDeepLink=false;
  @override
  void initState() {
    super.initState();
    widget.store.addListener(_openIncomingSeries);
  }
  @override
  void dispose() {
    widget.store.removeListener(_openIncomingSeries);
    super.dispose();
  }
  void _openIncomingSeries() {
    if(openedDeepLink || widget.store.loading || widget.store.error!=null) return;
    openedDeepLink=true;
    final parts=Uri.base.pathSegments;
    if(parts.length!=2 || parts.first!='series')return;
    final matching=widget.store.shows.where((s)=>s.id==parts.last);
    if(matching.isEmpty)return;
    WidgetsBinding.instance.addPostFrameCallback((_){
      if(mounted)openDetail(context, widget.store, matching.first);
    });
  }
  @override
  Widget build(BuildContext context)=>AnimatedBuilder(animation:widget.store,builder:(context,_) {
    if(widget.store.loading) return Scaffold(body:Center(child:Padding(
      padding:const EdgeInsets.symmetric(horizontal:28),
      child:Column(mainAxisSize:MainAxisSize.min,children:[
        const Icon(Icons.play_circle_fill_rounded,color:coral,size:78),
        const SizedBox(height:14),
        const Text('KISA',style:TextStyle(fontSize:35,fontWeight:FontWeight.w900,letterSpacing:8)),
        const SizedBox(height:18),
        const SizedBox(height:22,width:22,child:CircularProgressIndicator(strokeWidth:2.4,color:coral)),
        const SizedBox(height:16),
        Text(widget.store.startingSlow
          ? 'Preparing KISA for you. Our free server is waking up; this may take a minute.'
          : 'Finding great stories for you…',
          textAlign:TextAlign.center,style:const TextStyle(color:pale,fontSize:13)),
      ]))));
    if(widget.store.error!=null) return Scaffold(body:Center(child:Padding(
      padding:const EdgeInsets.all(30),child:Column(mainAxisSize:MainAxisSize.min,children:[
      const Icon(Icons.wifi_off_rounded,size:58,color:coral),const SizedBox(height:15),
      Text(widget.store.error!,textAlign:TextAlign.center),const SizedBox(height:16),
      FilledButton(onPressed:widget.store.initialize,child:const Text('Try again'))]))));
    return Scaffold(body:IndexedStack(index:index,children:[
      DiscoverScreen(store:widget.store,onWallet:()=>setState(() {index=3; walletVisited=true;})),
      ExploreScreen(store:widget.store),LibraryScreen(store:widget.store),
      walletVisited ? WalletScreen(store:widget.store) : const SizedBox.shrink()]),
      bottomNavigationBar:SafeArea(top:false,child:Container(
        decoration:const BoxDecoration(color:Color(0xFF191825),border:Border(top:BorderSide(color:Color(0xFF292838)))),
        padding:const EdgeInsets.fromLTRB(8,6,8,7),child:Row(mainAxisAlignment:MainAxisAlignment.spaceEvenly,children:[
          _nav(0,Icons.home_rounded,'Home'),_nav(1,Icons.explore_rounded,'Explore'),
          _nav(2,Icons.bookmark_rounded,'My List'),_nav(3,Icons.toll_rounded,'Coins')]))));
  });
  Widget _nav(int i,IconData icon,String label)=>Expanded(child:InkWell(
    onTap:(){
      if (i == index) return;
      setState(() { index=i; if (i==3) walletVisited=true; });
      if (i==2) unawaited(widget.store.refreshLibrary().catchError((Object _) {}));
    },
    borderRadius:BorderRadius.circular(16),child:Padding(padding:const EdgeInsets.symmetric(vertical:5),
      child:Column(mainAxisSize:MainAxisSize.min,children:[Icon(icon,color:index==i?coral:pale,size:25),
      const SizedBox(height:3),Text(label,style:TextStyle(color:index==i?coral:pale,fontSize:11,fontWeight:index==i?FontWeight.w700:FontWeight.w400))]))));
}

class Artwork extends StatelessWidget {
  final KisaShow show;
  final double? height;
  final bool wide;
  const Artwork({super.key,required this.show,this.height,this.wide=false});
  @override
  Widget build(BuildContext context) {
    final color=parseHex(show.accent);
    final image=show.posterUrl;
    return SizedBox(height:height,child:ClipRRect(borderRadius:BorderRadius.circular(18),
      child:Stack(fit:StackFit.expand,children:[
        Container(decoration:BoxDecoration(gradient:LinearGradient(begin:Alignment.topLeft,end:Alignment.bottomRight,
          colors:[color.withValues(alpha:.8),const Color(0xFF25203D),const Color(0xFF0A0912)]))),
        if(image!=null && image.startsWith('https://')) Image.network(image,fit:BoxFit.cover,
          errorBuilder:(_,__,___)=>const SizedBox.shrink()),
        Positioned(right:-28,top:wide?14:35,child:Icon(Icons.auto_awesome_rounded,
          color:Colors.white.withValues(alpha:.07),size:wide?230:160)),
        Positioned(right:14,top:35,child:Container(width:wide?115:70,height:wide?115:70,
          decoration:BoxDecoration(shape:BoxShape.circle,gradient:RadialGradient(
            colors:[color.withValues(alpha:.65),color.withValues(alpha:0)])))),
        Positioned.fill(child:DecoratedBox(decoration:BoxDecoration(
          gradient:LinearGradient(begin:Alignment.topCenter,end:Alignment.bottomCenter,
          colors:[Colors.transparent,Colors.black.withValues(alpha:.15),Colors.black.withValues(alpha:.86)],
          stops:const [0,.44,1])))),
        Positioned(left:14,right:12,bottom:13,child:Column(crossAxisAlignment:CrossAxisAlignment.start,
          mainAxisSize:MainAxisSize.min,children:[
            Text(show.genre.toUpperCase(),style:const TextStyle(color:Color(0xFFFFC6A2),letterSpacing:2,fontSize:10,fontWeight:FontWeight.bold)),
            const SizedBox(height:5),Text(show.title,maxLines:2,overflow:TextOverflow.ellipsis,
              style:TextStyle(fontSize:wide?30:17,fontWeight:FontWeight.w900,height:1.03)),
            if(wide) ...[const SizedBox(height:9),Text(show.synopsis,maxLines:2,overflow:TextOverflow.ellipsis,
              style:const TextStyle(fontSize:13,color:Color(0xFFE4DFE6),height:1.35))],
          ])),
      ])));
  }
}

class SectionHeading extends StatelessWidget {
  final String title;final String? subtitle;
  const SectionHeading(this.title,{super.key,this.subtitle});
  @override
  Widget build(BuildContext context)=>Padding(padding:const EdgeInsets.fromLTRB(20,27,20,14),
    child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
      Text(title,style:const TextStyle(fontWeight:FontWeight.w800,fontSize:22)),
      if(subtitle!=null)...[const SizedBox(height:3),Text(subtitle!,style:const TextStyle(color:pale,fontSize:12))]]));
}

void openDetail(BuildContext context,KisaStore store,KisaShow show) {
  Navigator.push(context,MaterialPageRoute(builder:(_)=>ShowScreen(store:store,show:show)));
}

class DiscoverScreen extends StatelessWidget {
  final KisaStore store;final VoidCallback onWallet;
  const DiscoverScreen({super.key,required this.store,required this.onWallet});
  @override
  Widget build(BuildContext context) {
    final all=store.shows;
    return SafeArea(child:RefreshIndicator(color:coral,onRefresh:()async{
      await store.reloadShows();await store.refreshMe();},child:CustomScrollView(slivers:[
      SliverToBoxAdapter(child:Padding(padding:const EdgeInsets.fromLTRB(20,22,20,12),
        child:Row(children:[const Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
          Text('KISA',style:TextStyle(fontSize:31,fontWeight:FontWeight.w900,letterSpacing:4)),
          Text('ONE MORE EPISODE.',style:TextStyle(color:pale,letterSpacing:1.6,fontSize:10))]),
          const Spacer(),InkWell(onTap:onWallet,child:Container(padding:const EdgeInsets.symmetric(horizontal:14,vertical:10),
            decoration:BoxDecoration(color:panel,borderRadius:BorderRadius.circular(22)),
            child:Row(children:[const Icon(Icons.toll_rounded,color:Color(0xFFFFCA70),size:21),
              const SizedBox(width:7),Text('${store.balance}',style:const TextStyle(fontWeight:FontWeight.bold))])))]))),
      if(all.isEmpty) SliverFillRemaining(hasScrollBody:false,
        child:Center(child:Padding(padding:const EdgeInsets.all(30),
          child:Column(mainAxisSize:MainAxisSize.min,children:[
            const Icon(Icons.movie_filter_rounded,color:coral,size:58),
            const SizedBox(height:16),
            const Text('New stories are on the way',
              textAlign:TextAlign.center,style:TextStyle(fontWeight:FontWeight.w800,fontSize:22)),
            const SizedBox(height:8),
            const Text('Check back soon for short dramas worth watching.',
              textAlign:TextAlign.center,style:TextStyle(color:pale)),
            const SizedBox(height:14),
            OutlinedButton.icon(onPressed:store.reloadShows,
              icon:const Icon(Icons.refresh_rounded),label:const Text('Refresh stories')),
          ])))),
      if(all.isNotEmpty) SliverToBoxAdapter(child:Padding(
        padding:const EdgeInsets.symmetric(horizontal:18),
        child:GestureDetector(onTap:()=>openDetail(context,store,all.first),
          child:Stack(children:[
            Artwork(show:all.first,height:270,wide:true),
            const Positioned(top:14,left:14,child:LabelPill('FEATURED')),
            Positioned(bottom:14,right:14,child:CircleAvatar(backgroundColor:coral,radius:25,
              child:Icon(Icons.play_arrow_rounded,size:30,color:Colors.white))),
          ])))),
      if(store.watching.isNotEmpty) ...[
        const SliverToBoxAdapter(child:SectionHeading('Continue watching')),
        SliverToBoxAdapter(child:SizedBox(height:180,child:ListView.separated(
          padding:const EdgeInsets.symmetric(horizontal:18),scrollDirection:Axis.horizontal,
          itemCount:store.watching.length,
          separatorBuilder:(_,__)=>const SizedBox(width:10),
          itemBuilder:(context,i)=>GestureDetector(
            onTap:()=>openDetail(context,store,store.watching[i]),
            child:SizedBox(width:130,child:Artwork(show:store.watching[i],height:175)))))),
      ],
      if(all.isNotEmpty) const SliverToBoxAdapter(child:SectionHeading(
        'All stories',subtitle:'Tap a series to start watching.')),
      if(all.isNotEmpty) SliverPadding(
        padding:const EdgeInsets.fromLTRB(18,0,18,30),
        sliver:SliverGrid.builder(
          itemCount:all.length,
          gridDelegate:const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount:2,crossAxisSpacing:12,mainAxisSpacing:12,childAspectRatio:.72),
          itemBuilder:(context,i)=>GestureDetector(
            onTap:()=>openDetail(context,store,all[i]),child:Artwork(show:all[i])))),
    ])));
  }
}
class LabelPill extends StatelessWidget {
  final String text;const LabelPill(this.text,{super.key});
  @override
  Widget build(BuildContext context)=>Container(padding:const EdgeInsets.symmetric(horizontal:11,vertical:7),
    decoration:BoxDecoration(color:coral,borderRadius:BorderRadius.circular(25)),
    child:Text(text,style:const TextStyle(color:Colors.white,fontWeight:FontWeight.w900,fontSize:10,letterSpacing:.5)));
}

class ExploreScreen extends StatefulWidget {
  final KisaStore store;const ExploreScreen({super.key,required this.store});
  @override
  State<ExploreScreen> createState()=>_ExploreScreenState();
}
class _ExploreScreenState extends State<ExploreScreen> {
  final controller=TextEditingController();
  String genre='All';
  Timer? debounce;
  int searchVersion=0;
  bool searching=false;
  List<KisaShow>? results;
  @override
  void dispose(){debounce?.cancel();controller.dispose();super.dispose();}
  Future<void> search() async {
    final query=controller.text.trim();
    final selectedGenre=genre=='All'?'':genre;
    final version=++searchVersion;
    if(query.isEmpty && selectedGenre.isEmpty){
      setState((){results=null;searching=false;});
      return;
    }
    setState(()=>searching=true);
    try {
      final found=await widget.store.searchShows(query:query,genre:selectedGenre);
      if(mounted && version==searchVersion)setState(() {results=found;searching=false;});
    } catch (_) {
      if(mounted && version==searchVersion){
        setState(()=>searching=false);
        notice(context,'Could not search right now. Please try again.');
      }
    }
  }
  @override
  Widget build(BuildContext context) {
    final movies=results??widget.store.shows;
    return SafeArea(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
    const Padding(padding:EdgeInsets.fromLTRB(20,22,20,16),child:Text('Explore',style:TextStyle(fontSize:31,fontWeight:FontWeight.w900))),
    Padding(padding:const EdgeInsets.symmetric(horizontal:18),child:TextField(controller:controller,
      onChanged:(_){debounce?.cancel();debounce=Timer(const Duration(milliseconds:300),search);},
      decoration:InputDecoration(hintText:'Find your next story',prefixIcon:const Icon(Icons.search_rounded),
        filled:true,fillColor:panel,border:OutlineInputBorder(borderRadius:BorderRadius.circular(15),borderSide:BorderSide.none)))),
    const SizedBox(height:15),SizedBox(height:42,child:ListView(scrollDirection:Axis.horizontal,
      padding:const EdgeInsets.symmetric(horizontal:18),children:['All','Romance','Mystery','Drama'].map((g)=>
      Padding(padding:const EdgeInsets.only(right:8),child:ChoiceChip(label:Text(g),selected:genre==g,
        selectedColor:coral,onSelected:(_){setState(()=>genre=g);search();}))).toList())),
    const SizedBox(height:15),Expanded(child:searching
      ?const Center(child:CircularProgressIndicator(color:coral))
      :movies.isEmpty
        ?const Center(child:Text('No stories found',style:TextStyle(color:pale)))
        :GridView.builder(padding:const EdgeInsets.fromLTRB(18,4,18,20),
        gridDelegate:const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount:2,
          crossAxisSpacing:12,mainAxisSpacing:12,childAspectRatio:.7),
        itemCount:movies.length,itemBuilder:(context,i){final s=movies[i];
          return GestureDetector(onTap:()=>openDetail(context,widget.store,s),child:Artwork(show:s));}))]));
  }
}

class LibraryScreen extends StatelessWidget {
  final KisaStore store;const LibraryScreen({super.key,required this.store});
  @override
  Widget build(BuildContext context)=>SafeArea(child:RefreshIndicator(onRefresh:store.refreshLibrary,
    child:ListView(children:[const SectionHeading('My Library',subtitle:'Pick up exactly where you stopped'),
      if(store.watching.isNotEmpty)...[
        const SectionHeading('Continue watching'),
        ...store.watching.map((s)=>ListTile(contentPadding:const EdgeInsets.symmetric(horizontal:20,vertical:4),
          leading:SizedBox(width:60,child:Artwork(show:s,height:90)),title:Text(s.title),
          subtitle:Text('Episode ${s.resumeEpisode ?? 1}',style:const TextStyle(color:pale)),
          trailing:const Icon(Icons.play_circle_fill_rounded,color:coral),
          onTap:()=>openDetail(context,store,s)))],
      const SectionHeading('Saved stories'),
      if(store.saved.isEmpty)const Padding(padding:EdgeInsets.all(24),child:Text('Tap the bookmark on a series to save it here.',style:TextStyle(color:pale))),
      ...store.saved.map((s)=>ListTile(contentPadding:const EdgeInsets.symmetric(horizontal:20,vertical:4),
        leading:SizedBox(width:60,child:Artwork(show:s,height:90)),title:Text(s.title),
        subtitle:Text(s.genre,style:const TextStyle(color:pale)),
        trailing:const Icon(Icons.chevron_right),onTap:()=>openDetail(context,store,s))),
      const SizedBox(height:40)])));
}

class ShowScreen extends StatefulWidget {
  final KisaStore store;final KisaShow show;
  const ShowScreen({super.key,required this.store,required this.show});
  @override
  State<ShowScreen> createState()=>_ShowScreenState();
}
class _ShowScreenState extends State<ShowScreen> {
  KisaDetail? detail;String? error;bool favourite=false;
  @override
  void initState(){super.initState();load();}
  Future<void> load() async {
    try {final d=await widget.store.detail(widget.show.id);
      if(mounted)setState((){detail=d;favourite=d.favourite;error=null;});}
    catch(e){if(mounted)setState(()=>error=e.toString());}
  }
  @override
  Widget build(BuildContext context) {
    final d=detail;
    return Scaffold(appBar:AppBar(title:const Text('KISA',style:TextStyle(fontWeight:FontWeight.w900,letterSpacing:4)),
      actions:[IconButton(tooltip:'Share series link',icon:const Icon(Icons.share_rounded),
        onPressed:()async{
          final base=Uri.base.origin;
          await Clipboard.setData(ClipboardData(
            text:'$base/series/${Uri.encodeComponent(widget.show.id)}'));
          if(context.mounted)notice(context,'Series link copied');
        }),IconButton(icon:Icon(favourite?Icons.bookmark_rounded:Icons.bookmark_border_rounded,color:coral),
        onPressed:()async{try{final b=await widget.store.toggleFavourite(widget.show.id);
          if(mounted)setState(()=>favourite=b);}catch(e){if(context.mounted)notice(context,e.toString());}})]),
      body: d==null?Center(child:error==null?const CircularProgressIndicator(color:coral):Column(
        mainAxisSize:MainAxisSize.min,children:[Text(error!),TextButton(onPressed:load,child:const Text('Retry'))])):
      ListView(children:[Padding(padding:const EdgeInsets.symmetric(horizontal:18),child:Artwork(show:d.show,height:310,wide:true)),
        Padding(padding:const EdgeInsets.fromLTRB(20,18,20,0),child:Column(crossAxisAlignment:CrossAxisAlignment.start,
        children:[Text(d.show.title,style:const TextStyle(fontSize:26,fontWeight:FontWeight.w900)),
          const SizedBox(height:9),Text(d.show.synopsis,style:const TextStyle(height:1.55,color:pale)),
          const SizedBox(height:18),Row(children:[LabelPill('${d.episodes.where((e)=>e.isFree).length} FREE EPISODES'),const SizedBox(width:12),
            Text('${d.episodes.length} episodes  ·  ${d.show.genre}',style:const TextStyle(color:pale,fontSize:12))]),
          const SizedBox(height:19),SizedBox(width:double.infinity,child:FilledButton.icon(
            onPressed:(){if(d.episodes.isNotEmpty)Navigator.push(context,MaterialPageRoute(
              builder:(_)=>PlayerScreen(store:widget.store,detail:d,initialNumber:d.resume))).then((_)=>load());},
            icon:const Icon(Icons.play_arrow_rounded),label:Text('Watch Episode ${d.resume}')))])),
        const SectionHeading('Episodes',subtitle:'Unlock once. Rewatch whenever you want.'),
        ...d.episodes.map((e)=>ListTile(contentPadding:const EdgeInsets.symmetric(horizontal:20,vertical:3),
          onTap:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>PlayerScreen(store:widget.store,detail:d,initialNumber:e.number))).then((_)=>load()),
          leading:Container(width:58,height:58,decoration:BoxDecoration(color:panel,borderRadius:BorderRadius.circular(14)),
            child:Center(child:Text('${e.number}'.padLeft(2,'0'),style:const TextStyle(fontWeight:FontWeight.w900,fontSize:21)))),
          title:Text('Episode ${e.number} · ${e.title}',maxLines:1,overflow:TextOverflow.ellipsis),
          subtitle:Text('${e.duration}s  ·  ${e.isFree?'FREE':e.isUnlocked?'UNLOCKED':'${e.cost} COINS'}',
            style:TextStyle(color:e.isFree||e.isUnlocked?const Color(0xFF8DDBC3):pale,fontSize:11)),
          trailing:Icon(e.isFree||e.isUnlocked?Icons.play_circle_outline_rounded:Icons.lock_outline_rounded,color:coral))),
        const SizedBox(height:28)]));
  }
}

class WalletScreen extends StatefulWidget {
  final KisaStore store;
  const WalletScreen({super.key,required this.store});
  @override
  State<WalletScreen> createState()=>_WalletScreenState();
}
class _WalletScreenState extends State<WalletScreen> with WidgetsBindingObserver {
  StreamSubscription<List<PurchaseDetails>>? subscription;
  ProductDetails? product;
  bool busy=false;
  bool storeAvailable=false;
  String? purchaseProblem;
  String? pendingClickpassId;
  Timer? reconciliationTimer;
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if(state==AppLifecycleState.resumed && pendingClickpassId!=null)reconcileClickpass();
  }
  Future<void> reconcileClickpass() async {
    final id=pendingClickpassId;
    if(id==null||!mounted)return;
    try {
      final result=await widget.store.refreshPayment(id);
      if(result['status']=='paid'){
        await widget.store.refreshWallet();
        reconciliationTimer?.cancel();pendingClickpassId=null;
        if(mounted)notice(context,'Payment confirmed. Your coins are ready!');
      }
    }catch(e){if(mounted)setState(()=>purchaseProblem=e.toString());}
  }
  @override
  void initState() {
    super.initState();WidgetsBinding.instance.addObserver(this);
    widget.store.refreshWallet().catchError((Object e){if(mounted)notice(context,e.toString());});
    if (billingMode=='play') {
      subscription=InAppPurchase.instance.purchaseStream.listen(onPurchases,
        onError:(Object e){if(mounted)setState(()=>purchaseProblem=e.toString());});
      loadProduct();
    }
  }
  Future<void> loadProduct() async {
    try {
      final available=await InAppPurchase.instance.isAvailable();
      if(!available){if(mounted)setState(()=>purchaseProblem='Google Play Billing is unavailable on this device.');return;}
      final products=await InAppPurchase.instance.queryProductDetails({productId});
      if(mounted)setState((){
        storeAvailable=true;
        if(products.productDetails.isNotEmpty)product=products.productDetails.first;
        else purchaseProblem='Configure $productId as an active in-app product in Play Console.';
      });
    }catch(e){if(mounted)setState(()=>purchaseProblem=e.toString());}
  }
  Future<void> onPurchases(List<PurchaseDetails> purchases) async {
    for (final p in purchases) {
      if(p.productID!=productId) continue;
      if(p.status==PurchaseStatus.error){if(mounted)setState(()=>purchaseProblem=p.error?.message??'Purchase failed');continue;}
      if(p.status==PurchaseStatus.canceled) { if(mounted)setState(()=>busy=false);continue; }
      if(p.status==PurchaseStatus.purchased||p.status==PurchaseStatus.restored) {
        try {
          // Backend validates purchase with Google before minting coins. One token can only be credited once.
          await widget.store.verifyPlay(p.productID,p.verificationData.serverVerificationData);
          // On Android, consume AFTER verified credit to allow buying the consumable again.
          await InAppPurchase.instance.getPlatformAddition<InAppPurchaseAndroidPlatformAddition>().consumePurchase(p);
          if(p.pendingCompletePurchase)await InAppPurchase.instance.completePurchase(p);
          if(mounted)notice(context,'30 coins added successfully!');
        } catch(e) {
          // Do NOT acknowledge/consume when fulfillment failed: allows retried verification.
          if(mounted)setState(()=>purchaseProblem='Payment verification pending: $e');
        }
      }
    }
    if(mounted)setState(()=>busy=false);
  }
  @override
  void dispose(){WidgetsBinding.instance.removeObserver(this);reconciliationTimer?.cancel();subscription?.cancel();super.dispose();}
  Future<void> buy() async {
    if(busy)return;
    setState((){busy=true;purchaseProblem=null;});
    try {
      if(!(billingMode=='demo' && widget.store.demo) && !widget.store.emailVerified) {
        final result = await Navigator.push<bool>(context,MaterialPageRoute(
          builder:(_)=>EmailSignInScreen(store:widget.store)));
        if(result!=true) return;
      }
      if(billingMode=='demo' && widget.store.demo) {
        await widget.store.demoTopup();
        if(mounted)notice(context,'DEMO: 30 test coins credited (no real payment).');
      } else if(billingMode=='play') {
        if(product==null)throw const ApiError(503,'Play product not available. Open through Play Store testing track.');
        final started=await InAppPurchase.instance.buyConsumable(
          purchaseParam:PurchaseParam(productDetails:product!),autoConsume:false);
        if(!started)throw const ApiError(503,'Could not launch Google Play checkout.');
        return; // Wait for purchaseStream outcome.
      } else if(billingMode=='clickpesa' || billingMode=='clickpass') {
        final r=await widget.store.createPayment();
        final checkout=r['checkout_url'];
        if(checkout is! String || !checkout.startsWith('https://')) {
          throw const ApiError(503,'ClickPesa checkout is not configured on the server.');
        }
        pendingClickpassId = r['id'] as String;
        reconciliationTimer?.cancel();
        reconciliationTimer=Timer.periodic(const Duration(seconds:6),(_)=>reconcileClickpass());
        final opened=await launchUrl(Uri.parse(checkout),mode:LaunchMode.externalApplication);
        if(!opened)throw const ApiError(503,'Unable to open secure payment checkout');
        if(mounted)notice(context,'Complete payment in the browser. Coins appear after provider confirmation.');
      } else {
        throw const ApiError(503,'Payment provider is not configured');
      }
    }catch(e){if(mounted)setState(()=>purchaseProblem=e.toString());}
    finally{if(mounted)setState(()=>busy=false);}
  }
  @override
  Widget build(BuildContext context)=>SafeArea(child:RefreshIndicator(onRefresh:widget.store.refreshWallet,
    child:ListView(padding:const EdgeInsets.fromLTRB(20,24,20,60),children:[
      const Text('My Wallet',style:TextStyle(fontWeight:FontWeight.w900,fontSize:32)),
      const SizedBox(height:20),Container(padding:const EdgeInsets.all(24),decoration:BoxDecoration(
        gradient:const LinearGradient(colors:[Color(0xFF40305B),Color(0xFF6F274D)]),
        borderRadius:BorderRadius.circular(24)),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
          const Text('AVAILABLE COINS',style:TextStyle(fontSize:11,letterSpacing:2.3,fontWeight:FontWeight.w800,color:Color(0xFFD6C4D9))),
          const SizedBox(height:12),Row(children:[const Icon(Icons.toll_rounded,color:Color(0xFFFFD27A),size:38),
            const SizedBox(width:9),Text('${widget.store.balance}',style:const TextStyle(fontSize:52,fontWeight:FontWeight.w900))]),
          const SizedBox(height:8),Text('Every premium episode costs ${widget.store.episodeCost} coins',style:const TextStyle(color:Color(0xFFE6CEDC),fontSize:12))])),
      if(!widget.store.emailVerified)Padding(padding:const EdgeInsets.only(top:14),
        child:TextButton.icon(onPressed:()async{
          await Navigator.push(context,MaterialPageRoute(
            builder:(_)=>EmailSignInScreen(store:widget.store)));
        },icon:const Icon(Icons.alternate_email),label:const Text('Verify email to protect your coins'))),
      const SectionHeading('Top up your wallet',subtitle:'Unlock your next cliffhanger'),
      Container(padding:const EdgeInsets.all(20),decoration:BoxDecoration(color:panel,borderRadius:BorderRadius.circular(19),
        border:Border.all(color:const Color(0xFF4A3F54))),child:Column(children:[
          Row(children:[const Icon(Icons.toll_rounded,color:Color(0xFFFFCC70),size:29),const SizedBox(width:9),
            Expanded(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
              Text('${widget.store.packCoins} Coins',style:const TextStyle(fontSize:23,fontWeight:FontWeight.w900)),
              Text('${widget.store.packCoins ~/ widget.store.episodeCost} premium episodes',
                style:const TextStyle(color:pale,fontSize:12))])),
            Text(product?.price ?? 'TZS ${widget.store.packTzs}',style:const TextStyle(fontSize:17,fontWeight:FontWeight.w800))]),
          const SizedBox(height:15),SizedBox(width:double.infinity,child:FilledButton.icon(
            onPressed:busy||widget.store.paymentMode=='disabled'?null:buy,
            icon:busy?const SizedBox(width:16,height:16,child:CircularProgressIndicator(strokeWidth:2,color:Colors.white)):
              const Icon(Icons.add_circle_rounded),
            label:Text(widget.store.paymentMode=='disabled'?'Purchases coming soon':
              billingMode=='demo'&&widget.store.demo?'Add DEMO coins':'Buy ${widget.store.packCoins} coins'))),
          if(billingMode=='demo'&&widget.store.demo)const Padding(padding:EdgeInsets.only(top:9),child:
            Text('TEST ONLY — no money is charged',style:TextStyle(color:Color(0xFFFFCE8E),fontSize:11))),
          if(purchaseProblem!=null)Padding(padding:const EdgeInsets.only(top:12),
            child:Text(purchaseProblem!,textAlign:TextAlign.center,style:const TextStyle(color:Color(0xFFFFB7BB),fontSize:12))),
        ])),
      const SectionHeading('Recent activity'),
      if(widget.store.entries.isEmpty)const Padding(padding:EdgeInsets.symmetric(vertical:14),
        child:Text('Your wallet history will appear here.',style:TextStyle(color:pale))),
      ...widget.store.entries.map((entry){final delta=(entry['delta'] as num).toInt();
        return ListTile(contentPadding:EdgeInsets.zero,leading:CircleAvatar(backgroundColor:panel,
          child:Icon(delta>0?Icons.add_rounded:Icons.play_arrow_rounded,color:delta>0?const Color(0xFF91E6C1):coral)),
          title:Text(delta>0?'Coin top-up':'Episode unlocked'),
          subtitle:Text((entry['kind']??'').toString(),style:const TextStyle(color:pale)),
          trailing:Text('${delta>0?'+':''}$delta',style:TextStyle(fontWeight:FontWeight.bold,
            color:delta>0?const Color(0xFF91E6C1):Colors.white)));}),
    ])));
}

class EmailSignInScreen extends StatefulWidget {
  final KisaStore store;
  const EmailSignInScreen({super.key, required this.store});
  @override
  State<EmailSignInScreen> createState() => _EmailSignInScreenState();
}

class _EmailSignInScreenState extends State<EmailSignInScreen> {
  final email = TextEditingController();
  final code = TextEditingController();
  bool sent = false;
  bool busy = false;
  String? error;
  @override
  void dispose(){ email.dispose(); code.dispose(); super.dispose(); }
  Future<void> submit() async {
    if(busy)return;
    setState((){busy=true;error=null;});
    try {
      if(!sent) {
        await widget.store.requestEmailCode(email.text);
        if(mounted)setState(()=>sent=true);
      } else {
        await widget.store.verifyEmailCode(email.text,code.text);
        if(mounted)Navigator.pop(context,true);
      }
    } catch(e) {if(mounted)setState(()=>error=e.toString());}
    finally {if(mounted)setState(()=>busy=false);}
  }
  @override
  Widget build(BuildContext context)=>Scaffold(
    appBar:AppBar(title:const Text('Secure your KISA account')),
    body:SafeArea(child:ListView(padding:const EdgeInsets.all(24),children:[
      const Icon(Icons.verified_user_rounded,color:coral,size:72),
      const SizedBox(height:20),
      Text(sent?'Enter your 6-digit code':'Keep your coins and episodes',
        style:const TextStyle(fontSize:25,fontWeight:FontWeight.w900)),
      const SizedBox(height:12),
      Text(sent?'We sent a verification code to your email. It expires in 10 minutes.':
        'Verify your email so your purchases can be recovered on another device.',
        style:const TextStyle(color:pale)),
      const SizedBox(height:20),
      TextField(controller:email,keyboardType:TextInputType.emailAddress,enabled:!sent,
        decoration:const InputDecoration(labelText:'Email address',border:OutlineInputBorder())),
      if(sent)...[const SizedBox(height:12),TextField(controller:code,
        keyboardType:TextInputType.number,maxLength:6,
        decoration:const InputDecoration(labelText:'Verification code',border:OutlineInputBorder()))],
      const SizedBox(height:16),
      FilledButton(onPressed:busy?null:submit,
        child:Text(busy?'Please wait…':sent?'Verify and continue':'Send verification code')),
      if(sent)TextButton(onPressed:busy?null:(){setState((){sent=false;code.clear();});},
        child:const Text('Use a different email')),
      if(error!=null)Padding(padding:const EdgeInsets.only(top:12),
        child:Text(error!,style:const TextStyle(color:Colors.redAccent))),
    ])));
}

class PlayerScreen extends StatefulWidget {
  final KisaStore store;
  final KisaDetail detail;
  final int initialNumber;
  const PlayerScreen({super.key,required this.store,required this.detail,required this.initialNumber});
  @override
  State<PlayerScreen> createState()=>_PlayerScreenState();
}
class _PlayerScreenState extends State<PlayerScreen> with WidgetsBindingObserver {
  late final PageController pages;
  VideoPlayerController? video;
  String? bunnyUrl;
  int selected=0;
  int loadCounter=0;
  bool starting=false;
  bool advancing=false;
  bool stalled=false;
  String? playbackError;
  List<KisaEpisode> episodes=[];
  DateTime _lastPlayerRepaint = DateTime.fromMillisecondsSinceEpoch(0);

  @override
  void initState() {
    super.initState();WidgetsBinding.instance.addObserver(this);
    episodes=List.of(widget.detail.episodes);
    selected=episodes.indexWhere((e)=>e.number==widget.initialNumber);
    if(selected<0)selected=0;
    pages=PageController(initialPage:selected);
    if(episodes.isNotEmpty)loadEpisode(selected);
  }
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if(state!=AppLifecycleState.resumed)video?.pause();
  }
  @override
  void dispose(){WidgetsBinding.instance.removeObserver(this);
    loadCounter++;video?.removeListener(onTick);video?.dispose();pages.dispose();super.dispose();}

  Future<void> loadEpisode(int i) async {
    if(i<0||i>=episodes.length)return;
    final generation=++loadCounter;
    final old=video;video=null;bunnyUrl=null;
    if(old!=null){old.removeListener(onTick);await old.dispose();}
    if(!mounted||generation!=loadCounter)return;
    setState((){selected=i;starting=true;playbackError=null;stalled=false;advancing=false;});
    final episode=episodes[i];
    if(!episode.isUnlocked){if(mounted)setState(()=>starting=false);return;}
    try {
      final r=await widget.store.playback(episode.id);
      if(!mounted||generation!=loadCounter)return;
      if(r['ready']!=true){setState((){starting=false;stalled=true;playbackError=(r['message']??'Video not ready').toString();});return;}
      if(r['player_type']=='bunny_embed') {
        if(kIsWeb) {
          setState((){bunnyUrl=r['url'] as String;starting=false;});
          widget.store.progress(widget.detail.show.id,episode.number).catchError((Object _){});
          return;
        }
        setState((){starting=false;stalled=true;playbackError='Bunny streaming is currently available in the web version.';});
        return;
      }
      final controller=VideoPlayerController.networkUrl(Uri.parse(r['url'] as String),
        videoPlayerOptions:VideoPlayerOptions(mixWithOthers:false));
      await controller.initialize();
      if(!mounted||generation!=loadCounter){await controller.dispose();return;}
      video=controller;controller.addListener(onTick);
      setState(()=>starting=false);
      await controller.play();
      widget.store.progress(widget.detail.show.id,episode.number).catchError((Object _){});
    }catch(e){if(mounted&&generation==loadCounter)setState((){starting=false;playbackError=e.toString();});}
  }
  void onTick() {
    final v=video;if(v==null||!mounted)return;
    if(v.value.hasError){setState(()=>playbackError=v.value.errorDescription??'Playback error');return;}
    if(v.value.isInitialized&&!advancing&&v.value.isCompleted) {
      advancing=true;
      if(selected<episodes.length-1) {
        pages.nextPage(duration:const Duration(milliseconds:310),curve:Curves.easeOutCubic);
      }
    }
    final now = DateTime.now();
    if(now.difference(_lastPlayerRepaint) >= const Duration(milliseconds: 250)) {
      _lastPlayerRepaint = now;
      setState((){});
    }
  }
  // The Bunny iframe is a web platform view. Navigation controls must live
  // outside its viewport so the iframe cannot consume their pointer events.
  void _closePlayer() {
    if (!mounted) return;
    final navigator = Navigator.of(context);
    if (navigator.canPop()) {
      navigator.pop();
    } else {
      // A direct entry with no preceding route can still return to KISA Home.
      navigator.pushReplacement<void, void>(
        MaterialPageRoute<void>(builder: (_) => KisaRoot(store: widget.store)),
      );
    }
  }

  void _nextEpisode() {
    if (selected < episodes.length - 1 && pages.hasClients) {
      pages.nextPage(
        duration: const Duration(milliseconds: 310),
        curve: Curves.easeOutCubic,
      );
    }
  }

  Future<void> unlock(KisaEpisode ep) async {
    try {
      await widget.store.unlock(ep.id);
      final d=await widget.store.detail(widget.detail.show.id);
      if(!mounted)return;
      setState(()=>episodes=d.episodes);
      await loadEpisode(selected);
    }on ApiError catch(e){
      if(!mounted)return;
      if(e.status==402){
        await Navigator.push(context,MaterialPageRoute(builder:(_)=>Scaffold(
          appBar:AppBar(title:const Text('Get coins')),
          body:WalletScreen(store:widget.store))));
        if(mounted){await widget.store.refreshMe();setState((){});}
      } else {notice(context,e.message);}
    }catch(e){if(mounted)notice(context,e.toString());}
  }
  @override
  Widget build(BuildContext context){
    return Scaffold(
      backgroundColor: Colors.black,
      // Keep the navigation bar OUTSIDE the Bunny iframe / HtmlElementView.
      // Flutter overlay buttons placed over iframes can appear but miss taps.
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          tooltip: 'Back to series',
          onPressed: _closePlayer,
          icon: const Icon(Icons.arrow_back_rounded),
        ),
        titleSpacing: 0,
        title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(widget.detail.show.title,
            maxLines: 1, overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          Text(episodes.isEmpty ? 'No episodes yet' : 'Episode ${episodes[selected].number} of ${episodes.length}',
            style: const TextStyle(color: Colors.white70, fontSize: 12)),
        ]),
        actions: [
          if (selected < episodes.length - 1)
            IconButton(
              tooltip: 'Next episode',
              onPressed: _nextEpisode,
              icon: const Icon(Icons.skip_next_rounded),
            ),
          const Icon(Icons.toll_rounded, color: Color(0xFFFFCE6E), size: 18),
          Padding(
            padding: const EdgeInsets.only(left: 5, right: 14),
            child: Center(child: Text('${widget.store.balance}',
              style: const TextStyle(fontWeight: FontWeight.bold))),
          ),
        ],
      ),
      body: episodes.isEmpty ?
      const Center(child:Text('No episodes yet')):
      Stack(children:[PageView.builder(controller:pages,scrollDirection:Axis.vertical,
        itemCount:episodes.length,onPageChanged:(i)=>loadEpisode(i),
        itemBuilder:(context,index)=>const SizedBox.expand()),
        Positioned.fill(child:bunnyUrl!=null
          ?BunnyPlayer(key:ValueKey(bunnyUrl),url:bunnyUrl!,onEnded:(){
              if(!advancing && selected<episodes.length-1){
                advancing=true;
                pages.nextPage(duration:const Duration(milliseconds:310),curve:Curves.easeOutCubic);
              }
            })
          :IgnorePointer(child:video!=null&&video!.value.isInitialized
            ?FittedBox(fit:BoxFit.cover,child:SizedBox(width:video!.value.size.width,
                height:video!.value.size.height,child:VideoPlayer(video!))):
              Container(decoration:BoxDecoration(gradient:LinearGradient(
                colors:[parseHex(widget.detail.show.accent),ink,Colors.black],
                begin:Alignment.topLeft,end:Alignment.bottomRight))))),
        Positioned.fill(child:IgnorePointer(child:DecoratedBox(decoration:BoxDecoration(
          gradient:LinearGradient(begin:Alignment.topCenter,end:Alignment.bottomCenter,
          stops:const [0,.22,.74,1],colors:[Colors.black54,Colors.transparent,Colors.transparent,Colors.black87]))))),
        SafeArea(child:Padding(padding:const EdgeInsets.fromLTRB(12,6,16,15),child:Column(children:[
          const Spacer(),
          if(starting)const CircularProgressIndicator(color:coral),
          if(!starting && !episodes[selected].isUnlocked)_locked(episodes[selected]),
          if(!starting && playbackError!=null && episodes[selected].isUnlocked)
            Container(padding:const EdgeInsets.all(20),decoration:BoxDecoration(color:panel,borderRadius:BorderRadius.circular(18)),
              child:Column(mainAxisSize:MainAxisSize.min,children:[
                const Icon(Icons.movie_outlined,size:45,color:coral),const SizedBox(height:10),
                Text(playbackError!,textAlign:TextAlign.center),const SizedBox(height:12),
                if(!stalled)TextButton(onPressed:()=>loadEpisode(selected),child:const Text('Retry'))])),
          if(!starting && video!=null && video!.value.isInitialized)
            IconButton(onPressed:(){video!.value.isPlaying?video!.pause():video!.play();setState((){});},
              icon:Icon(video!.value.isPlaying?Icons.pause_circle_outline:Icons.play_circle_outline,
                color:Colors.white.withValues(alpha:.8),size:57)),
          const Spacer(),
          Row(children:[Expanded(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
            Text('EP ${episodes[selected].number} · ${episodes[selected].title}',
              style:const TextStyle(fontWeight:FontWeight.w800,fontSize:17)),
            const SizedBox(height:7),Text(
              bunnyUrl != null ? 'Tap Next above to continue' : 'Swipe up for the next episode ↑',
              style:const TextStyle(color:Colors.white70,fontSize:12))])),
            if(selected<episodes.length-1)const Icon(
              Icons.keyboard_double_arrow_up_rounded,size:30,color:Colors.white70)]),
          const SizedBox(height:9),if(video!=null&&video!.value.isInitialized)
            VideoProgressIndicator(video!,allowScrubbing:true,
              colors:const VideoProgressColors(playedColor:coral,bufferedColor:Colors.white38,
                backgroundColor:Colors.white24)),
        ]))),
      ]));
  }
  Widget _locked(KisaEpisode e)=>Container(padding:const EdgeInsets.all(24),margin:const EdgeInsets.symmetric(horizontal:20),
    decoration:BoxDecoration(color:const Color(0xEE201928),borderRadius:BorderRadius.circular(24),
      border:Border.all(color:const Color(0xFF64445D))),
    child:Column(mainAxisSize:MainAxisSize.min,children:[
      const Icon(Icons.lock_rounded,size:43,color:Color(0xFFFFCD75)),
      const SizedBox(height:12),const Text('The story continues…',textAlign:TextAlign.center,
        style:TextStyle(fontSize:24,fontWeight:FontWeight.w900)),
      const SizedBox(height:9),Text('Unlock Episode ${e.number} forever for ${widget.store.episodeCost} coins.',
        textAlign:TextAlign.center,style:const TextStyle(color:pale)),
      const SizedBox(height:16),SizedBox(width:double.infinity,child:FilledButton.icon(
        onPressed:()=>unlock(e),icon:const Icon(Icons.toll_rounded),label:Text('Unlock · ${widget.store.episodeCost} coins'))),
      const SizedBox(height:10),Text('Your balance: ${widget.store.balance} coins',
        style:const TextStyle(color:pale,fontSize:12))]));
}
