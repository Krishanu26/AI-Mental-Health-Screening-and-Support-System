from __future__ import annotations
import os
from functools import lru_cache
from pymongo import MongoClient
from pymongo.errors import PyMongoError

_client = None

def get_client():
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI is missing. Copy .env.example to .env and configure it.")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    return _client

def get_db():
    return get_client()[os.getenv("MONGODB_DATABASE", "bdi_result")]

def get_collections():
    db = get_db()
    assessments = db["users"]
    registry = db["model_registry"]
    runs = db["training_runs"]
    assessments.create_index([("created_at", -1)])
    assessments.create_index([("research_consent", 1), ("created_at", 1)])
    registry.create_index([("model_name", 1), ("status", 1)])
    runs.create_index([("created_at", -1)])
    return db, assessments, registry, runs

def ping_database():
    get_client().admin.command("ping")
    return True
