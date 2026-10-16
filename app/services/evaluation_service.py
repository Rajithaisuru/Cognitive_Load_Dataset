from functools import lru_cache
from hashlib import sha256
from pathlib import Path

import joblib
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT_DIR / "scripts" / "cognitive_load_model.pkl"

FEATURE_COLUMNS = [
    "pause_frequency",
    "navigation_count_video",
    "rewatch_segments",
    "playback_rate_change",
    "idle_duration_video",
    "time_on_content",
]

SELF_REPORT_LABELS = {
    1: "Very Low",
    2: "Low",
    3: "Moderate",
    4: "High",
    5: "Very High",
}

COMPARISON_MODEL_LABELS = {
    1: "Very Low",
    2: "Low",
    3: "Medium",
    4: "High",
    5: "Very High",
}

MAPPING_VERSION = "self-report-5-to-model-classes-v1"


@lru_cache(maxsize=1)
def load_evaluation_model() -> dict:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Evaluation model not found at {MODEL_PATH}")

    bundle = joblib.load(MODEL_PATH)
    if not isinstance(bundle, dict) or "model" not in bundle:
        raise ValueError("Evaluation model must be a bundle containing a 'model' entry.")

    model = bundle["model"]
    feature_columns = list(bundle.get("feature_columns") or [])
    if feature_columns != FEATURE_COLUMNS:
        raise ValueError(
            "Evaluation model feature order does not match the six supported behavior features."
        )

    model_feature_names = list(getattr(model, "feature_names_in_", []))
    if model_feature_names and model_feature_names != FEATURE_COLUMNS:
        raise ValueError("Model feature_names_in_ does not match the bundle metadata.")

    model_classes = [str(value) for value in getattr(model, "classes_", [])]
    expected_classes = set(COMPARISON_MODEL_LABELS.values())
    if set(model_classes) != expected_classes:
        raise ValueError(
            "Evaluation model classes do not match the documented five-point label set."
        )

    # Limit per-request CPU fan-out on the 2-vCPU server without changing learned parameters.
    if hasattr(model, "named_steps"):
        estimator = model.named_steps.get("model")
        if estimator is not None and hasattr(estimator, "n_jobs"):
            estimator.n_jobs = 1

    return {
        "model": model,
        "feature_columns": feature_columns,
        "class_order": list(bundle.get("class_order") or model_classes),
        "sklearn_version": str(bundle.get("sklearn_version") or "unknown"),
        "file_hash": _model_file_hash(),
    }


def predict_evaluation_segment(feature_values: dict) -> dict:
    bundle = load_evaluation_model()
    row = {name: feature_values[name] for name in bundle["feature_columns"]}
    frame = pd.DataFrame([row], columns=bundle["feature_columns"])

    model = bundle["model"]
    prediction = str(model.predict(frame)[0])
    probabilities = model.predict_proba(frame)[0]
    confidence = float(max(probabilities))

    return {
        "model_prediction_value": prediction,
        "model_prediction_label": prediction,
        "model_confidence": round(confidence, 6),
        "model_version": f"evaluation-bundle-sklearn-{bundle['sklearn_version']}",
        "model_file_hash": bundle["file_hash"],
        "mapping_version": MAPPING_VERSION,
    }


def get_self_report_label(rating: int) -> str:
    try:
        return SELF_REPORT_LABELS[rating]
    except KeyError as exc:
        raise ValueError("Self-reported mental effort must be between 1 and 5.") from exc


def get_comparison_model_label(rating: int) -> str:
    try:
        return COMPARISON_MODEL_LABELS[rating]
    except KeyError as exc:
        raise ValueError("Self-reported mental effort must be between 1 and 5.") from exc


@lru_cache(maxsize=1)
def _model_file_hash() -> str:
    digest = sha256()
    with MODEL_PATH.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
