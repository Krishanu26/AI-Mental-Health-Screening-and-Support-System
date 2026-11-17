from __future__ import annotations
import os
from flask import Flask, jsonify, request
from flask_cors import CORS

from backend.assessment_data import BDI2_QUESTIONS, RECOMMENDATIONS
from backend.assessment import (
    create_assessment_document,
    save_assessment,
    save_recommendation_feedback,
)
from backend.database import ping_database
from backend.training import load_champion
from backend.chatbot import reply_to_message

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ["http://127.0.0.1:5173", "http://localhost:5173"]}})

@app.get("/api/health")
def health():
    try:
        ping_database()
        mongo = "connected"
    except Exception as exc:
        mongo = f"unavailable: {type(exc).__name__}"
    model, metadata = (None, None)
    try:
        model, metadata = load_champion()
    except Exception:
        pass
    return jsonify({"api": "ok", "mongodb": mongo,
                    "experimental_model": metadata or "not yet promoted"})

@app.get("/api/questions")
def questions():
    # The app serves the assessment content configured in the notebook.
    return jsonify({"questions": BDI2_QUESTIONS})

@app.post("/api/assessment")
def submit_assessment():
    data = request.get_json(silent=True) or {}
    try:
        document = create_assessment_document(
            responses=data.get("responses", []),
            storage_consent=data.get("storage_consent") is True,
            research_consent=data.get("research_consent") is True
        )
        document_id = save_assessment(document)
        level = document["risk_level"]
        response = {
            "saved": True,
            "assessment_id": document_id,
            "total_score": document["total_score"],
            "risk_level": level,
            "recommendations": RECOMMENDATIONS.get(level, {}),
            "self_harm_item_positive": document["self_harm_item_positive"],
            "notice": "This is a screening result, not a diagnosis. The experimental ML model is not used for clinical decisions."
        }
        return jsonify(response), 201
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 400
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("Assessment save failed")
        return jsonify({"error": "Could not save the assessment. Check MongoDB configuration."}), 503

@app.post("/api/assessment/<assessment_id>/recommendation-feedback")
def recommendation_feedback(assessment_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON response is required."}), 400
    try:
        save_recommendation_feedback(assessment_id, data.get("followed"))
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
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    if not message or len(message) > 4000:
        return jsonify({"error": "Enter a message up to 4000 characters."}), 400
    return jsonify({"reply": reply_to_message(message)})

@app.get("/api/model-status")
def model_status():
    try:
        model, meta = load_champion()
        return jsonify({"available": model is not None, "metadata": meta})
    except Exception:
        return jsonify({"available": False, "metadata": None}), 200
