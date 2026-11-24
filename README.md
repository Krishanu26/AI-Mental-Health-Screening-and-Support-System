# AI Mental Health Screening and Support System

AI-based mental-health screening and wellbeing companion built with React,
Flask, and MongoDB, with optional recommendation follow-up and no physical
movement tracking.

This is a modular local-development scaffold extracted from your uploaded notebook. Start the application with **one command**:

```powershell
python main.py
```

The launcher starts:
- Flask API on `http://127.0.0.1:5000`
- React/Vite frontend on `http://127.0.0.1:5173` (runs `npm install` on first launch if needed)
- MongoDB-backed assessment storage
- A background threshold-training worker (checks every 60 seconds)
- Optional Ollama chat integration when enabled in `.env`

## 1. Requirements
- Python 3.11 or 3.12
- Node.js 20+ and npm (for React frontend)
- MongoDB Atlas account or local MongoDB
- Optional: Ollama installed with a model such as `llama3`

## 2. Setup on Windows / VS Code

Open this folder in VS Code, then run in the terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

The example `.env` uses a local MongoDB server at `mongodb://127.0.0.1:27017`.
Start MongoDB locally before running the app, or edit `.env` and set your Atlas
connection string as `MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-url>/`.
Do not paste credentials into source code or commit `.env`.

In MongoDB Atlas:
1. Create a database user.
2. Add your current IP in Network Access.
3. Copy the Python driver connection string.
4. Replace username/password/cluster in `.env`.

Then run:

```powershell
python main.py
```

Open `http://127.0.0.1:5173`.
Check `http://127.0.0.1:5000/api/health` and confirm `mongodb` is `connected`.

## 3. What is saved
Assessment storage consent and research/model-training consent are separate:
- `storage_consent` must be true to save the assessment.
- `research_consent` must be true to use a de-identified record in experimental training.
- Users can optionally report whether they followed a suggested next step; this response is saved with their assessment after they submit it.
- The app does not track physical movement.
- The app does not save data when storage consent is declined.
- Do not enter real patient data into this development prototype until you have suitable security, privacy notices, access controls, retention rules, and legal/ethics approval.

## 4. Automatic training
The worker polls MongoDB every `TRAINING_POLL_SECONDS` seconds. It trains when at least `TRAINING_THRESHOLD` new research-consented records have arrived since the previous completed training batch. It requires at least two labels and enough examples per label for a stratified split.

Candidate models are stored in MongoDB GridFS with metadata in `model_registry`. Promotion requires the configured holdout weighted-F1 threshold. A rejected candidate is retained for audit but does not replace the champion.

**Important scientific limitation:** in this project the target category is calculated from the BDI-II total score. The text model therefore learns to reproduce score-derived categories; it does not independently detect or diagnose depression. It is experimental and must never drive clinical decisions. The deterministic questionnaire score remains the displayed screening category.

The threshold worker only runs while `main.py` is running. This is a local development setup, not a production always-on service.

## 5. Optional Ollama chatbot
Install Ollama separately, pull a model, and set in `.env`:
```env
OLLAMA_ENABLED=true
OLLAMA_MODEL=llama3
```
Then start Ollama before `python main.py`. The chatbot is supportive only and does not provide diagnosis or crisis assessment.

## 6. Project layout
- `main.py`: one-command process launcher
- `backend/app.py`: Flask routes
- `backend/database.py`: MongoDB connection and collections
- `backend/training.py`: threshold training, evaluation, GridFS registry
- `backend/assessment.py`: score calculation and consent-aware persistence
- `backend/chatbot.py`: optional Ollama integration
- `backend/assessment_data.py`: questionnaire and recommendation data extracted from your notebook
- `frontend/`: React UI
- `notebooks/`: your modified notebook preserved

Assessment documents are stored in the `users` collection in the database
configured by `MONGODB_DATABASE`. Training metadata is stored in
`model_registry` and `training_runs`; model artifacts use GridFS.

## 7. Stop
Press `Ctrl+C` in the terminal running `main.py`. It stops the frontend and backend worker.
