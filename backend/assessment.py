from datetime import datetime, timezone
import secrets

from backend.assessment_data import BDI2_QUESTIONS


def score_responses(responses: list[int]) -> tuple[int, str]:
    """Validate the 21 answers and return the questionnaire total and band."""
    if not isinstance(responses, list):
        raise ValueError("Responses must be a list of 21 option indexes.")
    if len(responses) != len(BDI2_QUESTIONS):
        raise ValueError(f"Expected {len(BDI2_QUESTIONS)} answers.")

    total = 0
    for idx, (answer, question) in enumerate(zip(responses, BDI2_QUESTIONS)):
        if isinstance(answer, bool) or not isinstance(answer, int):
            raise ValueError(f"Answer {idx + 1} must be an integer option index.")
        options = question.get("options", [])
        if answer < 0 or answer >= len(options):
            raise ValueError(f"Answer {idx + 1} is outside the allowed options.")
        score = options[answer].get("score")
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 3:
            raise ValueError(f"Question {idx + 1} has an invalid scoring configuration.")
        total += score

    if not 0 <= total <= 63:
        raise ValueError("Total score is outside the expected BDI-II range.")
    if total <= 13:
        level = "Minimal Depression"
    elif total <= 19:
        level = "Mild Depression"
    elif total <= 28:
        level = "Moderate Depression"
    else:
        level = "Severe Depression"
    return total, level


def create_assessment_document(
    responses: list[int], storage_consent: bool, research_consent: bool,
    user_id: str | None = None,
) -> dict:
    """Build a result; callers decide whether to persist it."""
    if not isinstance(storage_consent, bool) or not isinstance(research_consent, bool):
        raise ValueError("Consent values must be true or false.")
    if research_consent and not storage_consent:
        raise ValueError("Research consent requires separate assessment-storage consent.")

    if storage_consent and not user_id:
        raise ValueError("Sign in to save an assessment to your personal history.")

    total, level = score_responses(responses)
    selected = []
    for question, answer in zip(BDI2_QUESTIONS, responses):
        option = question["options"][answer]
        selected.append({
            "question": question["question"],
            "selected_text": option["text"],
            "score": int(option["score"]),
        })

    # BDI-II item 9 prompts human follow-up; it is not a suicide-risk assessment.
    self_harm_item_positive = int(
        BDI2_QUESTIONS[8]["options"][responses[8]]["score"]
    ) > 0

    document = {
        "total_score": total,
        "risk_level": level,
        "responses": selected,
        "storage_consent": storage_consent,
        "research_consent": research_consent,
        "training_status": "eligible" if research_consent else "not_consented",
        "created_at": datetime.now(timezone.utc),
        "schema_version": 5,
        "self_harm_item_positive": self_harm_item_positive,
    }
    if research_consent:
        document["raw_responses_for_ml"] = [item["selected_text"] for item in selected]
    if storage_consent:
        document["user_id"] = user_id
        document["feedback_token"] = secrets.token_urlsafe(48)
    return document


def save_assessment(document: dict) -> str:
    from backend.database import get_collections
    _, assessments, _, _ = get_collections()
    result = assessments.insert_one(document)
    return str(result.inserted_id)


def save_recommendation_feedback(feedback_token: str, followed: bool) -> None:
    if not isinstance(followed, bool):
        raise ValueError("Follow-up response must be true or false.")
    if not isinstance(feedback_token, str) or len(feedback_token) < 32:
        raise ValueError("Invalid feedback token.")

    from backend.database import get_collections
    _, assessments, _, _ = get_collections()
    result = assessments.update_one(
        {"feedback_token": feedback_token},
        {"$set": {"recommendation_feedback": {
            "followed": followed,
            "recorded_at": datetime.now(timezone.utc),
        }}},
    )
    if result.matched_count == 0:
        raise LookupError("Assessment not found.")
