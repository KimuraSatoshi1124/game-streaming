import argparse
import re

import pandas as pd

from youtube_videos import OUTPUT_COLUMNS, build_keyword_lookup, load_and_validate_target_games


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def build_twitch_metadata(target_games_path: str, raw_input_path: str, output_path: str):
    target_games = load_and_validate_target_games(target_games_path)
    raw = pd.read_csv(raw_input_path)
    required_raw = ["platform", "channel_name", "title", "raw_game_title", "published_at", "view_count", "url"]
    missing_raw = [column for column in required_raw if column not in raw.columns]
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
    args = parser.parse_args()
    build_twitch_metadata(args.target_games, args.raw_input, args.output)
