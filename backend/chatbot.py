import os

import requests


DISABLED_REPLY = (
    "The AI chat assistant is not enabled yet. Install Ollama, download a "
    "compatible model, and set OLLAMA_ENABLED=true in .env to enable it."
)
UNAVAILABLE_REPLY = "The local AI service is currently unavailable. Please try again later."


def reply_to_message(message: str) -> str:
    if os.getenv("OLLAMA_ENABLED", "false").strip().lower() != "true":
        return DISABLED_REPLY
    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3")
    prompt = (
        "You are a supportive wellbeing companion, not a clinician. Do not diagnose, "
        "prescribe, or claim to assess suicide risk. Encourage qualified human support "
        "for serious distress. If the user may be in immediate danger, encourage "
        "contacting local emergency services or a trusted person now. "
        "Respond empathetically and briefly.\n\n"
        f"User: {message}\nAssistant:"
    )
    try:
        response = requests.post(
            f"{base}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"num_predict": 256}},
            timeout=(5, 60),
        )
        response.raise_for_status()
        payload = response.json()
        reply = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(reply, str) or not reply.strip():
            return UNAVAILABLE_REPLY
        return reply.strip()
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return UNAVAILABLE_REPLY
