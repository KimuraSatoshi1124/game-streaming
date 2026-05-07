import argparse
import json
import os
import re
import urllib.parse
import urllib.request

import pandas as pd


OUTPUT_COLUMNS = [
    "platform",
    "channel_name",
    "title",
    "raw_game_title",
    "game_title",
    "steam_appid",
    "case_group",
    "category",
    "published_at",
    "view_count",
    "url",
]
RAW_COLUMNS = ["platform", "channel_name", "title", "raw_game_title", "published_at", "view_count", "url"]


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def load_and_validate_target_games(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = [
        "game_title",
        "steam_appid",
        "case_group",
        "category",
        "search_keywords",
        "include_flag",
        "indie_flag",
        "pvp_flag",
        "publisher_type",
    ]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"target_games.csv missing columns: {missing}")
    return df


def build_keyword_lookup(target_games: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, game in target_games.iterrows():
        keywords = [game["game_title"]]
        if pd.notna(game.get("search_keywords")):
            keywords.extend(str(game["search_keywords"]).split("|"))
        for keyword in keywords:
            rows.append({"match_key": normalize_text(keyword), **game.to_dict()})
    return pd.DataFrame(rows).drop_duplicates(subset=["match_key"])


def youtube_get_json(path: str, params: dict) -> dict:
    encoded = urllib.parse.urlencode(params)
    url = f"https://www.googleapis.com/youtube/v3/{path}?{encoded}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def choose_search_keyword(game: pd.Series) -> str:
    if pd.notna(game.get("search_keywords")):
        return str(game["search_keywords"]).split("|")[0]
    return str(game["game_title"])


def collect_youtube_api(
    target_games_path: str,
    output_raw_path: str,
    api_key: str | None = None,
    max_videos_per_game: int = 25,
    published_after: str | None = None,
    published_before: str | None = None,
) -> pd.DataFrame:
    api_key = api_key or os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("YouTube API collection requires YOUTUBE_API_KEY or --youtube-api-key")

    target_games = load_and_validate_target_games(target_games_path)
    rows = []
    for _, game in target_games.iterrows():
        query = choose_search_keyword(game)
        search_params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(max_videos_per_game, 50),
            "order": "date",
            "key": api_key,
        }
        if published_after:
            search_params["publishedAfter"] = published_after
        if published_before:
            search_params["publishedBefore"] = published_before
        search_payload = youtube_get_json("search", search_params)
        video_ids = [item["id"]["videoId"] for item in search_payload.get("items", []) if item.get("id", {}).get("videoId")]
        stats_by_id = {}
        if video_ids:
            stats_payload = youtube_get_json("videos", {
                "part": "statistics",
                "id": ",".join(video_ids),
                "key": api_key,
            })
            stats_by_id = {
                item["id"]: item.get("statistics", {})
                for item in stats_payload.get("items", [])
            }
        for item in search_payload.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            snippet = item.get("snippet", {})
            stats = stats_by_id.get(video_id, {})
            rows.append({
                "platform": "youtube",
                "channel_name": snippet.get("channelTitle"),
                "title": snippet.get("title"),
                "raw_game_title": game["game_title"],
                "published_at": snippet.get("publishedAt"),
                "view_count": stats.get("viewCount", 0),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })
    raw = pd.DataFrame(rows, columns=RAW_COLUMNS)
    raw.to_csv(output_raw_path, index=False)
    return raw


def build_youtube_videos(
    target_games_path: str,
    raw_input_path: str,
    output_path: str,
    max_videos_per_game: int = 50,
):
    target_games = load_and_validate_target_games(target_games_path)
    raw = pd.read_csv(raw_input_path)
    missing_raw = [column for column in RAW_COLUMNS if column not in raw.columns]
    if missing_raw:
        raise ValueError(f"raw youtube input missing columns: {missing_raw}")

    lookup = build_keyword_lookup(target_games)
    raw["match_key"] = raw["raw_game_title"].map(normalize_text)
    merged = raw.merge(lookup, on="match_key", how="left")

    merged["published_at"] = pd.to_datetime(merged["published_at"], errors="coerce")
    merged["view_count"] = pd.to_numeric(merged["view_count"], errors="coerce").fillna(0).astype(int)

    matched = merged.dropna(subset=["game_title"]).copy()
    matched = matched.sort_values(["game_title", "published_at", "view_count"], ascending=[True, False, False])
    matched = matched.groupby("game_title", as_index=False, group_keys=False).head(max_videos_per_game)
    matched["platform"] = "youtube"
    matched = matched[OUTPUT_COLUMNS]
    matched.to_csv(output_path, index=False)

    unmatched = merged[merged["game_title"].isna()][["platform", "channel_name", "title", "raw_game_title", "published_at", "url"]]
    unmatched.to_csv("unmatched_game_titles.csv", index=False)
    return matched, unmatched


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-games", default="target_games.csv")
    parser.add_argument("--raw-input", default="sample_youtube_videos.csv")
    parser.add_argument("--output", default="youtube_videos.csv")
    parser.add_argument("--max-videos-per-game", type=int, default=50)
    parser.add_argument("--fetch-live", action="store_true")
    parser.add_argument("--raw-output", default="youtube_api_raw.csv")
    parser.add_argument("--youtube-api-key", default=None)
    parser.add_argument("--published-after", default=None)
    parser.add_argument("--published-before", default=None)
    args = parser.parse_args()

    raw_input = args.raw_input
    if args.fetch_live:
        collect_youtube_api(
            args.target_games,
            args.raw_output,
            args.youtube_api_key,
            args.max_videos_per_game,
            args.published_after,
            args.published_before,
        )
        raw_input = args.raw_output
    build_youtube_videos(args.target_games, raw_input, args.output, args.max_videos_per_game)
