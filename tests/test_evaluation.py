import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.api.routes import create_evaluation_prediction, submit_evaluation_segment_rating
from app.schemas.evaluation import EvaluationPredictionInput, EvaluationRatingInput
from app.services.evaluation_service import (
    FEATURE_COLUMNS,
    get_comparison_model_label,
    get_self_report_label,
    load_evaluation_model,
    predict_evaluation_segment,
)


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

    @patch("app.api.routes.save_evaluation_prediction")
    @patch("app.api.routes.predict_evaluation_segment")
    def test_prediction_response_keeps_model_output_hidden(self, mock_predict, mock_save):
        mock_predict.return_value = {
            "model_prediction_value": "High",
            "model_prediction_label": "High",
            "model_confidence": 0.8,
            "model_version": "test-model",
            "model_file_hash": "a" * 64,
            "mapping_version": "test-mapping",
        }
        mock_save.return_value = {
            "evaluation_id": "11111111-1111-1111-1111-111111111111",
            "already_exists": False,
            "already_submitted": False,
        }

        response = create_evaluation_prediction(self.prediction_input)

        self.assertTrue(response["prediction_saved"])
        self.assertNotIn("model_prediction_value", response)
        self.assertNotIn("model_prediction_label", response)
        self.assertNotIn("model_confidence", response)

    @patch("app.api.routes.submit_evaluation_rating")
    def test_rating_response_reveals_stored_prediction(self, mock_submit):
        mock_submit.return_value = {
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


if __name__ == "__main__":
    unittest.main()
