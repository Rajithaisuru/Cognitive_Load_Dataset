from datetime import timezone

from app.core.database import get_db_connection
from app.services.paas_service import map_paas_to_cognitive_load


def save_raw_interaction_event(event_data: dict):
    query = """
        INSERT INTO raw_interaction_events (
            student_id,
            lesson_id,
            session_id,
            event_type,
            event_time,
            video_time,
            from_position,
            to_position,
            event_value,
            question_id,
            is_correct
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        event_data["student_id"],
        event_data["lesson_id"],
        event_data.get("session_id"),
        event_data["event_type"],
        _to_mysql_datetime(event_data["event_time"]),
        event_data.get("video_time"),
        event_data.get("from_position"),
        event_data.get("to_position"),
        event_data.get("event_value"),
        event_data.get("question_id"),
        event_data.get("is_correct"),
    )
    return _execute_insert(query, values)


def save_feature_window(feature_data: dict):
    query = """
        INSERT INTO feature_windows (
            student_id,
            lesson_id,
            session_id,
            minute_index,
            window_start,
            window_end,
            pause_frequency,
            navigation_count_video,
            rewatch_segments,
            playback_rate_change,
            idle_duration_video,
            time_on_content
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        feature_data["student_id"],
        feature_data["lesson_id"],
        feature_data.get("session_id"),
        feature_data["minute_index"],
        _to_mysql_datetime(feature_data.get("window_start")),
        _to_mysql_datetime(feature_data.get("window_end")),
        feature_data["pause_frequency"],
        feature_data["navigation_count_video"],
        feature_data["rewatch_segments"],
        feature_data["playback_rate_change"],
        feature_data["idle_duration_video"],
        feature_data["time_on_content"],
    )
    return _execute_insert(query, values)


def save_prediction_log(prediction_data: dict):
    query = """
        INSERT INTO prediction_logs (
            feature_window_id,
            student_id,
            lesson_id,
            session_id,
            predicted_cognitive_load,
            predicted_score,
            confidence
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        prediction_data.get("feature_window_id"),
        prediction_data["student_id"],
        prediction_data["lesson_id"],
        prediction_data.get("session_id"),
        prediction_data["predicted_cognitive_load"],
        prediction_data["predicted_score"],
        prediction_data["confidence"],
    )
    return _execute_insert(query, values)


def save_paas_rating(rating_data: dict):
    cognitive_load, cognitive_load_label = map_paas_to_cognitive_load(rating_data["paas_rating"])
    query = """
        INSERT INTO paas_ratings (
            student_id,
            lesson_id,
            session_id,
            minute_index,
            window_start,
            window_end,
            paas_rating,
            cognitive_load,
            cognitive_load_label
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        rating_data["student_id"],
        rating_data["lesson_id"],
        rating_data.get("session_id"),
        rating_data["minute_index"],
        _to_mysql_datetime(rating_data["window_start"]),
        _to_mysql_datetime(rating_data["window_end"]),
        rating_data["paas_rating"],
        cognitive_load,
        cognitive_load_label,
    )
    rating_id = _execute_insert(query, values)
    return {
        "id": rating_id,
        "cognitive_load": cognitive_load,
        "cognitive_load_label": cognitive_load_label,
    }


def get_raw_events_for_window(
    student_id: str,
    lesson_id: str,
    session_id: str | None,
    window_start,
    window_end,
):
    query = """
        SELECT
            event_type,
            event_time,
            video_time,
            from_position,
            to_position,
            event_value
        FROM raw_interaction_events
        WHERE student_id = %s
            AND lesson_id = %s
            AND (%s IS NULL OR session_id = %s)
            AND event_time >= %s
            AND event_time < %s
        ORDER BY event_time ASC, id ASC
    """
    values = (
        student_id,
        lesson_id,
        session_id,
        session_id,
        _to_mysql_datetime(window_start),
        _to_mysql_datetime(window_end),
    )
    return _execute_fetch_all(query, values)


def get_joined_dataset_rows():
    query = """
        SELECT
            fw.student_id AS participant_id,
            fw.lesson_id,
            fw.session_id,
            fw.minute_index,
            fw.window_start,
            fw.window_end,
            fw.pause_frequency,
            fw.navigation_count_video,
            fw.rewatch_segments,
            fw.playback_rate_change,
            fw.idle_duration_video,
            fw.time_on_content,
            pr.paas_rating,
            pr.cognitive_load,
            pr.cognitive_load_label,
            fw.created_at AS feature_created_at,
            pr.created_at AS rating_created_at
        FROM feature_windows fw
        INNER JOIN paas_ratings pr
            ON fw.student_id = pr.student_id
            AND fw.lesson_id = pr.lesson_id
            AND (
                fw.session_id = pr.session_id
                OR (fw.session_id IS NULL AND pr.session_id IS NULL)
            )
            AND fw.minute_index = pr.minute_index
        ORDER BY fw.student_id, fw.session_id, fw.minute_index
    """
    return _execute_fetch_all(query, ())


def _execute_insert(query: str, values: tuple):
    connection = get_db_connection()

    if connection is None:
        return None

    cursor = None

    try:
        cursor = connection.cursor()
        cursor.execute(query, values)
        connection.commit()
        return cursor.lastrowid
    except Exception as exc:
        print(f"MySQL insert failed: {exc}")
        return None
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def _execute_fetch_all(query: str, values: tuple):
    connection = get_db_connection()

    if connection is None:
        return []

    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, values)
        return cursor.fetchall()
    except Exception as exc:
        print(f"MySQL fetch failed: {exc}")
        return []
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def _to_mysql_datetime(value):
    if value is None:
        return None

    if getattr(value, "tzinfo", None) is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    return value
