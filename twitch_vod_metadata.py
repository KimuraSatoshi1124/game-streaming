import argparse
import json
import os
import re
import urllib.parse
import urllib.request

import pandas as pd

from youtube_videos import OUTPUT_COLUMNS, RAW_COLUMNS, build_keyword_lookup, load_and_validate_target_games


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def twitch_get_json(url: str, headers: dict | None = None, data: bytes | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {}, data=data)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_twitch_app_token(client_id: str, client_secret: str) -> str:
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }).encode("utf-8")
    payload = twitch_get_json("https://id.twitch.tv/oauth2/token", data=data)
    return payload["access_token"]


def twitch_helix_get(path: str, params: dict, client_id: str, token: str) -> dict:
    url = f"https://api.twitch.tv/helix/{path}?{urllib.parse.urlencode(params)}"
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
    }
    return twitch_get_json(url, headers=headers)


def choose_search_keyword(game: pd.Series) -> str:
    if pd.notna(game.get("search_keywords")):
        return str(game["search_keywords"]).split("|")[0]
    return str(game["game_title"])


def collect_twitch_api(
    target_games_path: str,
    output_raw_path: str,
    client_id: str | None = None,
    client_secret: str | None = None,
    max_vods_per_game: int = 20,
) -> pd.DataFrame:
    client_id = client_id or os.environ.get("TWITCH_CLIENT_ID")
    client_secret = client_secret or os.environ.get("TWITCH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError("Twitch API collection requires TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET")

    token = get_twitch_app_token(client_id, client_secret)
    target_games = load_and_validate_target_games(target_games_path)
    rows = []
    for _, game in target_games.iterrows():
        query = choose_search_keyword(game)
        category_payload = twitch_helix_get("search/categories", {"query": query, "first": 1}, client_id, token)
        categories = category_payload.get("data", [])
        if not categories:
            continue
        game_id = categories[0].get("id")
        if not game_id:
            continue
        videos_payload = twitch_helix_get("videos", {
            "game_id": game_id,
            "first": min(max_vods_per_game, 100),
            "period": "all",
            "sort": "time",
            "type": "archive",
        }, client_id, token)
        for item in videos_payload.get("data", []):
            rows.append({
                "platform": "twitch",
                "channel_name": item.get("user_name"),
                "title": item.get("title"),
                "raw_game_title": game["game_title"],
                "published_at": item.get("created_at"),
                "view_count": item.get("view_count", 0),
                "url": item.get("url"),
            })
    raw = pd.DataFrame(rows, columns=RAW_COLUMNS)
    raw.to_csv(output_raw_path, index=False)
    return raw


def build_twitch_metadata(target_games_path: str, raw_input_path: str, output_path: str):
    target_games = load_and_validate_target_games(target_games_path)
    raw = pd.read_csv(raw_input_path)
    missing_raw = [column for column in RAW_COLUMNS if column not in raw.columns]
    if missing_raw:
        raise ValueError(f"raw twitch input missing columns: {missing_raw}")

    lookup = build_keyword_lookup(target_games)
    raw["match_key"] = raw["raw_game_title"].map(normalize_text)
    merged = raw.merge(lookup, on="match_key", how="left")
    merged["published_at"] = pd.to_datetime(merged["published_at"], errors="coerce")
    merged["view_count"] = pd.to_numeric(merged["view_count"], errors="coerce").fillna(0).astype(int)

    matched = merged.dropna(subset=["game_title"]).copy()
    matched["platform"] = "twitch"
    matched = matched[OUTPUT_COLUMNS]
    matched.to_csv(output_path, index=False)
    return matched


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-games", default="target_games.csv")
    parser.add_argument("--raw-input", default="sample_twitch_vod_metadata.csv")
    parser.add_argument("--output", default="twitch_vod_metadata.csv")
    parser.add_argument("--fetch-live", action="store_true")
    parser.add_argument("--raw-output", default="twitch_api_raw.csv")
    parser.add_argument("--twitch-client-id", default=None)
    parser.add_argument("--twitch-client-secret", default=None)
    parser.add_argument("--max-vods-per-game", type=int, default=20)
    args = parser.parse_args()

    raw_input = args.raw_input
    if args.fetch_live:
        collect_twitch_api(
            args.target_games,
            args.raw_output,
            args.twitch_client_id,
            args.twitch_client_secret,
            args.max_vods_per_game,
        )
        raw_input = args.raw_output
    build_twitch_metadata(args.target_games, raw_input, args.output)
