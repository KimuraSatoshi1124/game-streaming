import pandas as pd
from youtube_videos import build_youtube_videos
from twitch_vod_metadata import build_twitch_metadata
from event_study import prepare_target_games, build_mapping, prepare_reviews, create_event_window


def main():
    included, excluded = prepare_target_games("target_games.csv")
    build_mapping(included)

    build_youtube_videos("target_games.csv", "sample_youtube_videos.csv", "youtube_videos.csv", max_videos_per_game=20)
    build_twitch_metadata("target_games.csv", "sample_twitch_vod_metadata.csv", "twitch_vod_metadata.csv")

    yt = pd.read_csv("youtube_videos.csv")
    tw = pd.read_csv("twitch_vod_metadata.csv")
    videos = pd.concat([yt, tw], ignore_index=True)
    videos["published_at"] = pd.to_datetime(videos["published_at"])

    reviews = prepare_reviews("sample_steam_reviews.csv")
    reviews.to_csv("steam_reviews_prepared.csv", index=False)

    ev = create_event_window(videos, reviews, window=14)
    ev.to_csv("event_study_dataset.csv", index=False)

    complete_flags = ev.groupby(["platform", "channel_name", "title", "canonical_game_title", "steam_appid"])["review_count"].apply(lambda x: x.notna().all())
    complete_cnt = complete_flags.sum()
    total_events = ev.groupby(["platform", "channel_name", "title", "canonical_game_title", "steam_appid"]).ngroups

    dq = {
        "入力動画数": [len(pd.read_csv("sample_youtube_videos.csv")) + len(pd.read_csv("sample_twitch_vod_metadata.csv"))],
        "対象ゲーム数": [len(included)],
        "除外ゲーム数": [len(excluded)],
        "結合成功数": [len(videos)],
        "結合率": [len(videos) / (len(pd.read_csv("sample_youtube_videos.csv")) + len(pd.read_csv("sample_twitch_vod_metadata.csv")))],
        "unmatched数": [len(pd.read_csv("unmatched_game_titles.csv"))],
        "event window完全取得数": [int(complete_cnt)],
        "event window欠損数": [int(total_events - complete_cnt)],
    }
    cat_counts = videos.groupby("game_category").size().to_dict()
    dq["game_category別件数"] = [str(cat_counts)]
    pd.DataFrame(dq).to_csv("data_quality_report.csv", index=False)

    by_day = ev.groupby(["game_category", "event_day"], dropna=False)["review_diff"].mean().reset_index()
    pre = ev[(ev["event_day"] >= -7) & (ev["event_day"] <= -1)].groupby("game_category")["review_diff"].mean().reset_index()
    pre["period"] = "pre"
    post = ev[(ev["event_day"] >= 0) & (ev["event_day"] <= 7)].groupby("game_category")["review_diff"].mean().reset_index()
    post["period"] = "post"
    summary = pd.concat([by_day.assign(period="event_day"), pre.assign(event_day=pd.NA), post.assign(event_day=pd.NA)], ignore_index=True)
    summary.to_csv("category_event_summary.csv", index=False)


if __name__ == "__main__":
    main()
