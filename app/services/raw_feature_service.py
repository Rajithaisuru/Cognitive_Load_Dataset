from datetime import datetime

from app.services.db_service import get_raw_events_for_window


def extract_feature_window_from_raw(data):
    events = get_raw_events_for_window(
        student_id=data.student_id,
        lesson_id=data.lesson_id,
        session_id=data.session_id,
        window_start=data.window_start,
        window_end=data.window_end,
    )

    pause_frequency = 0
    navigation_count_video = 0
    rewatch_segments = 0
    playback_rate_change = 0
    idle_duration_video = 0
    active_idle_start = None

    for event in events:
        event_type = event["event_type"]
        event_time = event["event_time"]

        if event_type == "pause":
            pause_frequency += 1
        elif event_type in ("seek_forward", "seek_backward"):
            navigation_count_video += 1
            if event_type == "seek_backward":
                rewatch_segments += 1
        elif event_type == "rate_change":
            playback_rate_change += 1
        elif event_type == "idle_start":
            active_idle_start = event_time
        elif event_type == "idle_end" and active_idle_start is not None:
            idle_duration_video += _seconds_between(active_idle_start, event_time)
            active_idle_start = None

    if active_idle_start is not None:
        idle_duration_video += _seconds_between(active_idle_start, data.window_end)

    window_seconds = _seconds_between(data.window_start, data.window_end)
    time_on_content = max(window_seconds - idle_duration_video, 0)

    return {
        "student_id": data.student_id,
        "lesson_id": data.lesson_id,
        "session_id": data.session_id,
        "minute_index": data.minute_index,
        "window_start": data.window_start,
        "window_end": data.window_end,
        "pause_frequency": pause_frequency,
        "navigation_count_video": navigation_count_video,
        "rewatch_segments": rewatch_segments,
        "playback_rate_change": playback_rate_change,
        "idle_duration_video": idle_duration_video,
        "time_on_content": time_on_content,
        "navigation_count_adaptation": 0,
        "revisit_frequency": 0,
        "idle_duration_adaptation": 0,
        "quiz_response_time": 0,
        "error_rate": 0.0,
    }


def _seconds_between(start: datetime, end: datetime) -> int:
    start = _normalize_datetime(start)
    end = _normalize_datetime(end)
    return max(round((end - start).total_seconds()), 0)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.replace(tzinfo=None)

    return value
