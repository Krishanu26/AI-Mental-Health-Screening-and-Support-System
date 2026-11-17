from __future__ import annotations
import os
import re
import time
import pickle
import hashlib
import logging
from collections import Counter
from datetime import datetime, timezone

from bson import ObjectId
from gridfs import GridFS
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from backend.database import get_client, get_collections

log = logging.getLogger("ori_ai.training")
MODEL_NAME = "bdi2_text_classifier_experimental"

def _clean_text(value):
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            value = " ".join(str(item.get("selected_text", "")) for item in value)
        else:
            value = " ".join(map(str, value))
    text = re.sub(r"[^a-z\\s]", " ", str(value or "").lower())
    return " ".join(text.split())

def _champion(registry):
    return registry.find_one(
        {"model_name": MODEL_NAME, "status": "champion"},
        sort=[("created_at", -1)]
    )

def maybe_train():
    threshold = max(2, int(os.getenv("TRAINING_THRESHOLD", "50")))
    client = get_client()
    db, assessments, registry, runs = get_collections()
    state_id = f"{MODEL_NAME}:state"
    state = registry.find_one({"_id": state_id})
    last_completed_at = state.get("last_completed_at") if state else None

    new_query = {"research_consent": True}
    if last_completed_at:
        new_query["created_at"] = {"$gt": last_completed_at}
    new_count = assessments.count_documents(new_query)
    if new_count < threshold:
        return {"status": "waiting", "new_records": new_count, "threshold": threshold}

    # Only consented records and no direct identifiers are loaded for training.
    docs = list(assessments.find(
        {"research_consent": True},
        {"_id": 1, "raw_responses_for_ml": 1, "responses": 1, "risk_level": 1}
    ))
    examples = []
    for doc in docs:
        label = doc.get("risk_level")
        text = _clean_text(doc.get("raw_responses_for_ml") or doc.get("responses"))
        if label and text:
            examples.append((text, str(label)))
    if len(examples) < threshold:
        return {"status": "waiting_for_usable_records", "usable_records": len(examples)}

    labels = [label for _, label in examples]
    counts = Counter(labels)
    if len(counts) < 2 or min(counts.values()) < 2:
        return {"status": "waiting_for_class_diversity", "class_counts": dict(counts)}

    X = [text for text, _ in examples]
    y = labels
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    candidate = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=3000, ngram_range=(1, 2))),
        ("classifier", LogisticRegression(
            max_iter=2000, class_weight="balanced", random_state=42
        ))
    ])
    candidate.fit(X_train, y_train)
    pred = candidate.predict(X_test)
    weighted_f1 = float(f1_score(y_test, pred, average="weighted"))
    macro_f1 = float(f1_score(y_test, pred, average="macro"))
    accuracy = float(accuracy_score(y_test, pred))
    min_f1 = float(os.getenv("MIN_MODEL_WEIGHTED_F1", "0.60"))
    promote = weighted_f1 >= min_f1

    now = datetime.now(timezone.utc)
    run_number = runs.count_documents({"model_name": MODEL_NAME}) + 1
    version = f"1.{run_number}.0"
    run_id = hashlib.sha256(f"{now.isoformat()}:{len(examples)}".encode()).hexdigest()[:16]
    payload = pickle.dumps(candidate, protocol=pickle.HIGHEST_PROTOCOL)
    fs = GridFS(db, collection="model_artifacts")
    artifact_id = fs.put(
        payload,
        filename=f"{MODEL_NAME}_{version}.pkl",
        content_type="application/python-pickle",
        metadata={"model_name": MODEL_NAME, "version": version, "run_id": run_id}
    )

    runs.insert_one({
        "run_id": run_id,
        "model_name": MODEL_NAME,
        "version": version,
        "created_at": now,
        "records": len(examples),
        "new_records_since_last_run": new_count,
        "class_counts": dict(counts),
        "weighted_f1": weighted_f1,
        "macro_f1": macro_f1,
        "accuracy": accuracy,
        "quality_gate": min_f1,
        "promoted": promote,
        "gridfs_id": artifact_id,
        "report": classification_report(y_test, pred, output_dict=True, zero_division=0),
        "validation_note": "Internal holdout only; labels are derived from questionnaire score bands. Not clinical validation."
    })

    status = "candidate"
    if promote:
        registry.update_many(
            {"model_name": MODEL_NAME, "status": "champion"},
            {"$set": {"status": "superseded", "superseded_at": now}}
        )
        status = "champion"
    registry.insert_one({
        "model_name": MODEL_NAME,
        "version": version,
        "status": status,
        "created_at": now,
        "gridfs_id": artifact_id,
        "run_id": run_id,
        "weighted_f1": weighted_f1,
        "macro_f1": macro_f1,
        "accuracy": accuracy
    })
    registry.update_one(
        {"_id": state_id},
        {"$set": {"last_completed_at": now, "updated_at": now}},
        upsert=True
    )
    log.info("Training completed: version=%s status=%s weighted_f1=%.4f", version, status, weighted_f1)
    return {"status": status, "version": version, "weighted_f1": weighted_f1,
            "macro_f1": macro_f1, "accuracy": accuracy, "records": len(examples)}

def load_champion():
    client = get_client()
    db, _, registry, _ = get_collections()
    champion = _champion(registry)
    if not champion:
        return None, None
    fs = GridFS(db, collection="model_artifacts")
    model = pickle.loads(fs.get(champion["gridfs_id"]).read())
    meta = {"version": champion["version"], "weighted_f1": champion.get("weighted_f1")}
    return model, meta

def training_worker():
    poll = max(10, int(os.getenv("TRAINING_POLL_SECONDS", "60")))
    log.info("MongoDB training worker started; polling every %s seconds.", poll)
    while True:
        try:
            result = maybe_train()
            if result.get("status") not in ("waiting",):
                log.info("Training worker status: %s", result)
        except Exception:
            log.exception("Training worker check failed")
        time.sleep(poll)
