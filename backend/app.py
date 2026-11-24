from __future__ import annotations

from flask import Flask, jsonify, request
from flask_cors import CORS

from backend.assessment_data import BDI2_QUESTIONS, RECOMMENDATIONS
from backend.assessment import create_assessment_document, save_assessment, save_recommendation_feedback
from backend.database import ping_database
from backend.training import load_champion
from backend.chatbot import reply_to_message

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
CORS(app, resources={r"/api/*": {"origins": [
    "http://127.0.0.1:5173", "http://localhost:5173"
]}})


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "Request body is too large."}), 413


@app.get("/api/health")
def health():
    try:
        ping_database()
        mongo = "connected"
    except Exception as exc:
        mongo = f"unavailable: {type(exc).__name__}"
    metadata = None
    if mongo == "connected":
        try:
            _model, metadata = load_champion()
        except Exception:
            app.logger.exception("Could not load experimental model metadata")
    return jsonify({
        "api": "ok", "mongodb": mongo,
        "experimental_model": metadata or "not yet promoted"
    })


@app.get("/api/questions")
def questions():
    return jsonify({"questions": BDI2_QUESTIONS})


@app.post("/api/assessment")
def submit_assessment():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    storage_consent = data.get("storage_consent", False)
    research_consent = data.get("research_consent", False)
    if not isinstance(storage_consent, bool) or not isinstance(research_consent, bool):
        return jsonify({"error": "Consent values must be true or false."}), 400
    try:
        document = create_assessment_document(
            responses=data.get("responses"),
            storage_consent=storage_consent,
            research_consent=research_consent,
        )
        # Screening remains available without storage consent; no DB write occurs.
        document_id = save_assessment(document) if storage_consent else None
        level = document["risk_level"]
        self_harm_positive = document["self_harm_item_positive"]
        return jsonify({
            "saved": document_id is not None,
            "feedback_token": document.get("feedback_token"),
            "total_score": document["total_score"],
            "risk_level": level,
            "recommendations": RECOMMENDATIONS.get(level, {}),
            "self_harm_item_positive": self_harm_positive,
            "safety_guidance": (
                "Your answer suggests speaking promptly with a qualified mental-health "
                "professional or trusted person. If you may act on these thoughts or "
                "are in immediate danger, contact local emergency services now."
                if self_harm_positive else None
            ),
            "notice": (
                "This is a screening result, not a diagnosis. The experimental ML "
                "model is not used for clinical decisions."
            ),
            "storage_notice": (
                "Your assessment was saved with your consent." if document_id
                else "Your assessment was not saved; this result is only in this response."
            ),
        }), 201
    except (PermissionError, ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("Assessment processing failed")
        return jsonify({"error": "Could not process the assessment. Check database configuration if storage was selected."}), 503


@app.post("/api/assessment/feedback/<feedback_token>/recommendation-feedback")
def recommendation_feedback(feedback_token):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON response is required."}), 400
    try:
        save_recommendation_feedback(feedback_token, data.get("followed"))
        return jsonify({"saved": True}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception:
        app.logger.exception("Recommendation feedback save failed")
        return jsonify({"error": "Could not save recommendation feedback."}), 503


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    message = data.get("message")
    if not isinstance(message, str):
        return jsonify({"error": "Message must be text."}), 400
    message = message.strip()
    if not message or len(message) > 4000:
        return jsonify({"error": "Enter a message up to 4000 characters."}), 400
    try:
        return jsonify({"reply": reply_to_message(message)})
    except Exception:
        app.logger.exception("Chat response generation failed")
        return jsonify({"error": "The chat service is currently unavailable."}), 503


@app.get("/api/model-status")
def model_status():
    try:
        model, meta = load_champion()
        return jsonify({"available": model is not None, "metadata": meta})
    except Exception:
        return jsonify({"available": False, "metadata": None}), 200
