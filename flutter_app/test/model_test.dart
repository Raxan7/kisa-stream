import 'package:flutter_test/flutter_test.dart';
import 'package:kisa_stream/core/models.dart';

void main() {
  test('episode distinguishes free and locked', () {
    final episode=KisaEpisode.fromJson({
      'id':'demo-9','number':9,'title':'Revelation','duration_seconds':75,
      'is_free':false,'is_unlocked':false,'cost_coins':10});
    expect(episode.number,9);
    expect(episode.isUnlocked,false);
    expect(episode.cost,10);
  });
  test('show preserves title and synopsis',(){
    final show=KisaShow.fromJson({'id':'one','title':'A Promise','synopsis':'Drama',
      'genre':'Romance','accent':'#FF5577','poster_url':null});
    expect(show.title,'A Promise');expect(show.genre,'Romance');
  });
}
