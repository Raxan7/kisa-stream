class KisaShow {
  final String id;
  final String title;
  final String synopsis;
  final String genre;
  final String accent;
  final String? posterUrl;
  final int? resumeEpisode;
  const KisaShow({required this.id, required this.title, required this.synopsis,
    required this.genre, required this.accent, this.posterUrl, this.resumeEpisode});

  factory KisaShow.fromJson(Map<String, dynamic> j) => KisaShow(
    id: (j['id'] ?? '').toString(), title: (j['title'] ?? '').toString(),
    synopsis: (j['synopsis'] ?? '').toString(), genre: (j['genre'] ?? 'Drama').toString(),
    accent: (j['accent'] ?? '#B83C70').toString(), posterUrl: j['poster_url'] as String?,
    resumeEpisode: (j['episode_number'] as num?)?.toInt(),
  );
}

class KisaEpisode {
  final String id;
  final int number;
  final String title;
  final int duration;
  final bool isFree;
  final bool isUnlocked;
  final int cost;
  const KisaEpisode({required this.id,required this.number,required this.title,
    required this.duration,required this.isFree,required this.isUnlocked,required this.cost});
  factory KisaEpisode.fromJson(Map<String,dynamic> j) => KisaEpisode(
    id:j['id'] as String,number:(j['number'] as num).toInt(),title:j['title'] as String,
    duration:(j['duration_seconds'] as num).toInt(),isFree:j['is_free'] == true,
    isUnlocked:j['is_unlocked'] == true,cost:(j['cost_coins'] as num).toInt());
}

class KisaDetail {
  final KisaShow show;
  final List<KisaEpisode> episodes;
  final int resume;
  final bool favourite;
  const KisaDetail({required this.show,required this.episodes,required this.resume,required this.favourite});
  factory KisaDetail.fromJson(Map<String,dynamic> j) => KisaDetail(
    show:KisaShow.fromJson(j),
    episodes:(j['episodes'] as List).map((e)=>KisaEpisode.fromJson(e as Map<String,dynamic>)).toList(),
    resume:(j['continue_episode'] as num).toInt(), favourite:j['favourite']==true);
}
