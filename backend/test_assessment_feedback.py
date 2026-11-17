import unittest
from unittest.mock import Mock, patch

from bson import ObjectId
from backend.assessment import save_recommendation_feedback
from backend.app import app


class SaveRecommendationFeedbackTests(unittest.TestCase):
    @patch("backend.database.get_collections")
    def test_saves_boolean_feedback_and_timestamp(self, get_collections):
        assessments = Mock()
        assessments.update_one.return_value.matched_count = 1
        get_collections.return_value = (None, assessments, None, None)

        save_recommendation_feedback("64b000000000000000000001", True)

        query, update = assessments.update_one.call_args.args
        self.assertEqual(query, {"_id": ObjectId("64b000000000000000000001")})
        feedback = update["$set"]["recommendation_feedback"]
        self.assertTrue(feedback["followed"])
        self.assertIsNotNone(feedback["recorded_at"])

    @patch("backend.database.get_collections")
    def test_rejects_non_boolean_feedback(self, get_collections):
        with self.assertRaises(ValueError):
            save_recommendation_feedback("64b000000000000000000001", "yes")
        get_collections.assert_not_called()

    @patch("backend.database.get_collections")
    def test_reports_unknown_assessment(self, get_collections):
        assessments = Mock()
        assessments.update_one.return_value.matched_count = 0
        get_collections.return_value = (None, assessments, None, None)

        with self.assertRaises(LookupError):
            save_recommendation_feedback("64b000000000000000000001", False)

    @patch("backend.app.save_recommendation_feedback")
    def test_api_saves_feedback_for_assessment(self, save_feedback):
        response = app.test_client().post(
            "/api/assessment/64b000000000000000000001/recommendation-feedback",
            json={"followed": False}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"saved": True})
        save_feedback.assert_called_once_with("64b000000000000000000001", False)


if __name__ == "__main__":
    unittest.main()
