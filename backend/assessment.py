from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from backend.assessment_data import BDI2_QUESTIONS

def score_responses(responses: list[int]) -> tuple[int, str]:
    if len(responses) != len(BDI2_QUESTIONS):
        raise ValueError(f"Expected {len(BDI2_QUESTIONS)} answers.")
    total = 0
    for idx, (answer, question) in enumerate(zip(responses, BDI2_QUESTIONS)):
        if isinstance(answer, bool) or not isinstance(answer, int):
            raise ValueError(f"Answer {idx + 1} must be an integer option index.")
        if answer < 0 or answer >= len(question["options"]):
            raise ValueError(f"Answer {idx + 1} is outside the allowed options.")
        total += int(question["options"][answer]["score"])
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

def create_assessment_document(responses: list[int], storage_consent: bool,
                               research_consent: bool) -> dict:
    if not storage_consent:
        raise PermissionError("Storage consent is required to save this assessment.")
    if not isinstance(research_consent, bool):
        raise ValueError("Research consent must be true or false.")
    total, level = score_responses(responses)
    selected = []
    for question, answer in zip(BDI2_QUESTIONS, responses):
        option = question["options"][answer]
        selected.append({
            "question": question["question"],
            "selected_text": option["text"],
            "score": int(option["score"])
        })
    # Self-harm item is item 9 in BDI-II. This is a simple prompt to seek human
    # support, not an automated risk assessment or crisis intervention.
    self_harm_item_positive = len(responses) >= 9 and int(
        BDI2_QUESTIONS[8]["options"][responses[8]]["score"]
    ) > 0
    return {
        "total_score": total,
        "risk_level": level,
        "responses": selected,
        "raw_responses_for_ml": [x["selected_text"] for x in selected],
        "storage_consent": True,
        "research_consent": research_consent,
        "training_status": "eligible" if research_consent else "not_consented",
        "created_at": datetime.now(timezone.utc),
        "schema_version": 3,
        "self_harm_item_positive": self_harm_item_positive
    }

def save_assessment(document: dict) -> str:
    from backend.database import get_collections
    _, assessments, _, _ = get_collections()
    result = assessments.insert_one(document)
    return str(result.inserted_id)

def save_recommendation_feedback(assessment_id: str, followed: bool) -> None:
    if not isinstance(followed, bool):
        raise ValueError("Follow-up response must be true or false.")
    try:
        object_id = ObjectId(assessment_id)
    except (InvalidId, TypeError) as exc:
        raise ValueError("Invalid assessment ID.") from exc

    from backend.database import get_collections
    _, assessments, _, _ = get_collections()
    result = assessments.update_one(
        {"_id": object_id},
        {"$set": {
            "recommendation_feedback": {
                "followed": followed,
                "recorded_at": datetime.now(timezone.utc)
            }
        }}
    )
    if result.matched_count == 0:
        raise LookupError("Assessment not found.")
