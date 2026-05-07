# Indie Streaming × Steam/Public Metrics Exploratory Pipeline

## 研究目的
このリポジトリは、インディーズゲームの実況・配信露出（YouTube/Twitch）と、Steam上の公開指標・公表DL数などの推移を探索的に比較するためのデータ収集・整形パイプラインです。

対象ケースは以下です。

- **Suika Game**: Steam中心の分析対象ではなく、Nintendo Switch、iOS、Android、Apple Arcade等を含むマルチプラットフォーム事例として扱います。
- **The Exit 8**: Steamレビュー・Steam公開指標を観測できる anomaly_walk 事例として扱います。
- **Chilla's Art系タイトル（サンプルでは The Closing Shift）**: Steamレビュー・Steam公開指標を観測できる story_short/ホラー実況事例として扱います。

このパイプラインは**売上推定ではなく、公開指標による探索的分析**を目的とします。Steamレビュー数は売上の代理変数になり得ますが、**売上そのものではありません**。また、コンソール版やモバイル版の販売数・収益は原則として取得困難です。公式発表や報道ベースの販売本数・DL数・収益情報がある場合のみ、`manual_sales_events.csv` に記録して補助的に利用します。

## 対象ゲームの選定基準
`target_games.csv` で各ケースのメタデータを管理します。主な列は以下です。

- `game_title`
- `steam_appid`
- `case_group`
- `category`
- `platform_notes`
- `include_flag`
- `exclusion_reason`
- `primary_platform`
- `available_platforms`
- `steam_observable_flag`
- `mobile_observable_flag`
- `console_observable_flag`
- `sales_data_type`
- `indie_flag`
- `pvp_flag`
- `publisher_type`

`category` は、`story_short`, `puzzle`, `anomaly_walk`, `tower_defense`, `roguelite`, `simulation_light`, `other` などを想定します。

`sales_data_type` は以下の値を想定します。

- `steam_review_proxy`
- `public_download_report`
- `mobile_revenue_estimate`
- `official_announcement`
- `unknown`

## 除外基準
以下のいずれかに該当するゲームは `event_study_dataset.csv` から除外します。

- `indie_flag != true`
- `pvp_flag == true`
- `publisher_type == major`
- `steam_appid` が空
- `include_flag != true`

除外されたゲームと理由は `excluded_games.csv` に出力されます。Suika Game はSteam中心ではないため `steam_appid` を空にし、`case_study_timeseries.csv` では扱いますが、Steam event study からは除外します。

## 入力CSV仕様

### `target_games.csv`
ケーススタディ対象ゲームと除外制御のマスタです。

### `sample_youtube_videos.csv` / `youtube_videos.csv`
ゲーム起点で収集したYouTube動画メタデータです。サンプル実行では `sample_youtube_videos.csv` を正規化して `youtube_videos.csv` を作成します。

### `sample_twitch_vod_metadata.csv` / `twitch_vod_metadata.csv`
ゲーム起点で収集したTwitch VODメタデータです。`streamer_login_list.csv` は任意であり、本サンプルでは必須にしていません。

### `sample_steam_reviews_raw.csv`
Steamレビューのローデータのサンプルです。`collect_steam_reviews_daily.py` が日別に集計します。

### `sample_steam_public_metrics.csv`
Steam公開指標のサンプルです。`collect_steam_public_metrics.py` はSteam reviews endpointやSteam current players APIから取得可能な範囲を取得する設計ですが、通常のサンプル実行では安定性のためこのサンプルCSVを利用します。SteamDBのfollowersや24h peakなど、スクレイピングが規約・技術的に難しい項目は取得不可または手入力扱いにし、品質レポートのnotesに記録します。

### `manual_sales_events.csv`
公式発表・報道ベースのDL数・収益情報を記録するテンプレートです。

列:

- `game_title`
- `date`
- `reported_sales_or_downloads`
- `reported_revenue`
- `platform`
- `source_url`
- `source_type`
- `notes`

## 出力CSV仕様

- `steam_reviews_daily.csv`: `review_created_date`, `daily_review_count`, `daily_positive_count`, `daily_negative_count`, `cumulative_review_count` を含むSteam日別レビュー集計。
- `steam_public_metrics.csv`: `appid`, `date`, `review_count_total`, `positive_review_count`, `negative_review_count`, `review_score_percent`, `current_players`, `peak_players_24h`, `followers`, `source_url`, `collected_at` を含む公開指標。
- `youtube_videos.csv`: YouTube動画の正規化結果。
- `twitch_vod_metadata.csv`: Twitch VODの正規化結果。
- `case_study_timeseries.csv`: `game_title × date` の可視化用時系列。YouTube/Twitch件数、レビュー日次・累積、Steamプレイヤー数、公表DL/収益情報を含みます。
- `event_study_dataset.csv`: 各動画・配信を `event_day = 0` とする `-14` から `+14` のイベントスタディ用データ。Steam event study対象外のSuika Gameは含みません。
- `data_quality_report.csv`: 各ゲームのYouTube/Twitch/Steamレビュー/公開指標の有無、event window coverage、missing days、notesを含みます。
- `excluded_games.csv`: event studyから除外したゲームと理由。
- `unmatched_game_titles.csv`: タイトル結合できなかった動画。

## 実行順序
`python run_pipeline.py` は以下の順に実行します。

1. `target_games.csv` の読み込み
2. 除外条件の適用
3. Steamレビュー日別集計
4. Steam公開指標の取得またはサンプル読込
5. YouTube/Twitchデータの正規化
6. `case_study_timeseries.csv` の作成
7. `event_study_dataset.csv` の作成
8. `data_quality_report.csv` の作成

## 実行方法

```bash
python -m pip install -r requirements.txt
python run_pipeline.py
```

## 実データへの切替
実データ投入時は、以下のサンプルCSVを同じ列仕様の実データへ差し替えてください。

- `sample_youtube_videos.csv`
- `sample_twitch_vod_metadata.csv`
- `sample_steam_reviews_raw.csv`
- `sample_steam_public_metrics.csv`（または `collect_steam_public_metrics.py --fetch-live` を利用）
- `manual_sales_events.csv`


## 実データ取得モード

サンプルCSVではなく実際の公開API/エンドポイントから取得する場合は、`run_pipeline.py` の source オプションを切り替えます。

### Steamのみ実取得する
Steam reviews endpoint と Steam current players API はAPIキーなしで取得できます。以下はSteamレビュー直近ページとSteam公開指標を実取得し、YouTube/Twitchは手元CSVまたはサンプルのまま使う例です。

```bash
python run_pipeline.py \
  --steam-reviews-source api \
  --max-steam-review-pages 5 \
  --steam-public-source api
```

注意: SteamレビューAPIから取得できるレビューはページング範囲に依存します。過去全期間の日別系列を厳密に作る場合は、十分なページ数を指定するか、別途蓄積済みCSVを `--steam-reviews-source csv --steam-reviews-raw <path>` で渡してください。

### YouTubeを実取得する
YouTube Data API v3 のAPIキーを `YOUTUBE_API_KEY` に設定してから実行します。検索クエリは `target_games.csv` の `search_keywords` をゲーム起点で利用します。

```bash
export YOUTUBE_API_KEY="<your_api_key>"
python run_pipeline.py \
  --youtube-source api \
  --youtube-published-after 2023-01-01T00:00:00Z \
  --max-videos-per-game 25
```

### Twitchを実取得する
Twitch Helix API の `TWITCH_CLIENT_ID` と `TWITCH_CLIENT_SECRET` を設定してから実行します。ゲームカテゴリ検索後、該当カテゴリのarchive VODを取得します。

```bash
export TWITCH_CLIENT_ID="<your_client_id>"
export TWITCH_CLIENT_SECRET="<your_client_secret>"
python run_pipeline.py \
  --twitch-source api \
  --max-twitch-vods-per-game 25
```

### 全体を実取得寄りで実行する
YouTube/Twitchの認証情報がある場合は、以下のように同時に切り替えられます。

```bash
python run_pipeline.py \
  --steam-reviews-source api \
  --max-steam-review-pages 5 \
  --steam-public-source api \
  --youtube-source api \
  --twitch-source api
```

### 既存の実データCSVを使う
APIで直接取得せず、外部で作成したCSVを投入する場合は `csv` source を使います。

```bash
python run_pipeline.py \
  --steam-reviews-source csv --steam-reviews-raw steam_reviews_raw.csv \
  --steam-public-source csv --steam-public-metrics-input steam_public_metrics_raw.csv \
  --youtube-source csv --youtube-raw-input youtube_raw.csv \
  --twitch-source csv --twitch-raw-input twitch_raw.csv
```

`youtube_raw.csv` と `twitch_raw.csv` は `platform, channel_name, title, raw_game_title, published_at, view_count, url` 列を持つ必要があります。

## 注意: 因果効果を断定しない
本パイプラインは、実況・配信露出と公開指標の時系列的な共変動を探索するためのものです。広告、セール、アップデート、SNS拡散、ランキング掲載、プラットフォーム差など多くの交絡要因があるため、分析結果から因果効果は断定しません。

## GitHub保存手順

```bash
git add .
git commit -m "Extend case-study pipeline with Steam public metrics"
git push
```
