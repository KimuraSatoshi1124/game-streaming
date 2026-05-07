import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd


def truthy(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_review_summary(appid: int) -> dict:
    params = urllib.parse.urlencode({
        "json": 1,
        "filter": "summary",
        "language": "all",
        "review_type": "all",
        "purchase_type": "all",
        "num_per_page": 0,
    })
    return fetch_json(f"https://store.steampowered.com/appreviews/{appid}?{params}")


def fetch_current_players(appid: int) -> dict:
    return fetch_json(f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}")


def parse_live_metrics(appid: int, game_title: str) -> dict:
    collected_at = datetime.now(timezone.utc).isoformat()
    source_url = f"https://store.steampowered.com/app/{appid}"
    notes = []
    review_count_total = pd.NA
    positive_review_count = pd.NA
    negative_review_count = pd.NA
    review_score_percent = pd.NA
    current_players = pd.NA

    try:
        summary = fetch_review_summary(appid).get("query_summary", {})
        review_count_total = summary.get("total_reviews", pd.NA)
        positive_review_count = summary.get("total_positive", pd.NA)
        negative_review_count = summary.get("total_negative", pd.NA)
        review_score_percent = summary.get("review_score", pd.NA)
    except Exception as exc:
        notes.append(f"review_summary_unavailable:{exc.__class__.__name__}")

    try:
        current_players = fetch_current_players(appid).get("response", {}).get("player_count", pd.NA)
    except Exception as exc:
        notes.append(f"current_players_unavailable:{exc.__class__.__name__}")

    notes.append("SteamDB followers and 24h peak are not scraped by default; provide sample/manual metrics if needed")
    return {
        "appid": appid,
        "game_title": game_title,
        "date": datetime.now(timezone.utc).date().isoformat(),
        "review_count_total": review_count_total,
        "positive_review_count": positive_review_count,
        "negative_review_count": negative_review_count,
        "review_score_percent": review_score_percent,
        "current_players": current_players,
        "peak_players_24h": pd.NA,
        "followers": pd.NA,
        "source_url": source_url,
        "collected_at": collected_at,
        "notes": "; ".join(notes),
    }


def collect_steam_public_metrics(
    target_games_path: str = "target_games.csv",
    sample_metrics_path: str = "sample_steam_public_metrics.csv",
    output_path: str = "steam_public_metrics.csv",
    fetch_live: bool = False,
) -> pd.DataFrame:
    target_games = pd.read_csv(target_games_path)
    steam_games = target_games[target_games["steam_observable_flag"].map(truthy)].dropna(subset=["steam_appid"])

    if fetch_live:
        rows = []
        for _, game in steam_games.iterrows():
            rows.append(parse_live_metrics(int(game["steam_appid"]), game["game_title"]))
            time.sleep(0.2)
        metrics = pd.DataFrame(rows)
    else:
        metrics = pd.read_csv(sample_metrics_path)
        metrics = metrics.rename(columns={"appid": "appid"})
        metrics["notes"] = metrics.get("notes", "sample/offline metrics; SteamDB followers unavailable unless supplied")

    required = [
        "appid",
        "date",
        "review_count_total",
        "positive_review_count",
        "negative_review_count",
        "review_score_percent",
        "current_players",
        "peak_players_24h",
        "followers",
        "source_url",
        "collected_at",
        "notes",
    ]
    for column in required:
        if column not in metrics.columns:
            metrics[column] = pd.NA
    metrics.to_csv(output_path, index=False)
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-games", default="target_games.csv")
    parser.add_argument("--sample-metrics", default="sample_steam_public_metrics.csv")
    parser.add_argument("--output", default="steam_public_metrics.csv")
    parser.add_argument("--fetch-live", action="store_true")
    args = parser.parse_args()
    collect_steam_public_metrics(args.target_games, args.sample_metrics, args.output, args.fetch_live)
