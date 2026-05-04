import argparse
import pandas as pd


def normalize_text(s: str) -> str:
    return str(s).strip().lower()


def load_and_validate_target_games(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = [
        "steam_appid", "canonical_game_title", "search_keywords", "game_category",
        "indie_flag", "pvp_flag", "publisher_type", "release_date", "note"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"target_games.csv missing columns: {missing}")
    return df


def build_youtube_videos(target_games_path: str, raw_input_path: str, output_path: str, max_videos_per_game: int = 50):
    tg = load_and_validate_target_games(target_games_path)
    raw = pd.read_csv(raw_input_path)
    required_raw = ["platform", "channel_name", "title", "raw_game_title", "published_at", "view_count", "url"]
    miss_raw = [c for c in required_raw if c not in raw.columns]
    if miss_raw:
        raise ValueError(f"raw youtube input missing columns: {miss_raw}")

    tg["canonical_norm"] = tg["canonical_game_title"].map(normalize_text)
    raw["raw_norm"] = raw["raw_game_title"].map(normalize_text)

    merged = raw.merge(
        tg[["steam_appid", "canonical_game_title", "canonical_norm", "game_category", "search_keywords"]],
        left_on="raw_norm",
        right_on="canonical_norm",
        how="left"
    )

    merged["published_at"] = pd.to_datetime(merged["published_at"], errors="coerce")
    merged["view_count"] = pd.to_numeric(merged["view_count"], errors="coerce").fillna(0).astype(int)

    matched = merged.dropna(subset=["steam_appid"]).copy()
    matched = matched.sort_values(["canonical_game_title", "published_at", "view_count"], ascending=[True, False, False])
    matched = matched.groupby("canonical_game_title", as_index=False, group_keys=False).head(max_videos_per_game)

    matched = matched[[
        "platform", "channel_name", "title", "raw_game_title", "canonical_game_title", "steam_appid",
        "game_category", "published_at", "view_count", "url"
    ]]
    matched.to_csv(output_path, index=False)

    unmatched = merged[merged["steam_appid"].isna()][["platform", "channel_name", "title", "raw_game_title", "published_at", "url"]]
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
