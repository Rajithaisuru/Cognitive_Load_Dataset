from __future__ import annotations

from contextlib import contextmanager
import csv
from datetime import date, datetime, timezone
from pathlib import Path
import threading


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKUP_DIR = ROOT_DIR / "data_backups"
SESSIONS_CSV = BACKUP_DIR / "evaluation_sessions_backup.csv"
PREDICTIONS_CSV = BACKUP_DIR / "evaluation_predictions_backup.csv"
RATINGS_CSV = BACKUP_DIR / "evaluation_ratings_backup.csv"
LOCK_FILE = BACKUP_DIR / ".evaluation_csv.lock"

SESSION_FIELDS = [
    "participant_id",
    "session_id",
    "video_id",
    "consented_at",
    "created_at",
]

PREDICTION_FIELDS = [
    "evaluation_id",
    "participant_id",
    "session_id",
    "video_id",
    "segment_index",
    "segment_start_time",
    "segment_end_time",
    "pause_frequency",
    "navigation_count_video",
    "rewatch_segments",
    "playback_rate_change",
    "idle_duration_video",
    "time_on_content",
    "model_prediction_value",
    "model_prediction_label",
    "model_confidence",
    "prediction_at",
    "model_version",
    "model_file_hash",
    "mapping_version",
    "created_at",
]

RATING_FIELDS = [
    "evaluation_id",
    "participant_id",
    "session_id",
    "participant_rating",
    "participant_rating_label",
    "comparison_model_label",
    "agreement",
    "submitted_at",
    "created_at",
]

_thread_lock = threading.Lock()


def evaluation_backup_participant_exists(participant_id: str) -> bool:
    with _evaluation_lock():
        return any(
            row.get("participant_id") == participant_id
            for row in _read_rows(SESSIONS_CSV)
        )


def save_evaluation_session_backup(session_data: dict) -> bool:
    with _evaluation_lock():
        sessions = _read_rows(SESSIONS_CSV)
        if any(row.get("session_id") == session_data["session_id"] for row in sessions):
            return True
        if any(
            row.get("participant_id") == session_data["participant_id"]
            for row in sessions
        ):
            return False
        return _append_row(SESSIONS_CSV, SESSION_FIELDS, session_data)


def save_evaluation_prediction_backup(record: dict):
    with _evaluation_lock():
        valid_session = any(
            row.get("participant_id") == record["participant_id"]
            and row.get("session_id") == record["session_id"]
            and row.get("video_id") == record["video_id"]
            for row in _read_rows(SESSIONS_CSV)
        )
        if not valid_session:
            return {"invalid_session": True}

        for existing in _read_rows(PREDICTIONS_CSV):
            if (
                existing.get("session_id") == record["session_id"]
                and existing.get("video_id") == record["video_id"]
                and existing.get("segment_index") == str(record["segment_index"])
            ):
                already_submitted = _find_rating(existing["evaluation_id"]) is not None
                return {
                    "evaluation_id": existing["evaluation_id"],
                    "already_exists": True,
                    "already_submitted": already_submitted,
                    "invalid_session": False,
                }

        if not _append_row(PREDICTIONS_CSV, PREDICTION_FIELDS, record):
            return None
        return {
            "evaluation_id": record["evaluation_id"],
            "already_exists": False,
            "already_submitted": False,
            "invalid_session": False,
        }


def submit_evaluation_rating_backup(rating_data: dict):
    with _evaluation_lock():
        prediction = next(
            (
                row
                for row in _read_rows(PREDICTIONS_CSV)
                if row.get("evaluation_id") == rating_data["evaluation_id"]
                and row.get("participant_id") == rating_data["participant_id"]
                and row.get("session_id") == rating_data["session_id"]
            ),
            None,
        )
        if prediction is None:
            return {"status": "not_found"}

        existing_rating = _find_rating(rating_data["evaluation_id"])
        if existing_rating is not None:
            return {
                "status": "already_submitted",
                "record": _merge_prediction_rating(prediction, existing_rating),
            }

        agreement = (
            rating_data["comparison_model_label"]
            == prediction["model_prediction_label"]
        )
        rating_row = {**rating_data, "agreement": agreement}
        if not _append_row(RATINGS_CSV, RATING_FIELDS, rating_row):
            return None
        return {
            "status": "submitted",
            "record": _merge_prediction_rating(prediction, rating_row),
        }


def get_evaluation_backup_records() -> list[dict]:
    with _evaluation_lock():
        ratings = {
            row["evaluation_id"]: row
            for row in _read_rows(RATINGS_CSV)
            if row.get("evaluation_id")
        }
        return [
            _merge_prediction_rating(row, ratings.get(row.get("evaluation_id")))
            for row in _read_rows(PREDICTIONS_CSV)
        ]


def _find_rating(evaluation_id: str):
    return next(
        (
            row
            for row in _read_rows(RATINGS_CSV)
            if row.get("evaluation_id") == evaluation_id
        ),
        None,
    )


def _merge_prediction_rating(prediction: dict, rating: dict | None) -> dict:
    merged = dict(prediction)
    merged.update(
        {
            "participant_rating": "",
            "participant_rating_label": "",
            "agreement": "",
            "submitted_at": "",
        }
    )
    if rating:
        merged.update(
            {
                "participant_rating": rating.get("participant_rating", ""),
                "participant_rating_label": rating.get(
                    "participant_rating_label", ""
                ),
                "agreement": _parse_bool(rating.get("agreement")),
                "submitted_at": rating.get("submitted_at", ""),
            }
        )
    return merged


def _read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(mode="r", newline="", encoding="utf-8") as file:
            return list(csv.DictReader(file))
    except Exception as exc:
        print(f"Evaluation CSV read failed for {path}: {exc}")
        return []


def _append_row(path: Path, fields: list[str], row: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = path.exists() and path.stat().st_size > 0
        prepared = {field: _serialize(row.get(field)) for field in fields}
        if not prepared.get("created_at"):
            prepared["created_at"] = datetime.now(timezone.utc).isoformat()
        with path.open(mode="a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            if not file_exists:
                writer.writeheader()
            writer.writerow(prepared)
        return True
    except Exception as exc:
        print(f"Evaluation CSV write failed for {path}: {exc}")
        return False


@contextmanager
def _evaluation_lock():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with _thread_lock:
        with LOCK_FILE.open(mode="a+", encoding="utf-8") as lock_handle:
            try:
                import fcntl

                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            except ImportError:
                fcntl = None
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if value in ("True", "true", "1", 1):
        return True
    if value in ("False", "false", "0", 0):
        return False
    return ""
