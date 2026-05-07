import pandas as pd


FILTER_COLUMNS = ["indie_flag", "pvp_flag", "publisher_type", "steam_appid"]
EVENT_OUTPUT_COLUMNS = [
    "platform",
    "channel_name",
    "title",
    "game_title",
    "steam_appid",
    "case_group",
    "category",
    "published_at",
    "event_day",
    "date",
    "daily_review_count",
    "cumulative_review_count",
    "review_score_percent",
    "current_players",
    "peak_players_24h",
    "view_count",
    "url",
]


def truthy(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def exclusion_reason(row: pd.Series) -> str:
    reasons = []
    if not truthy(row.get("indie_flag")):
        reasons.append("indie_flag_not_true")
    if truthy(row.get("pvp_flag")):
        reasons.append("pvp_flag_true")
    if str(row.get("publisher_type", "")).strip().lower() == "major":
        reasons.append("publisher_type_major")
    if pd.isna(row.get("steam_appid")) or str(row.get("steam_appid", "")).strip() == "":
        reasons.append("missing_steam_appid")
    if not truthy(row.get("include_flag", True)):
        reasons.append("include_flag_not_true")
    if row.get("exclusion_reason") and pd.notna(row.get("exclusion_reason")):
        reasons.append(str(row.get("exclusion_reason")))
    return ";".join(dict.fromkeys(reasons))


def prepare_target_games(path: str):
    target_games = pd.read_csv(path)
    missing = [column for column in FILTER_COLUMNS if column not in target_games.columns]
    if missing:
        raise ValueError(f"target_games.csv missing columns: {missing}")

    target_games["_exclude_reason"] = target_games.apply(exclusion_reason, axis=1)
    included = target_games[target_games["_exclude_reason"] == ""].copy()
    excluded = target_games[target_games["_exclude_reason"] != ""].copy()
    excluded["exclusion_reason"] = excluded["_exclude_reason"]
    included = included.drop(columns=["_exclude_reason"])
    excluded = excluded.drop(columns=["_exclude_reason"])
    excluded.to_csv("excluded_games.csv", index=False)
    return included, excluded, target_games.drop(columns=["_exclude_reason"])


def build_mapping(target_games: pd.DataFrame):
    mapping = target_games[["game_title", "steam_appid", "case_group", "category"]].drop_duplicates().copy()
    mapping.to_csv("game_title_mapping.csv", index=False)


def create_event_window(
    stream_df: pd.DataFrame,
    reviews_daily: pd.DataFrame,
    public_metrics: pd.DataFrame,
    included_games: pd.DataFrame,
    window: int = 14,
):
    included_appids = set(pd.to_numeric(included_games["steam_appid"], errors="coerce").dropna().astype(int))
    streams = stream_df.copy()
    streams["steam_appid_numeric"] = pd.to_numeric(streams["steam_appid"], errors="coerce")
    streams = streams[streams["steam_appid_numeric"].isin(included_appids)].copy()

    reviews = reviews_daily.copy()
    reviews["steam_appid"] = pd.to_numeric(reviews["steam_appid"], errors="coerce")
    reviews["date"] = pd.to_datetime(reviews["review_created_date"], errors="coerce").dt.normalize()

    metrics = public_metrics.copy()
    metrics["appid"] = pd.to_numeric(metrics["appid"], errors="coerce")
    metrics = metrics.sort_values(["appid", "date"]).drop_duplicates("appid", keep="last")
    metric_cols = ["appid", "review_score_percent", "current_players", "peak_players_24h"]

    records = []
    for _, row in streams.iterrows():
        published_at = pd.to_datetime(row["published_at"]).normalize()
        appid = int(row["steam_appid_numeric"])
        metric_match = metrics[metrics["appid"] == appid][metric_cols]
        metric_values = metric_match.iloc[0].to_dict() if not metric_match.empty else {}
        for event_day in range(-window, window + 1):
            event_date = published_at + pd.Timedelta(days=event_day)
            review_match = reviews[(reviews["steam_appid"] == appid) & (reviews["date"] == event_date)]
            review_values = review_match.iloc[0].to_dict() if not review_match.empty else {}
            records.append({
                "platform": row["platform"],
                "channel_name": row["channel_name"],
                "title": row["title"],
                "game_title": row["game_title"],
                "steam_appid": appid,
                "case_group": row["case_group"],
                "category": row["category"],
                "published_at": row["published_at"],
                "event_day": event_day,
                "date": event_date.date().isoformat(),
                "daily_review_count": review_values.get("daily_review_count", pd.NA),
                "cumulative_review_count": review_values.get("cumulative_review_count", pd.NA),
                "review_score_percent": metric_values.get("review_score_percent", pd.NA),
                "current_players": metric_values.get("current_players", pd.NA),
                "peak_players_24h": metric_values.get("peak_players_24h", pd.NA),
                "view_count": row["view_count"],
                "url": row["url"],
            })
    return pd.DataFrame(records, columns=EVENT_OUTPUT_COLUMNS)


def build_category_event_summary(event_study: pd.DataFrame) -> pd.DataFrame:
    if event_study.empty:
        return pd.DataFrame(columns=["category", "event_day", "daily_review_count", "period"])
    by_day = event_study.groupby(["category", "event_day"], dropna=False)["daily_review_count"].mean().reset_index()
    by_day["period"] = "event_day"
    pre = event_study[(event_study["event_day"] >= -7) & (event_study["event_day"] <= -1)].groupby("category")["daily_review_count"].mean().reset_index()
    pre["event_day"] = pd.NA
    pre["period"] = "pre"
    post = event_study[(event_study["event_day"] >= 0) & (event_study["event_day"] <= 7)].groupby("category")["daily_review_count"].mean().reset_index()
    post["event_day"] = pd.NA
    post["period"] = "post"
    return pd.concat([by_day, pre, post], ignore_index=True)
