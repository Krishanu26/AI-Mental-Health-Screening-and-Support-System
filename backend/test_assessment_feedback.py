import unittest
from unittest.mock import Mock, patch

from bson import ObjectId
from backend.assessment import (
    create_assessment_document,
    save_recommendation_feedback,
    score_responses,
)
from backend.assessment_data import BDI2_QUESTIONS
from backend.app import app


class AssessmentScoringTests(unittest.TestCase):
    def test_all_zero_answers_are_minimal(self):
        self.assertEqual(score_responses([0] * 21), (0, "Minimal Depression"))

    def test_all_three_answers_are_severe(self):
        self.assertEqual(score_responses([3] * 21), (63, "Severe Depression"))

    def test_boundary_scores(self):
        cases = [
            (13, "Minimal Depression"), (14, "Mild Depression"),
            (19, "Mild Depression"), (20, "Moderate Depression"),
            (28, "Moderate Depression"), (29, "Severe Depression"),
        ]
        for total, expected in cases:
            with self.subTest(total=total):
                # The first N answers score one; the remaining answers score zero.
                answers = [1 if i < total else 0 for i in range(21)]
                self.assertEqual(score_responses(answers)[1], expected)

    def test_rejects_wrong_length_and_invalid_types(self):
        with self.assertRaises(ValueError):
            score_responses([0] * 20)
        with self.assertRaises(ValueError):
            score_responses([False] + [0] * 20)
        with self.assertRaises(ValueError):
            score_responses(["0"] + [0] * 20)
        with self.assertRaises(ValueError):
            score_responses([4] + [0] * 20)

    def test_storage_is_optional_and_research_requires_storage(self):
        doc = create_assessment_document([0] * 21, False, False)
        self.assertFalse(doc["storage_consent"])
        self.assertNotIn("raw_responses_for_ml", doc)
        with self.assertRaises(ValueError):
            create_assessment_document([0] * 21, False, True)

    def test_self_harm_item_is_flagged_independently_of_total_band(self):
        answers = [0] * 21
        answers[8] = 1
        doc = create_assessment_document(answers, False, False)
        self.assertTrue(doc["self_harm_item_positive"])
        self.assertEqual(doc["risk_level"], "Minimal Depression")


class SaveRecommendationFeedbackTests(unittest.TestCase):
    @patch("backend.database.get_collections")
    def test_saves_boolean_feedback_and_timestamp(self, get_collections):
        assessments = Mock()
        assessments.update_one.return_value.matched_count = 1
        get_collections.return_value = (None, assessments, None, None)
        save_recommendation_feedback("64b000000000000000000001", True)
        query, update = assessments.update_one.call_args.args
        self.assertEqual(query, {"_id": ObjectId("64b000000000000000000001")})
        self.assertTrue(update["$set"]["recommendation_feedback"]["followed"])

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


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_questions_endpoint_returns_21_questions(self):
        response = self.client.get("/api/questions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["questions"]), 21)

    def test_malformed_assessment_payload_is_rejected(self):
        response = self.client.post("/api/assessment", data="not-json",
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch("backend.app.save_assessment")
    def test_assessment_can_be_completed_without_storage(self, save_assessment):
        response = self.client.post("/api/assessment", json={
            "responses": [0] * 21,
            "storage_consent": False,
            "research_consent": False,
        })
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.get_json()["saved"])
        save_assessment.assert_not_called()

    @patch("backend.app.save_recommendation_feedback")
    def test_api_saves_feedback_for_assessment(self, save_feedback):
        response = self.client.post(
            "/api/assessment/64b000000000000000000001/recommendation-feedback",
            json={"followed": False},
        )
        self.assertEqual(response.status_code, 200)
        save_feedback.assert_called_once_with("64b000000000000000000001", False)


if __name__ == "__main__":
    unittest.main()
