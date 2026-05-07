import pandas as pd

from collect_steam_public_metrics import collect_steam_public_metrics
from collect_steam_reviews_daily import collect_steam_reviews_daily
from event_study import build_category_event_summary, build_mapping, create_event_window, prepare_target_games
from twitch_vod_metadata import build_twitch_metadata
from youtube_videos import build_youtube_videos


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


def main():
    included_games, excluded_games, target_games = prepare_target_games("target_games.csv")
    build_mapping(target_games)

    reviews_daily = collect_steam_reviews_daily(
        target_games_path="target_games.csv",
        raw_reviews_path="sample_steam_reviews_raw.csv",
        output_path="steam_reviews_daily.csv",
        fetch_live=False,
    )
    public_metrics = collect_steam_public_metrics(
        target_games_path="target_games.csv",
        sample_metrics_path="sample_steam_public_metrics.csv",
        output_path="steam_public_metrics.csv",
        fetch_live=False,
    )

    youtube, _ = build_youtube_videos("target_games.csv", "sample_youtube_videos.csv", "youtube_videos.csv", max_videos_per_game=20)
    twitch = build_twitch_metadata("target_games.csv", "sample_twitch_vod_metadata.csv", "twitch_vod_metadata.csv")
    manual_sales = pd.read_csv("manual_sales_events.csv")

    case_timeseries = make_case_study_timeseries(target_games, youtube, twitch, reviews_daily, public_metrics, manual_sales)
    case_timeseries.to_csv("case_study_timeseries.csv", index=False)

    streams = pd.concat([youtube, twitch], ignore_index=True)
    event_study = create_event_window(streams, reviews_daily, public_metrics, included_games, window=14)
    event_study.to_csv("event_study_dataset.csv", index=False)

    category_summary = build_category_event_summary(event_study)
    category_summary.to_csv("category_event_summary.csv", index=False)

    data_quality = make_data_quality_report(target_games, youtube, twitch, reviews_daily, public_metrics, event_study)
    data_quality.to_csv("data_quality_report.csv", index=False)

    print("Pipeline completed")
    print("Outputs:")
    for output in [
        "excluded_games.csv",
        "game_title_mapping.csv",
        "steam_reviews_daily.csv",
        "steam_public_metrics.csv",
        "youtube_videos.csv",
        "twitch_vod_metadata.csv",
        "case_study_timeseries.csv",
        "event_study_dataset.csv",
        "category_event_summary.csv",
        "data_quality_report.csv",
        "unmatched_game_titles.csv",
    ]:
        print(f"- {output}")
    print("\nData quality report:")
    print(data_quality.to_string(index=False))


if __name__ == "__main__":
    main()
