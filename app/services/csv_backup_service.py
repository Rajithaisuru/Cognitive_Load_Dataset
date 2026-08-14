from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import csv


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKUP_DIR = ROOT_DIR / "data_backups"

RAW_EVENTS_CSV = BACKUP_DIR / "raw_interaction_events_backup.csv"
FEATURE_WINDOWS_CSV = BACKUP_DIR / "feature_windows_backup.csv"
PREDICTION_LOGS_CSV = BACKUP_DIR / "prediction_logs_backup.csv"
PAAS_RATINGS_CSV = BACKUP_DIR / "paas_ratings_backup.csv"
PARTICIPANT_SESSIONS_CSV = BACKUP_DIR / "participant_sessions_backup.csv"

RAW_EVENT_FIELDS = [
    "id",
    "student_id",
    "lesson_id",
    "session_id",
    "event_type",
    "event_time",
    "video_time",
    "from_position",
    "to_position",
    "event_value",
    "question_id",
    "is_correct",
    "created_at",
]

FEATURE_WINDOW_FIELDS = [
    "id",
    "student_id",
    "lesson_id",
    "session_id",
    "minute_index",
    "window_start",
    "window_end",
    "pause_frequency",
    "navigation_count_video",
    "rewatch_segments",
    "playback_rate_change",
    "idle_duration_video",
    "time_on_content",
    "created_at",
]

PREDICTION_LOG_FIELDS = [
    "id",
    "feature_window_id",
    "student_id",
    "lesson_id",
    "session_id",
    "predicted_cognitive_load",
    "predicted_score",
    "predicted_label",
    "confidence",
    "created_at",
]

PAAS_RATING_FIELDS = [
    "id",
    "student_id",
    "lesson_id",
    "session_id",
    "minute_index",
    "window_start",
    "window_end",
    "paas_rating",
    "cognitive_load",
    "cognitive_load_label",
    "created_at",
]

PARTICIPANT_SESSION_FIELDS = [
    "id",
    "student_id",
    "lesson_id",
    "session_id",
    "created_at",
]


def save_raw_event_backup(row: dict, mysql_id=None) -> bool:
    return _append_csv(RAW_EVENTS_CSV, RAW_EVENT_FIELDS, {**row, "id": mysql_id})


def save_feature_window_backup(row: dict, mysql_id=None) -> bool:
    return _append_csv(FEATURE_WINDOWS_CSV, FEATURE_WINDOW_FIELDS, {**row, "id": mysql_id})


def save_prediction_log_backup(row: dict, mysql_id=None) -> bool:
    return _append_csv(PREDICTION_LOGS_CSV, PREDICTION_LOG_FIELDS, {**row, "id": mysql_id})


def save_paas_rating_backup(row: dict, mysql_id=None) -> bool:
    return _append_csv(PAAS_RATINGS_CSV, PAAS_RATING_FIELDS, {**row, "id": mysql_id})


def save_participant_session_backup(row: dict, mysql_id=None) -> bool:
    return _append_csv(PARTICIPANT_SESSIONS_CSV, PARTICIPANT_SESSION_FIELDS, {**row, "id": mysql_id})


def _append_csv(file_path: Path, fieldnames: list[str], row: dict) -> bool:
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        file_exists = file_path.exists()
        prepared_row = _prepare_row(fieldnames, row)

        with file_path.open(mode="a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(prepared_row)

        return True
    except Exception as exc:
        print(f"CSV backup failed for {file_path}: {exc}")
        return False


def _prepare_row(fieldnames: list[str], row: dict) -> dict:
    prepared = {field: _serialize_value(row.get(field)) for field in fieldnames}

    if not prepared.get("created_at"):
        prepared["created_at"] = datetime.utcnow().isoformat()

    return prepared


def _serialize_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value
