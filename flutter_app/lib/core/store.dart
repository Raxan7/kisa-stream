import 'dart:async';
import 'package:flutter/foundation.dart';
import 'api.dart';
import 'models.dart';

class KisaStore extends ChangeNotifier {
  final KisaApi api;
  KisaStore(this.api);
  bool loading = true;
  bool startingSlow = false;
  bool initializing = false;
  String? error;
  int balance = 0;
  bool emailVerified = false;
  int episodeCost = 10;
  int packCoins = 30;
  int packTzs = 1000;
  bool demo = false;
  String paymentMode = billingMode;
  List<KisaShow> shows = [];
  List<KisaShow> saved = [];
  List<KisaShow> watching = [];
  List<Map<String,dynamic>> entries = [];

  Future<void> initialize() async {
    if (initializing) return;
    initializing = true;
    loading = true;
    startingSlow = false;
    error = null;
    notifyListeners();
    final slowTimer = Timer(const Duration(seconds: 7), () {
      if (loading) {
        startingSlow = true;
        notifyListeners();
      }
    });
    try {
      await api.initialize();
      // Only the catalogue blocks Home. Personalization loads separately.
      await reloadShows();
    } catch (e) {
      error = e.toString();
    } finally {
      slowTimer.cancel();
      loading = false;
      initializing = false;
      notifyListeners();
    }
    if (error == null) {
      // Wallet/library failures must not prevent viewers from browsing.
      unawaited(refreshMe().catchError((Object _) {}));
      unawaited(refreshLibrary().catchError((Object _) {}));
    }
  }

  Future<void> refreshMe() async {
    final m=await api.get('/v1/me');
    balance=(m['balance'] as num).toInt();demo=m['demo_mode'] == true;
    emailVerified = m['email_verified'] == true;
    episodeCost = (m['episode_cost'] as num?)?.toInt() ?? 10;
    packCoins = (m['pack_coins'] as num?)?.toInt() ?? 30;
    packTzs = (m['pack_tzs'] as num?)?.toInt() ?? 1000;
    paymentMode=(m['payment_mode'] ?? billingMode).toString();
    notifyListeners();
  }
  Future<void> reloadShows({String query='',String genre=''}) async {
    final params=Uri(queryParameters:{if(query.isNotEmpty)'q':query,if(genre.isNotEmpty)'genre':genre}).query;
    final response=await api.get('/v1/shows${params.isEmpty?'':'?$params'}');
    shows=(response['items'] as List).map((e)=>KisaShow.fromJson(e as Map<String,dynamic>)).toList();
    notifyListeners();
  }
  // Explore results are independent from the Home catalogue.
  Future<List<KisaShow>> searchShows({String query='', String genre=''}) async {
    final params = Uri(queryParameters: {
      if (query.isNotEmpty) 'q': query,
      if (genre.isNotEmpty) 'genre': genre,
    }).query;
    final response = await api.get('/v1/shows${params.isEmpty ? '' : '?$params'}');
    return (response['items'] as List)
        .map((e) => KisaShow.fromJson(e as Map<String,dynamic>))
        .toList();
  }

  Future<KisaDetail> detail(String showId) async => KisaDetail.fromJson(await api.get('/v1/shows/${Uri.encodeComponent(showId)}'));
  Future<void> refreshLibrary() async {
    final response=await api.get('/v1/library');
    saved=(response['saved'] as List).map((e)=>KisaShow.fromJson(e as Map<String,dynamic>)).toList();
    watching=(response['continue_watching'] as List).map((e)=>KisaShow.fromJson(e as Map<String,dynamic>)).toList();
    notifyListeners();
  }
  Future<bool> toggleFavourite(String sid) async {
    final response=await api.post('/v1/shows/${Uri.encodeComponent(sid)}/favourite');
    await refreshLibrary();return response['favourite']==true;
  }
  Future<Map<String,dynamic>> unlock(String id) async {
    final r=await api.post('/v1/episodes/${Uri.encodeComponent(id)}/unlock');
    balance=(r['balance'] as num).toInt();notifyListeners();return r;
  }
  Future<Map<String,dynamic>> playback(String id) => api.post('/v1/episodes/${Uri.encodeComponent(id)}/play');
  Future<void> progress(String sid,int n) async {
    await api.post('/v1/shows/${Uri.encodeComponent(sid)}/progress',{'episode_number':n});
    await refreshLibrary();
  }
  Future<void> refreshWallet() async {
    final response=await api.get('/v1/wallet');
    balance=(response['balance'] as num).toInt();
    entries=(response['entries'] as List).cast<Map<String,dynamic>>();notifyListeners();
  }
  Future<void> demoTopup() async {
    await api.post('/v1/dev/me/demo-topup');
    await refreshWallet();
  }
  Future<void> requestEmailCode(String email) async {
    await api.post('/v1/auth/email/request', {'email':email.trim()});
  }
  Future<void> verifyEmailCode(String email,String code) async {
    final result = await api.post('/v1/auth/email/verify', {
      'email':email.trim(), 'code':code.trim(),
    });
    await api.saveAccessToken(result['access_token'] as String);
    await Future.wait([refreshMe(),reloadShows(),refreshWallet(),refreshLibrary()]);
  }
  Future<Map<String,dynamic>> createPayment() => api.post('/v1/payments');
  Future<Map<String,dynamic>> refreshPayment(String id) => api.post('/v1/payments/${Uri.encodeComponent(id)}/refresh');
  Future<Map<String,dynamic>> verifyPlay(String product,String token) async {
    final response=await api.post('/v1/billing/play/verify',{
      'product_id':product,'purchase_token':token});
    await refreshWallet();return response;
  }
  @override
  void dispose(){api.close();super.dispose();}
}
