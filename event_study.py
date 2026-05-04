import pandas as pd


def prepare_target_games(path: str):
    tg = pd.read_csv(path)
    excluded = tg[(tg["indie_flag"] != True) | (tg["pvp_flag"] != False) | (tg["publisher_type"] == "major") | (tg["steam_appid"].isna())].copy()
    included = tg[(tg["indie_flag"] == True) & (tg["pvp_flag"] == False) & (tg["publisher_type"] != "major") & (~tg["steam_appid"].isna())].copy()
    excluded.to_csv("excluded_games.csv", index=False)
    return included, excluded


def build_mapping(target_games: pd.DataFrame):
    mapping = target_games[["canonical_game_title", "steam_appid"]].drop_duplicates().copy()
    mapping.to_csv("game_title_mapping.csv", index=False)


def prepare_reviews(path: str):
    rv = pd.read_csv(path)
    rv["date"] = pd.to_datetime(rv["date"])
    rv = rv.sort_values(["steam_appid", "date"])
    rv["review_diff"] = rv.groupby("steam_appid")["review_count"].diff().fillna(0)
    return rv


def create_event_window(stream_df: pd.DataFrame, reviews_df: pd.DataFrame, window: int = 14):
    records = []
    for _, row in stream_df.iterrows():
        pub = pd.to_datetime(row["published_at"]).normalize()
        for d in range(-window, window + 1):
            target_date = pub + pd.Timedelta(days=d)
            match = reviews_df[(reviews_df["steam_appid"] == row["steam_appid"]) & (reviews_df["date"] == target_date)]
            if match.empty:
                rec = {
                    **{k: row[k] for k in ["platform", "channel_name", "title", "canonical_game_title", "steam_appid", "game_category", "published_at", "view_count", "url"]},
                    "event_day": d,
                    "date": target_date,
                    "review_count": pd.NA,
                    "review_diff": pd.NA,
                }
            else:
                m = match.iloc[0]
                rec = {
                    **{k: row[k] for k in ["platform", "channel_name", "title", "canonical_game_title", "steam_appid", "game_category", "published_at", "view_count", "url"]},
                    "event_day": d,
                    "date": target_date,
                    "review_count": m["review_count"],
                    "review_diff": m["review_diff"],
                }
            records.append(rec)
    return pd.DataFrame(records)
