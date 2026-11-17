import os
import requests

def reply_to_message(message: str) -> str:
    if os.getenv("OLLAMA_ENABLED", "false").lower() != "true":
        return ("The AI chat assistant is not enabled yet. You can enable it by installing "
                "Ollama, downloading a model, and setting OLLAMA_ENABLED=true in .env.")
    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3")
    prompt = (
        "You are a supportive wellbeing companion, not a clinician. Do not diagnose, "
        "prescribe, or assess suicide risk. Encourage qualified human support for serious "
        "distress. If the user may be in immediate danger, encourage contacting local "
        "emergency services or a trusted person now. Respond empathetically and briefly.\\n\\n"
        f"User: {message}\\nAssistant:"
    )
    try:
        response = requests.post(
            f"{base}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=90
        )
        response.raise_for_status()
        return response.json().get("response", "I couldn't generate a response right now.")
    except requests.RequestException:
        return "The local AI service is currently unavailable. Please try again later."
