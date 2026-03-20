"""Configuration helpers for the GradPath web backend."""

from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"

API_TITLE = "GradPath UI API"
API_VERSION = "1.0.0"

DEFAULT_TARGET_SEMESTER = os.getenv("GRADPATH_DEFAULT_TARGET_SEMESTER", "Fall 2026")
DEFAULT_MAX_CREDITS = int(os.getenv("GRADPATH_DEFAULT_MAX_CREDITS", "9"))
FRONTEND_ORIGIN = os.getenv("GRADPATH_FRONTEND_ORIGIN", "http://localhost:5173")
USE_ADK_WRAPPER = os.getenv("GRADPATH_USE_ADK_WRAPPER", "false").lower() == "true"
