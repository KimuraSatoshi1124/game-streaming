import argparse
import re

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


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def truthy(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


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


def build_youtube_videos(
    target_games_path: str,
    raw_input_path: str,
    output_path: str,
    max_videos_per_game: int = 50,
):
    target_games = load_and_validate_target_games(target_games_path)
    raw = pd.read_csv(raw_input_path)
    required_raw = ["platform", "channel_name", "title", "raw_game_title", "published_at", "view_count", "url"]
    missing_raw = [column for column in required_raw if column not in raw.columns]
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
    args = parser.parse_args()
    build_youtube_videos(args.target_games, args.raw_input, args.output, args.max_videos_per_game)
