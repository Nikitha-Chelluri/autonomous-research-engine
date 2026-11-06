import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root: services/dashboard/config.py -> parents[2] == Project_2
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
# Use 127.0.0.1, not "localhost": on Windows, localhost often resolves to ::1 first;
# Docker commonly binds ::1:8000 so /research/jobs 404s while FastAPI is on 127.0.0.1:8000.
API_BASE_URL = os.getenv("RESEARCH_API_URL", "http://127.0.0.1:8000").rstrip("/")
