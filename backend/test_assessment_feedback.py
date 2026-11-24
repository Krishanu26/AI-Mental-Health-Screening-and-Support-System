import unittest
from unittest.mock import Mock, patch

from backend.assessment import create_assessment_document, save_recommendation_feedback, score_responses
from backend.app import app

TOKEN = "t" * 40


class AssessmentScoringTests(unittest.TestCase):
    def test_all_zero_answers_are_minimal(self):
        self.assertEqual(score_responses([0] * 21), (0, "Minimal Depression"))

    def test_all_three_answers_are_severe(self):
        self.assertEqual(score_responses([3] * 21), (63, "Severe Depression"))

    def test_boundary_scores(self):
        for total, expected in [
            (13, "Minimal Depression"), (14, "Mild Depression"),
            (19, "Mild Depression"), (20, "Moderate Depression"),
            (28, "Moderate Depression"), (29, "Severe Depression"),
        ]:
            remaining = total
            answers = []
            for _ in range(21):
                score = min(3, remaining)
                answers.append(score)
                remaining -= score
            with self.subTest(total=total):
                self.assertEqual(score_responses(answers)[1], expected)

    def test_rejects_wrong_length_and_invalid_types(self):
        for answers in ([0] * 20, [False] + [0] * 20, ["0"] + [0] * 20, [4] + [0] * 20):
            with self.subTest(answers=answers[:2]):
                with self.assertRaises(ValueError):
                    score_responses(answers)

    def test_storage_optional_and_research_requires_storage(self):
        doc = create_assessment_document([0] * 21, False, False)
        self.assertFalse(doc["storage_consent"])
        self.assertNotIn("raw_responses_for_ml", doc)
        self.assertNotIn("feedback_token", doc)
        with self.assertRaises(ValueError):
            create_assessment_document([0] * 21, False, True)

    def test_research_consent_adds_training_data_and_token(self):
        doc = create_assessment_document([0] * 21, True, True)
        self.assertEqual(len(doc["raw_responses_for_ml"]), 21)
        self.assertGreaterEqual(len(doc["feedback_token"]), 32)

    def test_self_harm_item_flagged_independently_of_total_band(self):
        answers = [0] * 21
        answers[8] = 1
        doc = create_assessment_document(answers, False, False)
        self.assertTrue(doc["self_harm_item_positive"])
        self.assertEqual(doc["risk_level"], "Minimal Depression")


class SaveRecommendationFeedbackTests(unittest.TestCase):
    @patch("backend.database.get_collections")
    def test_saves_feedback_by_opaque_token(self, get_collections):
        assessments = Mock()
        assessments.update_one.return_value.matched_count = 1
        get_collections.return_value = (None, assessments, None, None)
        save_recommendation_feedback(TOKEN, True)
        query, update = assessments.update_one.call_args.args
        self.assertEqual(query, {"feedback_token": TOKEN})
        self.assertTrue(update["$set"]["recommendation_feedback"]["followed"])

    @patch("backend.database.get_collections")
    def test_rejects_non_boolean_feedback(self, get_collections):
        with self.assertRaises(ValueError):
            save_recommendation_feedback(TOKEN, "yes")
        get_collections.assert_not_called()

    @patch("backend.database.get_collections")
    def test_reports_unknown_assessment(self, get_collections):
        assessments = Mock()
        assessments.update_one.return_value.matched_count = 0
        get_collections.return_value = (None, assessments, None, None)
        with self.assertRaises(LookupError):
            save_recommendation_feedback(TOKEN, False)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_questions_returns_21(self):
        response = self.client.get("/api/questions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["questions"]), 21)

    def test_malformed_assessment_payload_rejected(self):
        response = self.client.post("/api/assessment", data="not-json",
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch("backend.app.save_assessment")
    def test_assessment_can_run_without_storage(self, save_assessment):
        response = self.client.post("/api/assessment", json={
            "responses": [0] * 21, "storage_consent": False, "research_consent": False
        })
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.get_json()["saved"])
        self.assertIsNone(response.get_json()["feedback_token"])
        save_assessment.assert_not_called()

    @patch("backend.app.save_assessment", return_value="mocked")
    def test_stored_assessment_returns_opaque_token(self, save_assessment):
        response = self.client.post("/api/assessment", json={
            "responses": [0] * 21, "storage_consent": True, "research_consent": False
        })
        self.assertEqual(response.status_code, 201)
        self.assertGreaterEqual(len(response.get_json()["feedback_token"]), 32)

    @patch("backend.app.save_recommendation_feedback")
    def test_feedback_endpoint_uses_token(self, save_feedback):
        response = self.client.post(
            f"/api/assessment/feedback/{TOKEN}/recommendation-feedback",
            json={"followed": False}
        )
        self.assertEqual(response.status_code, 200)
        save_feedback.assert_called_once_with(TOKEN, False)


if __name__ == "__main__":
    unittest.main()
