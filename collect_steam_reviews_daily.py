import argparse
import json
import time
import urllib.parse
import urllib.request

import pandas as pd


def truthy(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def aggregate_reviews(raw_reviews: pd.DataFrame, target_games: pd.DataFrame) -> pd.DataFrame:
    required = ["steam_appid", "review_created_date", "voted_up"]
    missing = [column for column in required if column not in raw_reviews.columns]
    if missing:
        raise ValueError(f"raw review input missing columns: {missing}")

    reviews = raw_reviews.copy()
    reviews["steam_appid"] = pd.to_numeric(reviews["steam_appid"], errors="coerce")
    reviews["review_created_date"] = pd.to_datetime(reviews["review_created_date"], errors="coerce").dt.date
    reviews["voted_up_bool"] = reviews["voted_up"].map(truthy)
    reviews = reviews.dropna(subset=["steam_appid", "review_created_date"])

    daily = (
        reviews.groupby(["steam_appid", "review_created_date"], dropna=False)
        .agg(
            daily_review_count=("voted_up_bool", "size"),
            daily_positive_count=("voted_up_bool", "sum"),
        )
        .reset_index()
    )
    daily["daily_negative_count"] = daily["daily_review_count"] - daily["daily_positive_count"]

    frames = []
    for _, game in target_games.dropna(subset=["steam_appid"]).iterrows():
        appid = pd.to_numeric(game["steam_appid"], errors="coerce")
        if pd.isna(appid):
            continue
        app_reviews = daily[daily["steam_appid"] == appid].copy()
        if app_reviews.empty:
            continue
        all_dates = pd.date_range(app_reviews["review_created_date"].min(), app_reviews["review_created_date"].max(), freq="D")
        calendar = pd.DataFrame({"review_created_date": all_dates.date, "steam_appid": appid})
        app_reviews = calendar.merge(app_reviews, on=["steam_appid", "review_created_date"], how="left")
        for column in ["daily_review_count", "daily_positive_count", "daily_negative_count"]:
            app_reviews[column] = app_reviews[column].fillna(0).astype(int)
        app_reviews["cumulative_review_count"] = app_reviews["daily_review_count"].cumsum()
        app_reviews["game_title"] = game["game_title"]
        frames.append(app_reviews)

    if not frames:
        return pd.DataFrame(columns=[
            "steam_appid",
            "game_title",
            "review_created_date",
            "daily_review_count",
            "daily_positive_count",
            "daily_negative_count",
            "cumulative_review_count",
        ])

    output = pd.concat(frames, ignore_index=True)
    return output[[
        "steam_appid",
        "game_title",
        "review_created_date",
        "daily_review_count",
        "daily_positive_count",
        "daily_negative_count",
        "cumulative_review_count",
    ]]


def fetch_review_page(appid: int, cursor: str = "*") -> dict:
    params = urllib.parse.urlencode({
        "json": 1,
        "filter": "recent",
        "language": "all",
        "review_type": "all",
        "purchase_type": "all",
        "num_per_page": 100,
        "cursor": cursor,
    })
    url = f"https://store.steampowered.com/appreviews/{appid}?{params}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def collect_live_reviews(target_games: pd.DataFrame, max_pages_per_app: int = 3) -> pd.DataFrame:
    rows = []
    for _, game in target_games.dropna(subset=["steam_appid"]).iterrows():
        appid = int(game["steam_appid"])
        cursor = "*"
        for _ in range(max_pages_per_app):
            payload = fetch_review_page(appid, cursor)
            for review in payload.get("reviews", []):
                rows.append({
                    "steam_appid": appid,
                    "game_title": game["game_title"],
                    "review_created_date": pd.to_datetime(review.get("timestamp_created"), unit="s").date(),
                    "voted_up": review.get("voted_up"),
                })
            cursor = payload.get("cursor")
            if not cursor or not payload.get("reviews"):
                break
            time.sleep(0.2)
    return pd.DataFrame(rows)


def collect_steam_reviews_daily(
    target_games_path: str = "target_games.csv",
    raw_reviews_path: str = "sample_steam_reviews_raw.csv",
    output_path: str = "steam_reviews_daily.csv",
    fetch_live: bool = False,
) -> pd.DataFrame:
    target_games = pd.read_csv(target_games_path)
    steam_games = target_games[target_games["steam_observable_flag"].map(truthy)].copy()
    if fetch_live:
        raw_reviews = collect_live_reviews(steam_games)
    else:
        raw_reviews = pd.read_csv(raw_reviews_path)
    daily = aggregate_reviews(raw_reviews, steam_games)
    daily.to_csv(output_path, index=False)
    return daily


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-games", default="target_games.csv")
    parser.add_argument("--raw-reviews", default="sample_steam_reviews_raw.csv")
    parser.add_argument("--output", default="steam_reviews_daily.csv")
    parser.add_argument("--fetch-live", action="store_true")
    args = parser.parse_args()
    collect_steam_reviews_daily(args.target_games, args.raw_reviews, args.output, args.fetch_live)
