import argparse
import pandas as pd


def normalize_text(s: str) -> str:
    return str(s).strip().lower()


def build_twitch_metadata(target_games_path: str, raw_input_path: str, output_path: str):
    tg = pd.read_csv(target_games_path)
    raw = pd.read_csv(raw_input_path)

    tg["canonical_norm"] = tg["canonical_game_title"].map(normalize_text)
    raw["raw_norm"] = raw["raw_game_title"].map(normalize_text)

    merged = raw.merge(
        tg[["steam_appid", "canonical_game_title", "canonical_norm", "game_category"]],
        left_on="raw_norm",
        right_on="canonical_norm",
        how="left"
    )
    merged["published_at"] = pd.to_datetime(merged["published_at"], errors="coerce")
    merged["view_count"] = pd.to_numeric(merged["view_count"], errors="coerce").fillna(0).astype(int)

    matched = merged.dropna(subset=["steam_appid"])[[
        "platform", "channel_name", "title", "raw_game_title", "canonical_game_title", "steam_appid",
        "game_category", "published_at", "view_count", "url"
    ]]
    matched.to_csv(output_path, index=False)
    return matched


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-games", default="target_games.csv")
    parser.add_argument("--raw-input", default="sample_twitch_vod_metadata.csv")
    parser.add_argument("--output", default="twitch_vod_metadata.csv")
    args = parser.parse_args()
    build_twitch_metadata(args.target_games, args.raw_input, args.output)
