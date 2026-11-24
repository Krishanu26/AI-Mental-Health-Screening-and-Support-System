"""Standalone MongoDB training worker for container deployments."""
from dotenv import load_dotenv

load_dotenv()

from backend.training import training_worker


if __name__ == "__main__":
    training_worker()
