import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.api.routes import (
    create_evaluation_prediction,
    create_evaluation_session,
    submit_evaluation_segment_rating,
)
from app.schemas.evaluation import (
    EvaluationPredictionInput,
    EvaluationRatingInput,
    EvaluationSessionInput,
)
from app.services.evaluation_service import (
    FEATURE_COLUMNS,
    get_comparison_model_label,
    get_self_report_label,
    load_evaluation_model,
    predict_evaluation_segment,
)
from app.services import evaluation_csv_service


class EvaluationModelTests(unittest.TestCase):
    def test_bundle_metadata_matches_supported_features_and_classes(self):
        bundle = load_evaluation_model()

        self.assertEqual(bundle["feature_columns"], FEATURE_COLUMNS)
        self.assertEqual(
            set(bundle["model"].classes_),
            {"Very Low", "Low", "Medium", "High", "Very High"},
        )
        self.assertEqual(len(bundle["file_hash"]), 64)

    def test_real_model_inference_uses_original_class_label(self):
        result = predict_evaluation_segment(
            {
                "pause_frequency": 1,
                "navigation_count_video": 2,
                "rewatch_segments": 0,
                "playback_rate_change": 1,
                "idle_duration_video": 5,
                "time_on_content": 115,
            }
        )

        self.assertIn(
            result["model_prediction_value"],
            {"Very Low", "Low", "Medium", "High", "Very High"},
        )
        self.assertGreaterEqual(result["model_confidence"], 0)
        self.assertLessEqual(result["model_confidence"], 1)

    def test_moderate_self_report_preserves_its_name_and_maps_explicitly(self):
        self.assertEqual(get_self_report_label(3), "Moderate")
        self.assertEqual(get_comparison_model_label(3), "Medium")


class EvaluationRouteTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime.now(timezone.utc)
        self.prediction_input = EvaluationPredictionInput(
            participant_id="EABCDE",
            session_id="EABCDE-123",
            video_id="L101",
            segment_index=1,
            segment_start_time=self.start,
            segment_end_time=self.start + timedelta(minutes=2),
            pause_frequency=1,
            navigation_count_video=2,
            rewatch_segments=0,
            playback_rate_change=1,
            idle_duration_video=5,
            time_on_content=115,
        )

    @patch("app.api.routes.save_evaluation_prediction_backup")
    @patch("app.api.routes.save_evaluation_prediction")
    @patch("app.api.routes.predict_evaluation_segment")
    def test_prediction_response_keeps_model_output_hidden(
        self, mock_predict, mock_save, mock_csv_save
    ):
        mock_predict.return_value = {
            "model_prediction_value": "High",
            "model_prediction_label": "High",
            "model_confidence": 0.8,
            "model_version": "test-model",
            "model_file_hash": "a" * 64,
            "mapping_version": "test-mapping",
        }
        mock_save.return_value = None
        mock_csv_save.return_value = {
            "evaluation_id": "11111111-1111-1111-1111-111111111111",
            "already_exists": False,
            "already_submitted": False,
            "invalid_session": False,
        }

        response = create_evaluation_prediction(self.prediction_input)

        self.assertTrue(response["prediction_saved"])
        self.assertNotIn("model_prediction_value", response)
        self.assertNotIn("model_prediction_label", response)
        self.assertNotIn("model_confidence", response)
        self.assertFalse(response["saved_to_mysql"])
        self.assertTrue(response["saved_to_csv"])

    def test_session_input_accepts_browser_generated_participant_code(self):
        data = EvaluationSessionInput(video_id="L101", participant_id="E1A2B3")

        self.assertEqual(data.participant_id, "E1A2B3")

    @patch("app.api.routes.save_evaluation_session_backup", return_value=True)
    @patch("app.api.routes.evaluation_backup_participant_exists", return_value=False)
    @patch("app.api.routes.save_evaluation_session")
    @patch("app.api.routes.evaluation_participant_exists", return_value=False)
    def test_session_uses_browser_generated_participant_code(
        self, mock_exists, mock_save, mock_csv_exists, mock_csv_save
    ):
        mock_save.return_value = 1

        response = create_evaluation_session(
            EvaluationSessionInput(video_id="L101", participant_id="E1A2B3")
        )

        self.assertEqual(response["participant_id"], "E1A2B3")
        self.assertTrue(response["session_id"].startswith("E1A2B3-"))

    @patch("app.api.routes.submit_evaluation_rating_backup")
    @patch("app.api.routes.submit_evaluation_rating")
    def test_rating_response_reveals_stored_prediction(
        self, mock_submit, mock_csv_submit
    ):
        mock_submit.return_value = None
        mock_csv_submit.return_value = {
            "status": "submitted",
            "record": {
                "participant_rating": 3,
                "participant_rating_label": "Moderate",
                "model_prediction_value": "Medium",
                "model_prediction_label": "Medium",
                "model_confidence": 0.75,
                "agreement": True,
                "mapping_version": "self-report-5-to-model-classes-v1",
            },
        }
        data = EvaluationRatingInput(
            evaluation_id="11111111-1111-1111-1111-111111111111",
            participant_id="EABCDE",
            session_id="EABCDE-123",
            participant_rating=3,
        )

        response = submit_evaluation_segment_rating(data)

        self.assertEqual(response["participant_rating_label"], "Moderate")
        self.assertEqual(response["model_prediction_label"], "Medium")
        self.assertTrue(response["agreement"])
        self.assertFalse(response["saved_to_mysql"])
        self.assertTrue(response["saved_to_csv"])


class EvaluationCsvFallbackTests(unittest.TestCase):
    def setUp(self):
        test_backup_root = Path.cwd() / "data_backups"
        test_backup_root.mkdir(parents=True, exist_ok=True)
        self.temp_dir = TemporaryDirectory(dir=test_backup_root)
        root = Path(self.temp_dir.name)
        self.path_patch = patch.multiple(
            evaluation_csv_service,
            BACKUP_DIR=root,
            SESSIONS_CSV=root / "sessions.csv",
            PREDICTIONS_CSV=root / "predictions.csv",
            RATINGS_CSV=root / "ratings.csv",
            LOCK_FILE=root / ".lock",
        )
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_full_csv_fallback_flow_preserves_hidden_prediction(self):
        now = datetime.now(timezone.utc)
        session = {
            "participant_id": "ECSV01",
            "session_id": "ECSV01-123",
            "video_id": "L101",
            "consented_at": now,
        }
        self.assertTrue(evaluation_csv_service.save_evaluation_session_backup(session))

        prediction = {
            **session,
            "evaluation_id": "11111111-1111-1111-1111-111111111111",
            "segment_index": 1,
            "segment_start_time": now,
            "segment_end_time": now + timedelta(minutes=2),
            "pause_frequency": 1,
            "navigation_count_video": 2,
            "rewatch_segments": 0,
            "playback_rate_change": 1,
            "idle_duration_video": 5,
            "time_on_content": 115,
            "model_prediction_value": "Medium",
            "model_prediction_label": "Medium",
            "model_confidence": 0.75,
            "prediction_at": now,
            "model_version": "test-model",
            "model_file_hash": "a" * 64,
            "mapping_version": "self-report-5-to-model-classes-v1",
        }
        saved = evaluation_csv_service.save_evaluation_prediction_backup(prediction)
        self.assertNotIn("model_prediction_label", saved)
        self.assertFalse(saved["already_exists"])

        rating = {
            "evaluation_id": prediction["evaluation_id"],
            "participant_id": session["participant_id"],
            "session_id": session["session_id"],
            "participant_rating": 3,
            "participant_rating_label": "Moderate",
            "comparison_model_label": "Medium",
            "submitted_at": now + timedelta(minutes=2, seconds=5),
        }
        result = evaluation_csv_service.submit_evaluation_rating_backup(rating)
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(result["record"]["model_prediction_label"], "Medium")
        self.assertTrue(result["record"]["agreement"])

        duplicate = evaluation_csv_service.submit_evaluation_rating_backup(rating)
        self.assertEqual(duplicate["status"], "already_submitted")
        records = evaluation_csv_service.get_evaluation_backup_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["participant_rating"], "3")


if __name__ == "__main__":
    unittest.main()
