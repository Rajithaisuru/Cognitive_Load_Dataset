from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "training_video_features_6_from_previous_dataset.csv"
MODEL_PATH = ROOT_DIR / "model" / "cognitive_load_model.pkl"
REPORT_PATH = ROOT_DIR / "model" / "training_report.txt"

MODEL_FEATURES = [
    "pause_frequency",
    "navigation_count_video",
    "rewatch_segments",
    "playback_rate_change",
    "idle_duration_video",
    "time_on_content",
]
TARGET_COLUMN = "cognitive_load"


def load_clean_data() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    df = pd.read_csv(DATA_PATH)

    required_columns = [*MODEL_FEATURES, TARGET_COLUMN]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    clean_df = df[required_columns].copy()
    for column in required_columns:
        clean_df[column] = pd.to_numeric(clean_df[column], errors="coerce")

    before_rows = len(clean_df)
    clean_df = clean_df.dropna()
    clean_df = clean_df[clean_df[TARGET_COLUMN].isin([1, 2, 3, 4, 5])]
    clean_df[TARGET_COLUMN] = clean_df[TARGET_COLUMN].astype(int)

    if clean_df.empty:
        raise ValueError("No valid training rows found after cleaning.")

    removed_rows = before_rows - len(clean_df)
    print(f"Loaded {len(df)} rows. Using {len(clean_df)} valid rows. Removed {removed_rows} rows.")

    return clean_df[MODEL_FEATURES], clean_df[TARGET_COLUMN], clean_df


def train_model(x: pd.DataFrame, y: pd.Series) -> tuple[CalibratedClassifierCV, str]:
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    base_model = RandomForestClassifier(
        n_estimators=500,
        max_depth=10,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=1,
    )

    model = CalibratedClassifierCV(
        estimator=base_model,
        method="isotonic",
        cv=5,
    )
    model.fit(x_train, y_train)

    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)
    confidence = probabilities.max(axis=1)

    report = "\n".join(
        [
            f"Training data: {DATA_PATH.name}",
            f"Rows used: {len(x)}",
            f"Features: {MODEL_FEATURES}",
            "",
            "Class distribution:",
            y.value_counts().sort_index().to_string(),
            "",
            f"Accuracy: {accuracy_score(y_test, predictions):.4f}",
            f"Average confidence: {confidence.mean():.4f}",
            f"Median confidence: {pd.Series(confidence).median():.4f}",
            "",
            "Classification report:",
            classification_report(y_test, predictions, digits=4),
            "Confusion matrix:",
            str(confusion_matrix(y_test, predictions, labels=[1, 2, 3, 4, 5])),
        ]
    )

    return model, report


def backup_existing_model() -> None:
    if not MODEL_PATH.exists():
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = MODEL_PATH.with_name(f"cognitive_load_model_backup_{timestamp}.pkl")
    shutil.copy2(MODEL_PATH, backup_path)
    print(f"Backed up existing model to {backup_path}")


def main() -> None:
    x, y, _ = load_clean_data()
    model, report = train_model(x, y)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup_existing_model()
    joblib.dump(model, MODEL_PATH)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"Saved model to {MODEL_PATH}")
    print(f"Saved report to {REPORT_PATH}")
    print(report)


if __name__ == "__main__":
    main()
