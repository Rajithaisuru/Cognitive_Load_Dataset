from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import csv
from io import StringIO
import secrets
import string
import time

from app.schemas.event import RawInteractionEventInput
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
    save_paas_rating,
    save_participant_session,
    save_raw_interaction_event,
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
        }
        session_id = save_participant_session(session_data)
        saved_to_csv = save_participant_session_backup(session_data, mysql_id=session_id)

        if session_id is not None:
            return {
                "student_id": student_id,
                "session_id": session_data["session_id"],
                "lesson_id": data.lesson_id,
                "saved_to_mysql": True,
                "saved_to_csv": saved_to_csv,
            }

    raise HTTPException(status_code=503, detail="Could not create a unique participant code")


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

    return {
        "message": "Feature window processed",
        "saved_to_mysql": feature_window_id is not None,
        "saved_to_csv": saved_to_csv,
        "id": feature_window_id,
    }


@router.post("/paas-ratings")
def create_paas_rating(data: PaasRatingInput):
    rating_data = data.model_dump()
    result = save_paas_rating(rating_data)
    saved_to_csv = save_paas_rating_backup({**rating_data, **result}, mysql_id=result["id"])

    return {
        "message": "Paas rating saved",
        "saved_to_mysql": result["id"] is not None,
        "saved_to_csv": saved_to_csv,
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
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cognitive_load_dataset.csv"},
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
