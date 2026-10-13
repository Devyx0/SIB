"""JWT helpers — sign and verify tokens using settings.SECRET_KEY."""
from __future__ import annotations

from .config import settings

# Placeholder — real implementation in Phase B once auth endpoints are wired.
SECRET_KEY: str = settings.SECRET_KEY
ALGORITHM = "HS256"
