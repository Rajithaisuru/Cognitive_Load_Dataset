from datetime import datetime, timezone
import csv
import os

import pandas as pd

from app.core.model_loader import model
from app.services.csv_backup_service import save_feature_window_backup, save_prediction_log_backup
from app.services.db_service import save_feature_window, save_prediction_log


CSV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "cognitive_load_predictions.csv")
FALLBACK_CSV_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "cognitive_load_predictions_fallback.csv"
)

CSV_FIELDS = [
    "student_id",
    "lesson_id",
    "minute_index",
    "pause_frequency",
    "navigation_count_video",
    "rewatch_segments",
    "playback_rate_change",
    "idle_duration_video",
    "time_on_content",
    "navigation_count_adaptation",
    "revisit_frequency",
    "idle_duration_adaptation",
    "quiz_response_time",
    "error_rate",
    "predicted_cognitive_load",
    "predicted_score",
    "predicted_label",
    "confidence",
    "created_at",
]

MODEL_FEATURES = [
    "pause_frequency",
    "navigation_count_video",
    "rewatch_segments",
    "playback_rate_change",
    "idle_duration_video",
    "time_on_content",
]

STORAGE_FEATURES = [
    *MODEL_FEATURES,
    "navigation_count_adaptation",
    "revisit_frequency",
    "idle_duration_adaptation",
    "quiz_response_time",
    "error_rate",
]

STORAGE_DEFAULTS = {
    "navigation_count_adaptation": 0,
    "revisit_frequency": 0,
    "idle_duration_adaptation": 0,
    "quiz_response_time": 0,
    "error_rate": 0.0,
}


def get_label(score: int):
    labels = {
        1: "Very Low",
        2: "Low",
        3: "Medium",
        4: "High",
        5: "Very High",
    }
    return labels.get(score, "Unknown")


def save_to_csv(row_data: dict):
    target_file = CSV_FILE

    try:
        _write_csv_row(target_file, row_data)
    except PermissionError:
        # If the main CSV is locked by another app such as Excel, keep the API alive
        # and persist the prediction to a fallback file instead of failing the request.
        target_file = FALLBACK_CSV_FILE
        _write_csv_row(target_file, row_data)


def _write_csv_row(file_path: str, row_data: dict):
    file_exists = os.path.isfile(file_path)

    with open(file_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row_data)


def get_prediction_logs(student_id: str | None = None, lesson_id: str | None = None, minute_index: int | None = None):
    records = []

    for file_path in (CSV_FILE, FALLBACK_CSV_FILE):
        if not os.path.isfile(file_path):
            continue

        with open(file_path, mode="r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            for row in reader:
                normalized_row = _normalize_csv_row(row)

                if student_id and normalized_row["student_id"] != student_id:
                    continue

                if lesson_id and normalized_row["lesson_id"] != lesson_id:
                    continue

                if minute_index is not None and normalized_row["minute_index"] != minute_index:
                    continue

                records.append(normalized_row)

    records.sort(key=lambda item: item["created_at"], reverse=True)
    return records


def _normalize_csv_row(row: dict):
    int_fields = {
        "minute_index",
        "pause_frequency",
        "navigation_count_video",
        "rewatch_segments",
        "playback_rate_change",
        "idle_duration_video",
        "time_on_content",
        "navigation_count_adaptation",
        "revisit_frequency",
        "idle_duration_adaptation",
        "quiz_response_time",
        "predicted_score",
    }
    float_fields = {"error_rate", "confidence"}

    normalized = {}

    for field in CSV_FIELDS:
        value = row.get(field)

        if field in int_fields and value not in (None, ""):
            normalized[field] = int(value)
        elif field in float_fields and value not in (None, ""):
            normalized[field] = float(value)
        else:
            normalized[field] = value

    return normalized


def _get_value(data, field: str):
    return getattr(data, field, STORAGE_DEFAULTS.get(field))


def _feature_values(data, fields: list[str]):
    return {field: _get_value(data, field) for field in fields}


def predict_cognitive_load(data):
    feature_window_data = {
        "student_id": data.student_id,
        "lesson_id": data.lesson_id,
        "session_id": data.session_id,
        "minute_index": data.minute_index,
        "window_start": data.window_start,
        "window_end": data.window_end,
        **_feature_values(data, STORAGE_FEATURES),
    }

    input_df = pd.DataFrame([_feature_values(data, MODEL_FEATURES)], columns=MODEL_FEATURES)

    prediction = model.predict(input_df)[0]
    proba = model.predict_proba(input_df)[0]
    confidence = max(proba)
    label = get_label(int(prediction))

    response_data = {
        "student_id": data.student_id,
        "lesson_id": data.lesson_id,
        "minute_index": data.minute_index,
        **_feature_values(data, STORAGE_FEATURES),
        "predicted_cognitive_load": label,
        "predicted_score": int(prediction),
        "predicted_label": label,
        "confidence": round(float(confidence), 2),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    feature_window_id = save_feature_window(feature_window_data)
    feature_window_saved_to_csv = save_feature_window_backup(feature_window_data, mysql_id=feature_window_id)

    prediction_log_data = {
        "feature_window_id": feature_window_id,
        "student_id": data.student_id,
        "lesson_id": data.lesson_id,
        "session_id": data.session_id,
        "predicted_cognitive_load": label,
        "predicted_score": int(prediction),
        "predicted_label": label,
        "confidence": round(float(confidence), 2),
    }
    prediction_log_id = save_prediction_log(prediction_log_data)
    prediction_log_saved_to_csv = save_prediction_log_backup(prediction_log_data, mysql_id=prediction_log_id)

    response_data["saved_to_mysql"] = feature_window_id is not None and prediction_log_id is not None
    response_data["saved_to_csv"] = feature_window_saved_to_csv and prediction_log_saved_to_csv
    response_data["storage"] = {
        "feature_window": {
            "id": feature_window_id,
            "saved_to_mysql": feature_window_id is not None,
            "saved_to_csv": feature_window_saved_to_csv,
        },
        "prediction_log": {
            "id": prediction_log_id,
            "saved_to_mysql": prediction_log_id is not None,
            "saved_to_csv": prediction_log_saved_to_csv,
        },
    }
    return response_data
