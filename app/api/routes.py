from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import csv
from datetime import datetime, timezone
from io import StringIO
import secrets
import string
import time
from uuid import uuid4

from app.schemas.event import RawInteractionEventInput
from app.schemas.evaluation import (
    EvaluationPredictionInput,
    EvaluationRatingInput,
    EvaluationSessionInput,
)
from app.schemas.feature_window import FeatureWindowInput
from app.schemas.paas import PaasRatingInput
from app.schemas.participant import ParticipantCreateInput
from app.schemas.raw_window import RawWindowInput
from app.services.csv_backup_service import (
    save_feature_window_backup,
    save_paas_rating_backup,
    save_participant_session_backup,
    save_raw_event_backup,
)
from app.services.db_service import (
    get_joined_dataset_rows,
    participant_code_exists,
    save_feature_window,
    save_model_experiment_dataset_row,
    save_paas_rating,
    save_participant_session,
    save_raw_interaction_event,
)
from app.services.evaluation_db_service import (
    evaluation_participant_exists,
    get_evaluation_records,
    save_evaluation_prediction,
    save_evaluation_session,
    submit_evaluation_rating,
)
from app.services.evaluation_csv_service import (
    evaluation_backup_participant_exists,
    get_evaluation_backup_records,
    save_evaluation_prediction_backup,
    save_evaluation_session_backup,
    submit_evaluation_rating_backup,
)
from app.services.evaluation_service import (
    get_comparison_model_label,
    get_self_report_label,
    predict_evaluation_segment,
)
from app.services.raw_feature_service import extract_feature_window_from_raw


router = APIRouter()


@router.get("/")
def root():
    return {"message": "Cognitive Load Prediction API is running"}


@router.get("/health")
def health():
    return {
        "status": "ok",
        "mode": "data_collection",
        "model_loaded": False,
        "prediction_enabled": False,
    }


@router.post("/participants/create")
def create_participant(data: ParticipantCreateInput):
    alphabet = string.ascii_uppercase + string.digits

    for _ in range(20):
        student_id = "P" + "".join(secrets.choice(alphabet) for _ in range(5))
        if participant_code_exists(student_id):
            continue

        session_data = {
            "student_id": student_id,
            "lesson_id": data.lesson_id,
            "session_id": f"{student_id}-{int(time.time() * 1000)}",
            "session_start_time": datetime.now(timezone.utc),
        }
        session_id = save_participant_session(session_data)
        saved_to_csv = save_participant_session_backup(session_data, mysql_id=session_id)

        if session_id is not None or saved_to_csv:
            return {
                "student_id": student_id,
                "session_id": session_data["session_id"],
                "lesson_id": data.lesson_id,
                "saved_to_mysql": session_id is not None,
                "saved_to_csv": saved_to_csv,
            }

    raise HTTPException(status_code=503, detail="Could not save participant code to MySQL or CSV")


@router.post("/evaluation/sessions")
def create_evaluation_session(data: EvaluationSessionInput):
    alphabet = string.ascii_uppercase + string.digits

    for _ in range(20):
        participant_id = data.participant_id or (
            "E" + "".join(secrets.choice(alphabet) for _ in range(5))
        )
        if evaluation_participant_exists(participant_id) or evaluation_backup_participant_exists(
            participant_id
        ):
            if data.participant_id:
                raise HTTPException(
                    status_code=409,
                    detail="Participant code already exists. Generate a new code.",
                )
            continue

        session_data = {
            "participant_id": participant_id,
            "session_id": f"{participant_id}-{int(time.time() * 1000)}",
            "video_id": data.video_id,
            "consented_at": datetime.now(timezone.utc),
        }
        session_row_id = save_evaluation_session(session_data)
        saved_to_csv = save_evaluation_session_backup(session_data)
        if session_row_id is not None or saved_to_csv:
            return {
                "participant_id": participant_id,
                "session_id": session_data["session_id"],
                "video_id": data.video_id,
                "saved_to_mysql": session_row_id is not None,
                "saved_to_csv": saved_to_csv,
            }

        if data.participant_id:
            break

    raise HTTPException(
        status_code=503,
        detail="Could not save the evaluation session to MySQL or CSV",
    )


@router.post("/evaluation/segments/predict")
def create_evaluation_prediction(data: EvaluationPredictionInput):
    if data.segment_end_time <= data.segment_start_time:
        raise HTTPException(status_code=422, detail="Segment end time must follow start time")

    features = {
        "pause_frequency": data.pause_frequency,
        "navigation_count_video": data.navigation_count_video,
        "rewatch_segments": data.rewatch_segments,
        "playback_rate_change": data.playback_rate_change,
        "idle_duration_video": data.idle_duration_video,
        "time_on_content": data.time_on_content,
    }
    try:
        prediction = predict_evaluation_segment(features)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Model inference failed") from exc

    record = {
        **data.model_dump(),
        **prediction,
        "evaluation_id": str(uuid4()),
        "prediction_at": datetime.now(timezone.utc),
    }
    saved_to_mysql = save_evaluation_prediction(record)
    if saved_to_mysql and not saved_to_mysql.get("invalid_session"):
        record["evaluation_id"] = saved_to_mysql["evaluation_id"]
    saved_to_csv = save_evaluation_prediction_backup(record)
    saved = (
        saved_to_mysql
        if saved_to_mysql and not saved_to_mysql.get("invalid_session")
        else saved_to_csv
    )
    if saved is None:
        raise HTTPException(status_code=503, detail="Could not save the evaluation prediction")
    if saved.get("invalid_session"):
        raise HTTPException(status_code=404, detail="Evaluation session not found")

    # Prediction values intentionally remain server-side until rating submission.
    return {
        "evaluation_id": saved["evaluation_id"],
        "status": "already_submitted" if saved["already_submitted"] else "awaiting_rating",
        "prediction_saved": True,
        "already_exists": saved["already_exists"],
        "saved_to_mysql": bool(
            saved_to_mysql and not saved_to_mysql.get("invalid_session")
        ),
        "saved_to_csv": bool(saved_to_csv and not saved_to_csv.get("invalid_session")),
    }


@router.post("/evaluation/segments/rating")
def submit_evaluation_segment_rating(data: EvaluationRatingInput):
    rating_data = {
        **data.model_dump(),
        "participant_rating_label": get_self_report_label(data.participant_rating),
        "comparison_model_label": get_comparison_model_label(data.participant_rating),
        "submitted_at": datetime.now(timezone.utc),
    }
    mysql_result = submit_evaluation_rating(rating_data)
    csv_result = submit_evaluation_rating_backup(rating_data)
    result = (
        mysql_result
        if mysql_result and mysql_result.get("status") != "not_found"
        else csv_result
    )
    if result is None:
        raise HTTPException(status_code=503, detail="Could not save the evaluation rating")
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Evaluation segment not found")

    record = result["record"]
    return {
        "status": result["status"],
        "duplicate_submission": result["status"] == "already_submitted",
        "participant_rating": record["participant_rating"],
        "participant_rating_label": record["participant_rating_label"],
        "model_prediction_value": record["model_prediction_value"],
        "model_prediction_label": record["model_prediction_label"],
        "model_confidence": float(record["model_confidence"]),
        "agreement": bool(record["agreement"]),
        "mapping_version": record["mapping_version"],
        "saved_to_mysql": bool(
            mysql_result and mysql_result.get("status") != "not_found"
        ),
        "saved_to_csv": bool(csv_result and csv_result.get("status") != "not_found"),
    }


@router.post("/predict")
def predict(data: dict):
    from app.schemas.prediction import CognitiveLoadInput
    from app.services.prediction_service import predict_cognitive_load

    try:
        return predict_cognitive_load(CognitiveLoadInput(**data))
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Loaded model is not compatible with the 6-feature prediction input. "
                "Replace model/cognitive_load_model.pkl with the retrained 6-feature model."
            ),
        ) from exc


@router.post("/events/raw")
def create_raw_event(data: RawInteractionEventInput):
    raw_event_data = data.model_dump()
    event_id = save_raw_interaction_event(raw_event_data)
    saved_to_csv = save_raw_event_backup(raw_event_data, mysql_id=event_id)

    return {
        "message": "Raw interaction event processed",
        "saved_to_mysql": event_id is not None,
        "saved_to_csv": saved_to_csv,
        "id": event_id,
    }


@router.post("/predict/from-raw")
def predict_from_raw(data: RawWindowInput):
    from app.schemas.prediction import CognitiveLoadInput
    from app.services.prediction_service import predict_cognitive_load

    feature_data = extract_feature_window_from_raw(data)
    feature_input = CognitiveLoadInput(**feature_data)

    try:
        return predict_cognitive_load(feature_input)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Loaded model is not compatible with the extracted 6-feature input. "
                "Replace model/cognitive_load_model.pkl with the retrained 6-feature model."
            ),
        ) from exc


@router.post("/feature-windows")
def create_feature_window(data: FeatureWindowInput):
    feature_window_data = data.model_dump()
    feature_window_id = save_feature_window(feature_window_data)
    saved_to_csv = save_feature_window_backup(feature_window_data, mysql_id=feature_window_id)
    model_dataset_rows = save_model_experiment_dataset_row(feature_window_data)

    return {
        "message": "Feature window processed",
        "saved_to_mysql": feature_window_id is not None,
        "saved_to_csv": saved_to_csv,
        "model_dataset_saved_to_mysql": model_dataset_rows is not None,
        "model_dataset_rows_inserted": model_dataset_rows or 0,
        "id": feature_window_id,
    }


@router.post("/paas-ratings")
def create_paas_rating(data: PaasRatingInput):
    rating_data = data.model_dump()
    result = save_paas_rating(rating_data)
    saved_to_csv = save_paas_rating_backup({**rating_data, **result}, mysql_id=result["id"])
    model_dataset_rows = save_model_experiment_dataset_row(rating_data)

    return {
        "message": "Paas rating saved",
        "saved_to_mysql": result["id"] is not None,
        "saved_to_csv": saved_to_csv,
        "model_dataset_saved_to_mysql": model_dataset_rows is not None,
        "model_dataset_rows_inserted": model_dataset_rows or 0,
        **result,
    }


@router.get("/dataset/export")
def export_dataset():
    rows = get_joined_dataset_rows()
    output = StringIO()
    fieldnames = [
        "participant_id",
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
        "paas_rating",
        "cognitive_load",
        "cognitive_load_label",
        "feature_created_at",
        "rating_created_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cognitive_load_dataset.csv"},
    )


@router.get("/evaluation/export")
def export_evaluation_dataset():
    mysql_rows = get_evaluation_records()
    csv_rows = get_evaluation_backup_records()
    rows_by_segment = {
        (str(row["session_id"]), str(row["video_id"]), str(row["segment_index"])): row
        for row in csv_rows
    }
    for row in mysql_rows:
        rows_by_segment[
            (str(row["session_id"]), str(row["video_id"]), str(row["segment_index"]))
        ] = row
    rows = list(rows_by_segment.values())
    output = StringIO()
    fieldnames = [
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
        "participant_rating",
        "participant_rating_label",
        "agreement",
        "prediction_at",
        "submitted_at",
        "model_version",
        "model_file_hash",
        "mapping_version",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=model_evaluation_records.csv"},
    )


@router.get("/xai/data")
def get_xai_data(
    student_id: str | None = None,
    lesson_id: str | None = None,
    minute_index: int | None = None,
):
    from app.services.prediction_service import get_prediction_logs

    return get_prediction_logs(
        student_id=student_id,
        lesson_id=lesson_id,
        minute_index=minute_index,
    )
