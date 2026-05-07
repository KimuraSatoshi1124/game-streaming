import argparse

import pandas as pd

from collect_steam_public_metrics import collect_steam_public_metrics
from collect_steam_reviews_daily import collect_steam_reviews_daily
from event_study import build_category_event_summary, build_mapping, create_event_window, prepare_target_games
from twitch_vod_metadata import build_twitch_metadata, collect_twitch_api
from youtube_videos import build_youtube_videos, collect_youtube_api


def normalize_date_column(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(df[column], errors="coerce").dt.date.astype("string")


def make_case_study_timeseries(
    target_games: pd.DataFrame,
    youtube: pd.DataFrame,
    twitch: pd.DataFrame,
    reviews_daily: pd.DataFrame,
    public_metrics: pd.DataFrame,
    manual_sales: pd.DataFrame,
) -> pd.DataFrame:
    target = target_games[target_games["include_flag"].astype(str).str.lower().isin(["true", "1", "yes"])].copy()
    frames = []
    for _, game in target.iterrows():
        dates = set()
        for df in [youtube, twitch]:
            game_media = df[df["game_title"] == game["game_title"]].copy()
            if not game_media.empty:
                dates.update(normalize_date_column(game_media, "published_at").dropna().tolist())
        if pd.notna(game.get("steam_appid")) and str(game.get("steam_appid", "")).strip():
            appid = pd.to_numeric(game["steam_appid"], errors="coerce")
            review_dates = reviews_daily[pd.to_numeric(reviews_daily["steam_appid"], errors="coerce") == appid]
            if not review_dates.empty:
                dates.update(normalize_date_column(review_dates, "review_created_date").dropna().tolist())
            metric_dates = public_metrics[pd.to_numeric(public_metrics["appid"], errors="coerce") == appid]
            if not metric_dates.empty:
                dates.update(normalize_date_column(metric_dates, "date").dropna().tolist())
        sales_dates = manual_sales[manual_sales["game_title"] == game["game_title"]]
        if not sales_dates.empty:
            dates.update(normalize_date_column(sales_dates, "date").dropna().tolist())
        if not dates:
            continue
        calendar = pd.DataFrame({"date": sorted(dates)})
        calendar["game_title"] = game["game_title"]
        calendar["case_group"] = game["case_group"]
        frames.append(calendar)

    if not frames:
        return pd.DataFrame()

    base = pd.concat(frames, ignore_index=True)

    yt_daily = youtube.copy()
    yt_daily["date"] = normalize_date_column(yt_daily, "published_at")
    yt_daily = yt_daily.groupby(["game_title", "date"]).agg(
        youtube_video_count=("url", "count"),
        youtube_view_count=("view_count", "sum"),
    ).reset_index()

    tw_daily = twitch.copy()
    tw_daily["date"] = normalize_date_column(tw_daily, "published_at")
    tw_daily = tw_daily.groupby(["game_title", "date"]).agg(
        twitch_vod_count=("url", "count"),
        twitch_view_count=("view_count", "sum"),
    ).reset_index()

    reviews = reviews_daily.copy()
    reviews["date"] = normalize_date_column(reviews, "review_created_date")
    reviews = reviews[["game_title", "date", "daily_review_count", "cumulative_review_count"]]

    metrics = public_metrics.copy()
    metrics["date"] = normalize_date_column(metrics, "date")
    appid_to_title = target_games.dropna(subset=["steam_appid"])[["steam_appid", "game_title"]].copy()
    appid_to_title["appid"] = pd.to_numeric(appid_to_title["steam_appid"], errors="coerce")
    metrics["appid"] = pd.to_numeric(metrics["appid"], errors="coerce")
    if "game_title" in metrics.columns:
        metrics = metrics.drop(columns=["game_title"])
    metrics = metrics.merge(appid_to_title[["appid", "game_title"]], on="appid", how="left")
    metrics = metrics[["game_title", "date", "current_players", "peak_players_24h"]]

    sales = manual_sales.copy()
    sales["date"] = normalize_date_column(sales, "date")
    sales = sales.rename(columns={
        "reported_sales_or_downloads": "reported_downloads",
        "reported_revenue": "reported_revenue",
        "platform": "reported_platform",
        "source_url": "report_source_url",
        "source_type": "report_source_type",
    })
    sales = sales[["game_title", "date", "reported_downloads", "reported_revenue", "reported_platform", "report_source_url", "report_source_type"]]

    output = base.merge(yt_daily, on=["game_title", "date"], how="left")
    output = output.merge(tw_daily, on=["game_title", "date"], how="left")
    output = output.merge(reviews, on=["game_title", "date"], how="left")
    output = output.merge(metrics, on=["game_title", "date"], how="left")
    output = output.merge(sales, on=["game_title", "date"], how="left")

    count_columns = ["youtube_video_count", "youtube_view_count", "twitch_vod_count", "twitch_view_count"]
    for column in count_columns:
        output[column] = output[column].fillna(0).astype(int)

    return output[[
        "game_title",
        "case_group",
        "date",
        "youtube_video_count",
        "youtube_view_count",
        "twitch_vod_count",
        "twitch_view_count",
        "daily_review_count",
        "cumulative_review_count",
        "current_players",
        "peak_players_24h",
        "reported_downloads",
        "reported_revenue",
        "reported_platform",
        "report_source_url",
        "report_source_type",
    ]].sort_values(["game_title", "date"])


def make_data_quality_report(
    target_games: pd.DataFrame,
    youtube: pd.DataFrame,
    twitch: pd.DataFrame,
    reviews_daily: pd.DataFrame,
    public_metrics: pd.DataFrame,
    event_study: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for _, game in target_games.iterrows():
        title = game["game_title"]
        appid = pd.to_numeric(game.get("steam_appid"), errors="coerce")
        game_events = event_study[event_study["game_title"] == title] if not event_study.empty else pd.DataFrame()
        expected_rows = 0
        missing_days = 0
        coverage = pd.NA
        if not game_events.empty:
            expected_rows = len(game_events)
            missing_days = int(game_events["daily_review_count"].isna().sum())
            coverage = 1 - (missing_days / expected_rows)
        has_review_data = False
        has_public_metrics = False
        if pd.notna(appid):
            has_review_data = pd.to_numeric(reviews_daily["steam_appid"], errors="coerce").eq(appid).any()
            has_public_metrics = pd.to_numeric(public_metrics["appid"], errors="coerce").eq(appid).any()
        notes = []
        if not str(game.get("steam_observable_flag", "")).lower() == "true":
            notes.append("not Steam-centered; use manual/public multi-platform indicators")
        if pd.isna(appid):
            notes.append("no steam_appid; excluded from event_study")
        if game.get("exclusion_reason") and pd.notna(game.get("exclusion_reason")):
            notes.append(str(game.get("exclusion_reason")))
        if pd.notna(appid):
            metric_rows = public_metrics[pd.to_numeric(public_metrics["appid"], errors="coerce").eq(appid)]
            followers_missing = metric_rows.empty or metric_rows.get("followers", pd.Series(dtype="object")).isna().all()
            if followers_missing:
                notes.append("SteamDB followers not scraped by default; provide manual/sample metrics if available")
        if not has_public_metrics and pd.notna(appid):
            notes.append("public Steam metrics unavailable or not collected")
        rows.append({
            "game_title": title,
            "steam_appid": game.get("steam_appid"),
            "case_group": game.get("case_group"),
            "has_youtube_data": bool((youtube["game_title"] == title).any()),
            "has_twitch_data": bool((twitch["game_title"] == title).any()),
            "has_review_daily_data": bool(has_review_data),
            "has_public_metrics_data": bool(has_public_metrics),
            "event_window_coverage_rate": coverage,
            "missing_days": missing_days if expected_rows else pd.NA,
            "notes": "; ".join(notes),
        })
    return pd.DataFrame(rows)


def raw_path_for_source(source: str, sample_path: str, csv_path: str, api_path: str) -> str:
    if source == "sample":
        return sample_path
    if source == "csv":
        return csv_path
    if source == "api":
        return api_path
    raise ValueError(f"Unsupported source: {source}")


def run_pipeline(args: argparse.Namespace) -> pd.DataFrame:
    included_games, excluded_games, target_games = prepare_target_games(args.target_games)
    build_mapping(target_games)

    reviews_daily = collect_steam_reviews_daily(
        target_games_path=args.target_games,
        raw_reviews_path=args.steam_reviews_raw,
        output_path=args.steam_reviews_daily_output,
        fetch_live=args.steam_reviews_source == "api",
        max_pages_per_app=args.max_steam_review_pages,
    )
    public_metrics = collect_steam_public_metrics(
        target_games_path=args.target_games,
        sample_metrics_path=args.steam_public_metrics_input,
        output_path=args.steam_public_metrics_output,
        fetch_live=args.steam_public_source == "api",
    )

    youtube_raw_input = raw_path_for_source(args.youtube_source, args.sample_youtube_input, args.youtube_raw_input, args.youtube_api_raw_output)
    if args.youtube_source == "api":
        collect_youtube_api(
            args.target_games,
            args.youtube_api_raw_output,
            args.youtube_api_key,
            args.max_videos_per_game,
            args.youtube_published_after,
            args.youtube_published_before,
        )
    youtube, _ = build_youtube_videos(args.target_games, youtube_raw_input, args.youtube_output, max_videos_per_game=args.max_videos_per_game)

    twitch_raw_input = raw_path_for_source(args.twitch_source, args.sample_twitch_input, args.twitch_raw_input, args.twitch_api_raw_output)
    if args.twitch_source == "api":
        collect_twitch_api(
            args.target_games,
            args.twitch_api_raw_output,
            args.twitch_client_id,
            args.twitch_client_secret,
            args.max_twitch_vods_per_game,
        )
    twitch = build_twitch_metadata(args.target_games, twitch_raw_input, args.twitch_output)
    manual_sales = pd.read_csv(args.manual_sales_events)

    case_timeseries = make_case_study_timeseries(target_games, youtube, twitch, reviews_daily, public_metrics, manual_sales)
    case_timeseries.to_csv(args.case_study_timeseries_output, index=False)

    streams = pd.concat([youtube, twitch], ignore_index=True)
    event_study = create_event_window(streams, reviews_daily, public_metrics, included_games, window=args.event_window_days)
    event_study.to_csv(args.event_study_output, index=False)

    category_summary = build_category_event_summary(event_study)
    category_summary.to_csv(args.category_event_summary_output, index=False)

    data_quality = make_data_quality_report(target_games, youtube, twitch, reviews_daily, public_metrics, event_study)
    data_quality.to_csv(args.data_quality_report_output, index=False)

    print("Pipeline completed")
    print("Outputs:")
    for output in [
        "excluded_games.csv",
        "game_title_mapping.csv",
        args.steam_reviews_daily_output,
        args.steam_public_metrics_output,
        args.youtube_output,
        args.twitch_output,
        args.case_study_timeseries_output,
        args.event_study_output,
        args.category_event_summary_output,
        args.data_quality_report_output,
        "unmatched_game_titles.csv",
    ]:
        print(f"- {output}")
    print("\nData quality report:")
    print(data_quality.to_string(index=False))
    return data_quality


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the indie streaming × public metrics pipeline.")
    parser.add_argument("--target-games", default="target_games.csv")
    parser.add_argument("--manual-sales-events", default="manual_sales_events.csv")
    parser.add_argument("--event-window-days", type=int, default=14)

    parser.add_argument("--steam-reviews-source", choices=["sample", "csv", "api"], default="sample")
    parser.add_argument("--steam-reviews-raw", default="sample_steam_reviews_raw.csv")
    parser.add_argument("--steam-reviews-daily-output", default="steam_reviews_daily.csv")
    parser.add_argument("--max-steam-review-pages", type=int, default=3)

    parser.add_argument("--steam-public-source", choices=["sample", "csv", "api"], default="sample")
    parser.add_argument("--steam-public-metrics-input", default="sample_steam_public_metrics.csv")
    parser.add_argument("--steam-public-metrics-output", default="steam_public_metrics.csv")

    parser.add_argument("--youtube-source", choices=["sample", "csv", "api"], default="sample")
    parser.add_argument("--sample-youtube-input", default="sample_youtube_videos.csv")
    parser.add_argument("--youtube-raw-input", default="youtube_raw.csv")
    parser.add_argument("--youtube-api-raw-output", default="youtube_api_raw.csv")
    parser.add_argument("--youtube-output", default="youtube_videos.csv")
    parser.add_argument("--youtube-api-key", default=None)
    parser.add_argument("--youtube-published-after", default=None)
    parser.add_argument("--youtube-published-before", default=None)
    parser.add_argument("--max-videos-per-game", type=int, default=20)

    parser.add_argument("--twitch-source", choices=["sample", "csv", "api"], default="sample")
    parser.add_argument("--sample-twitch-input", default="sample_twitch_vod_metadata.csv")
    parser.add_argument("--twitch-raw-input", default="twitch_raw.csv")
    parser.add_argument("--twitch-api-raw-output", default="twitch_api_raw.csv")
    parser.add_argument("--twitch-output", default="twitch_vod_metadata.csv")
    parser.add_argument("--twitch-client-id", default=None)
    parser.add_argument("--twitch-client-secret", default=None)
    parser.add_argument("--max-twitch-vods-per-game", type=int, default=20)

    parser.add_argument("--case-study-timeseries-output", default="case_study_timeseries.csv")
    parser.add_argument("--event-study-output", default="event_study_dataset.csv")
    parser.add_argument("--category-event-summary-output", default="category_event_summary.csv")
    parser.add_argument("--data-quality-report-output", default="data_quality_report.csv")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    run_pipeline(args)


if __name__ == "__main__":
    main()
