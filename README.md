# Indieゲーム実況・配信 × Steamレビュー探索パイプライン

## 研究目的
インディーズゲームにおける実況/配信露出とSteamレビュー数変化の関係を**探索的**に確認するためのパイプラインです。因果効果の断定は行いません。

## 対象ゲームの選定基準
- indie_flag == true
- pvp_flag == false
- publisher_type != major
- steam_appid が存在

## 除外基準
- AAAタイトル
- 大手パブリッシャー作品
- PvP中心作品
- eスポーツ系作品

## game_category 定義
- story_short
- puzzle
- anomaly_walk
- tower_defense
- roguelite
- simulation_light
- other

## 入力CSV仕様
- `target_games.csv`
- `youtube_videos.csv`（通常運用時。サンプル実行では `sample_youtube_videos.csv`）
- `twitch_vod_metadata.csv`（通常運用時。サンプル実行では `sample_twitch_vod_metadata.csv`）
- `steam_reviews.csv`（通常運用時。サンプル実行では `sample_steam_reviews.csv`）

## 出力CSV仕様
- `youtube_videos.csv`
- `twitch_vod_metadata.csv`
- `steam_reviews_prepared.csv`
- `game_title_mapping.csv`
- `excluded_games.csv`
- `unmatched_game_titles.csv`
- `event_study_dataset.csv`
- `data_quality_report.csv`
- `category_event_summary.csv`

## 実行方法
```bash
python run_pipeline.py
```

## 実データへの切替
`run_pipeline.py` 内の入力ファイル名を以下に差し替えてください。
- `sample_youtube_videos.csv` → `youtube_videos.csv`（raw）
- `sample_twitch_vod_metadata.csv` → `twitch_vod_metadata.csv`（raw）
- `sample_steam_reviews.csv` → `steam_reviews.csv`

## GitHub保存手順
```bash
git add .
git commit -m "Add exploratory pipeline for indie streaming and Steam reviews"
git push
```

## 注意
本パイプラインの出力は探索的分析のためのもので、実況・配信が売上/レビューに与える因果効果を断定するものではありません。
